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
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timedelta

from config import now_local
from database import (
    get_bookings_due_for_reminder, claim_notification, mark_notification,
    init_database,
)
from email_utils import send_slot_reminder, last_message_id

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)
logger = logging.getLogger('reminder_worker')

CHANNEL = 'email'
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


def run_once(dry_run=False, now=None):
    """One pass: find everything due and send it.

    Returns a count per outcome.
    """
    now = now or now_local()
    lead = get_lead_minutes()
    grace = get_grace_minutes()

    due = get_bookings_due_for_reminder(
        lead_minutes=lead, channel=CHANNEL, kind=KIND,
        now=now, window_minutes=grace)

    counts = {'sent': 0, 'failed': 0, 'skipped': 0, 'claimed-by-other': 0}
    if not due:
        # Log an idle pass periodically rather than every time: silence
        # makes a running worker indistinguishable from a dead one, but
        # a line every 10s would bury the sends that matter.
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
