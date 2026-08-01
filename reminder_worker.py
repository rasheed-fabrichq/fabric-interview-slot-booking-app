"""
Sends reminders to candidates shortly before their booked slot starts.

Run as a long-lived process alongside the Flask app:

    python reminder_worker.py

It wakes every POLL_INTERVAL_SECONDS, finds bookings starting within the
next REMINDER_LEAD_MINUTES, and sends each candidate one reminder.

Why a separate process rather than a thread in the web app: the
confirmation email uses a daemon thread with a sleep, which loses the
email if the app restarts inside the delay. A reminder is far more
time-critical, so the schedule lives in the database instead -- restart
the worker and it picks up whatever is still due.

Double-sending is prevented by the notifications table, not by this
loop: each reminder is claimed with an INSERT whose UNIQUE constraint
only one caller can win. Running two workers by accident is therefore
safe, and so is restarting mid-run.

Options:

    --once      run a single pass and exit (for cron, or testing)
    --dry-run   report what would be sent without sending or claiming
"""
# dotenv MUST be loaded before email_utils, which reads os.environ for
# the SES credentials.
from dotenv import load_dotenv
load_dotenv()

import argparse
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

from config import now_local
from database import (
    get_bookings_due_for_reminder, claim_notification, mark_notification,
    init_database, create_call_log, get_pollable_call_logs,
    update_call_log, bump_call_poll_attempt,
)
from job_call_settings import get_job_call_config, get_all_job_call_configs
from email_utils import send_slot_reminder, last_message_id
from caller_utils import build_call_payload, place_call, get_call_details

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('reminder_worker')

CHANNEL = 'email'
CALL_CHANNEL = 'call'
KIND = 'reminder_15m'


def _int_env(key, default):
    raw = os.environ.get(key, '')
    try:
        value = int(str(raw).strip())
        return value if value > 0 else default
    except (TypeError, ValueError):
        if str(raw).strip():
            logger.warning('Ignoring invalid %s=%r; using %s',
                           key, raw, default)
        return default


def get_lead_minutes():
    """How long before a slot the reminder goes out."""
    return _int_env('REMINDER_LEAD_MINUTES', 15)


def get_call_lead_minutes():
    """How long before a slot the reminder call is placed.

    Separate from the email lead so the two can be tuned independently.
    """
    return _int_env('CALL_LEAD_MINUTES', 30)


def calls_enabled():
    """Whether to place reminder calls at all.

    Off by default: the calling system is a separate service, and a
    misconfigured deployment should fail closed rather than dial
    candidates unexpectedly.
    """
    return _cfg_flag('CALLS_ENABLED', False)


def _cfg_flag(key, default=False):
    raw = os.environ.get(key, '').strip().lower()
    if not raw:
        return default
    return raw in ('1', 'true', 'yes', 'on')


def get_poll_interval():
    """Seconds between passes."""
    return _int_env('REMINDER_POLL_INTERVAL_SECONDS', 60)


def get_grace_minutes():
    """How late a missed reminder is still worth sending.

    If the worker was down over a slot's reminder window, sending "your
    interview starts in 15 minutes" an hour after it began is worse
    than sending nothing. Past this many minutes into the window, the
    reminder is skipped instead.
    """
    return _int_env('REMINDER_GRACE_MINUTES', 5)


def build_interview_link(booking):
    """The join link, with the slot's start/end appended.

    Mirrors add_expiry_to_interview_link in app.py. It lives here too so
    the worker does not import the Flask app, which would run
    init_database and bind config at import time.
    """
    link = (booking.get('interview_link') or '').strip()
    if not link:
        return ''
    start_dt = booking['slot_datetime']
    end_dt = start_dt + timedelta(
        minutes=booking.get('slot_duration_minutes') or 0)
    separator = '&' if '?' in link else '?'
    return (f"{link}{separator}"
            f"start_time={start_dt.strftime('%Y-%m-%dT%H:%M')}"
            f"&end_time={end_dt.strftime('%Y-%m-%dT%H:%M')}")


def send_one(booking, now, dry_run=False):
    """Claim and send a single reminder.

    Returns one of 'sent', 'failed', 'skipped', 'claimed-by-other'.
    """
    candidate_id = booking['candidate_id']
    job_id = booking['job_id']
    email = booking['email']
    slot_dt = booking['slot_datetime']
    minutes_until = max(0, int(round((slot_dt - now).total_seconds() / 60)))

    if dry_run:
        logger.info('[DRY RUN] would remind %s (%s) -- slot %s %s, in %s min',
                    booking['name'], email, booking['date'],
                    booking['start_time'], minutes_until)
        return 'sent'

    # Claim first: if this fails, someone else owns the send. Doing any
    # work before this point risks two workers both emailing.
    if not claim_notification(candidate_id, job_id, CHANNEL, KIND,
                              booking['date'], booking['start_time'],
                              scheduled_for=now):
        logger.debug('Already claimed: %s / %s', candidate_id, job_id)
        return 'claimed-by-other'

    if not email:
        logger.warning('No email address for candidate %s; skipping',
                       candidate_id)
        mark_notification(candidate_id, job_id, CHANNEL, KIND, 'skipped',
                          error='No email address on record')
        return 'skipped'

    try:
        duration = booking.get('slot_duration_minutes')
        end_dt = slot_dt + timedelta(minutes=duration or 0)

        success, error = send_slot_reminder(
            candidate_name=booking['name'],
            candidate_email=email,
            job_name=booking['job_name'],
            slot_date=booking['date'],
            day_of_week=booking['day_of_week'],
            start_time=slot_dt.strftime('%I:%M %p'),
            end_time=end_dt.strftime('%I:%M %p'),
            interview_link_with_expiry=build_interview_link(booking),
            minutes_until=minutes_until,
            duration_minutes=duration,
        )
    except Exception as exc:
        logger.error('Exception reminding %s: %s', email, exc)
        logger.debug(traceback.format_exc())
        mark_notification(candidate_id, job_id, CHANNEL, KIND, 'failed',
                          error=str(exc))
        return 'failed'

    if success:
        logger.info('Reminded %s -- slot %s %s (in %s min)',
                    email, booking['date'], booking['start_time'],
                    minutes_until)
        mark_notification(candidate_id, job_id, CHANNEL, KIND, 'sent',
                          provider_ref=last_message_id())
        return 'sent'

    logger.error('Failed to remind %s: %s', email, error)
    mark_notification(candidate_id, job_id, CHANNEL, KIND, 'failed',
                      error=error)
    return 'failed'


def call_one(booking, now, dry_run=False):
    """Claim and place a single reminder call.

    Returns 'sent', 'failed', 'skipped' or 'claimed-by-other'. Uses the
    same claim-before-work pattern as the email, against the same table
    with channel='call', so a candidate cannot be called twice.
    """
    candidate_id = booking['candidate_id']
    job_id = booking['job_id']
    phone = booking.get('phone')
    slot_dt = booking['slot_datetime']
    duration = booking.get('slot_duration_minutes') or 0
    end_dt = slot_dt + timedelta(minutes=duration)

    job_config = get_job_call_config(job_id)

    if dry_run:
        payload = build_call_payload(
            candidate_name=booking['name'], phone_e164=phone,
            job_name=booking['job_name'], slot_start=slot_dt,
            slot_end=end_dt, duration_minutes=duration, now=now,
            user_id=candidate_id, job_config=job_config)
        logger.info('[DRY RUN] would call %s for %s%s:\n%s',
                    phone or '(no number)', booking['name'],
                    ' (job override)' if job_config else '',
                    json.dumps(payload, indent=2))
        return 'sent'

    if not claim_notification(candidate_id, job_id, CALL_CHANNEL, KIND,
                              booking['date'], booking['start_time'],
                              scheduled_for=now):
        logger.debug('Call already claimed: %s / %s', candidate_id, job_id)
        return 'claimed-by-other'

    # No number is the normal case for anyone whose phone did not
    # normalise on upload, so it is recorded and skipped rather than
    # treated as a failure to investigate.
    if not phone:
        logger.info('No phone number for %s; skipping call', booking['name'])
        mark_notification(candidate_id, job_id, CALL_CHANNEL, KIND, 'skipped',
                          error='No phone number on record')
        return 'skipped'

    try:
        payload = build_call_payload(
            candidate_name=booking['name'], phone_e164=phone,
            job_name=booking['job_name'], slot_start=slot_dt,
            slot_end=end_dt, duration_minutes=duration, now=now,
            user_id=candidate_id, job_config=job_config)
        success, error, reference = place_call(payload,
                                               job_config=job_config)
    except Exception as exc:
        logger.error('Exception calling %s: %s', phone, exc)
        logger.debug(traceback.format_exc())
        mark_notification(candidate_id, job_id, CALL_CHANNEL, KIND, 'failed',
                          error=str(exc))
        return 'failed'

    if success:
        logger.info('Call queued for %s (%s) -- slot %s %s',
                    booking['name'], phone, booking['date'],
                    booking['start_time'])
        mark_notification(candidate_id, job_id, CALL_CHANNEL, KIND, 'sent',
                          provider_ref=reference)
        # Record it so the poller can follow it to an outcome. The
        # payload is stored as sent, phone number and spoken variables
        # included, so the call can be explained afterwards.
        if reference:
            create_call_log(
                candidate_id=candidate_id, job_id=job_id,
                execution_id=reference, phone=phone,
                slot_date=booking['date'],
                slot_start_time=booking['start_time'],
                request_payload=payload)
        else:
            logger.warning('No execution id returned for %s; the call '
                           'cannot be tracked', booking['name'])
        return 'sent'

    logger.error('Failed to queue call for %s: %s', phone, error)
    mark_notification(candidate_id, job_id, CALL_CHANNEL, KIND, 'failed',
                      error=error)
    return 'failed'


# Timestamp of the last idle-pass log line, so the heartbeat can be
# rate-limited independently of how often the loop actually runs.
_last_heartbeat = [None]

# Seconds between "nothing due" log lines.
HEARTBEAT_SECONDS = 300


def _heartbeat(now, lead, grace):
    """Log an idle pass, at most once every HEARTBEAT_SECONDS."""
    last = _last_heartbeat[0]
    if last is not None and (now - last).total_seconds() < HEARTBEAT_SECONDS:
        return
    _last_heartbeat[0] = now
    # Include the date: a large lead pushes the window past midnight,
    # where a bare %H:%M reads as though it ran backwards.
    fmt = '%d-%m %H:%M'
    window_start = (now - timedelta(minutes=grace)).strftime(fmt)
    window_end = (now + timedelta(minutes=lead)).strftime(fmt)
    logger.info('Idle -- no bookings starting between %s and %s',
                window_start, window_end)


def job_calls_enabled(job_id, job_config=None):
    """Whether calls are on for this specific job.

    A job row can switch calls on or off independently; with no row the
    global CALLS_ENABLED applies.
    """
    if job_config is None:
        job_config = get_job_call_config(job_id)
    if job_config and job_config.get('calls_enabled') is not None:
        return bool(job_config['calls_enabled'])
    return calls_enabled()


def job_call_lead_minutes(job_id, job_config=None):
    """Call lead time for this job, falling back to the global value."""
    if job_config is None:
        job_config = get_job_call_config(job_id)
    if job_config and job_config.get('lead_minutes'):
        return int(job_config['lead_minutes'])
    return get_call_lead_minutes()


def get_poll_batch_size():
    """How many calls to poll in one pass."""
    return _int_env('CALL_POLL_BATCH_SIZE', 20)


def get_poll_max_attempts():
    """Give up polling a call after this many attempts.

    At one pass a minute the default is roughly an hour, after which a
    call the provider never closes out stops being polled rather than
    being retried forever.
    """
    return _int_env('CALL_POLL_MAX_ATTEMPTS', 60)


def _poll_calls(dry_run=False):
    """Follow placed calls until they reach an outcome.

    Only terminal states are written. A polling error leaves the row
    alone so the next pass tries again -- treating a network blip as an
    outcome would close out a call that is still ringing.
    """
    if dry_run:
        return {'polled': 0, 'completed': 0}

    rows = get_pollable_call_logs(batch_size=get_poll_batch_size(),
                                  max_attempts=get_poll_max_attempts())
    if not rows:
        return {'polled': 0, 'completed': 0}

    counts = {'polled': 0, 'completed': 0}
    for row in rows:
        execution_id = row['execution_id']
        job_config = get_job_call_config(row['job_id'])
        counts['polled'] += 1
        bump_call_poll_attempt(execution_id)

        details = get_call_details(execution_id, job_config=job_config)

        if not details.get('success'):
            logger.warning('Poll failed for call %s: %s',
                           execution_id, details.get('error'))
            update_call_log(execution_id, error=details.get('error'))
            continue

        status = details['status']

        if not details.get('call_completed'):
            # Still live -- record the status change (queued -> ringing)
            # but nothing terminal.
            update_call_log(execution_id, status=status, error=None)
            continue

        update_call_log(
            execution_id,
            status=status,
            call_successful=1 if details.get('call_successful') else 0,
            hangup_reason=details.get('hangup_reason'),
            duration_seconds=details.get('duration'),
            cost=details.get('cost'),
            transcript=details.get('transcript'),
            recording_available=1 if details.get('recording_available') else 0,
            raw_response=json.dumps(details.get('raw'))[:20000],
            completed_at=now_local(),
            error=None,
        )
        counts['completed'] += 1
        logger.info('Call %s ended: status=%s successful=%s reason=%s '
                    'duration=%ss', execution_id, status,
                    details.get('call_successful'),
                    details.get('hangup_reason'), details.get('duration'))

    if counts['polled']:
        logger.info('Polled %s call(s), %s reached an outcome',
                    counts['polled'], counts['completed'])
    return counts


def _run_calls(now, grace, dry_run=False):
    """Place every reminder call that is due.

    Jobs can have different lead times, so the widest lead is queried
    and each booking is then filtered against its own job's window.
    Querying per job would mean one round trip per job; this is one
    query plus an in-memory filter.
    """
    counts = {'sent': 0, 'failed': 0, 'skipped': 0, 'claimed-by-other': 0}

    job_configs = get_all_job_call_configs()
    global_enabled = calls_enabled()
    global_lead = get_call_lead_minutes()

    # Nothing to do if calls are off globally and no job turns them on.
    any_enabled = global_enabled or any(
        cfg.get('calls_enabled') for cfg in job_configs.values())
    if not any_enabled:
        return counts

    leads = [global_lead] + [
        int(cfg['lead_minutes']) for cfg in job_configs.values()
        if cfg.get('lead_minutes')]
    widest_lead = max(leads)

    candidates = get_bookings_due_for_reminder(
        lead_minutes=widest_lead, channel=CALL_CHANNEL, kind=KIND,
        now=now, window_minutes=grace)
    if not candidates:
        return counts

    due = []
    for booking in candidates:
        job_id = booking['job_id']
        cfg = {k: v for k, v in (job_configs.get(job_id) or {}).items()
               if v is not None}
        if not job_calls_enabled(job_id, cfg):
            continue
        lead = job_call_lead_minutes(job_id, cfg)
        minutes_until = (booking['slot_datetime'] - now).total_seconds() / 60
        # Re-check against this job's own lead, since the query used the
        # widest one across all jobs.
        if minutes_until <= lead:
            due.append(booking)

    if not due:
        return counts

    logger.info('%s call(s) due', len(due))
    for booking in due:
        outcome = call_one(booking, now, dry_run=dry_run)
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def run_once(dry_run=False, now=None):
    """One pass: send every due email, then place every due call.

    The two channels are independent -- a candidate still gets the call
    if SES is down, and still gets the email if the calling system is
    unreachable. Each has its own lead time and its own claim row.

    Returns a count per outcome, combined across both channels.
    """
    now = now or now_local()
    lead = get_lead_minutes()
    grace = get_grace_minutes()

    due = get_bookings_due_for_reminder(
        lead_minutes=lead, channel=CHANNEL, kind=KIND,
        now=now, window_minutes=grace)

    counts = {'sent': 0, 'failed': 0, 'skipped': 0, 'claimed-by-other': 0}

    call_counts = _run_calls(now, grace, dry_run=dry_run)
    for key, value in call_counts.items():
        counts[key] = counts.get(key, 0) + value

    # Follow already-placed calls to their outcome. Runs every pass,
    # independently of whether anything new was due.
    poll_counts = _poll_calls(dry_run=dry_run)

    if not due:
        if not any(call_counts.values()) and not poll_counts['polled']:
            # Log an idle pass periodically rather than every time:
            # silence makes a running worker indistinguishable from a
            # dead one, but a line every 10s would bury what matters.
            _heartbeat(now, lead, grace)
        return counts

    logger.info('%s reminder(s) due within %s minutes', len(due), lead)
    for booking in due:
        outcome = send_one(booking, now, dry_run=dry_run)
        counts[outcome] = counts.get(outcome, 0) + 1

    logger.info('Pass complete: %s', ', '.join(
        f'{k}={v}' for k, v in counts.items() if v))
    return counts


def main():
    parser = argparse.ArgumentParser(
        description='Send slot reminders to candidates.')
    parser.add_argument('--once', action='store_true',
                        help='run a single pass and exit')
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would be sent, without sending')
    args = parser.parse_args()

    # The worker may start before the web app on a fresh box, so it
    # cannot assume the notifications table already exists. This is
    # idempotent -- init_database only creates what is missing.
    init_database()

    lead = get_lead_minutes()
    interval = get_poll_interval()

    if args.dry_run:
        logger.info('DRY RUN -- no emails will be sent, nothing is claimed')

    if args.once:
        # Exit non-zero on a failed pass so cron and CI notice, rather
        # than reporting success for a run that emailed nobody.
        try:
            counts = run_once(dry_run=args.dry_run)
        except Exception as exc:
            logger.error('Pass failed: %s', exc)
            logger.debug(traceback.format_exc())
            return 1
        return 1 if counts.get('failed') else 0

    grace = get_grace_minutes()
    started = now_local()
    logger.info('Reminder worker started: lead=%s min, poll=%s s, grace=%s min',
                lead, interval, grace)
    logger.info('Now %s IST -- reminding bookings that start before %s',
                started.strftime('%d-%m-%Y %H:%M'),
                (started + timedelta(minutes=lead)).strftime('%d-%m-%Y %H:%M'))
    if lead > 240:
        # A lead this large is almost always a typo. Left working, since
        # a long lead is legitimate for testing, but called out.
        logger.warning('REMINDER_LEAD_MINUTES=%s is %.1f hours -- candidates '
                       'will be reminded well before their slot. Set it to 15 '
                       'for the real run.', lead, lead / 60)
    while True:
        try:
            run_once(dry_run=args.dry_run)
        except Exception as exc:
            # A bad pass must not kill the worker, or every later
            # reminder is lost too.
            logger.error('Pass failed: %s', exc)
            logger.debug(traceback.format_exc())
        time.sleep(interval)


if __name__ == '__main__':
    sys.exit(main())
