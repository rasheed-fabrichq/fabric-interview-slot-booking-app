"""
Show what the reminder worker currently sees.

    python check_reminders.py

Prints the current time, the configured window, and every booking with
whether its reminder is due, already sent, or still waiting -- so a
reminder that has not arrived can be diagnosed without reading the
database by hand.
"""
from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta

from config import now_local
from database import get_db_connection
from job_call_settings import get_job_call_config
from reminder_worker import (
    get_lead_minutes, get_grace_minutes, get_call_lead_minutes,
    calls_enabled, job_calls_enabled, job_call_lead_minutes,
    CHANNEL, CALL_CHANNEL, KIND,
)

now = now_local()
lead = get_lead_minutes()
grace = get_grace_minutes()
calls_lead_display = get_call_lead_minutes()
calls_on_globally = calls_enabled()

print(f'Now (IST):        {now.strftime("%d-%m-%Y %H:%M:%S")}')
print(f'Reminder lead:    {lead} minutes before the slot')
print(f'Grace period:     {grace} minutes after the send window opens')
# The date is included because a large lead pushes the window past
# midnight, where a bare %H:%M reads as though it ran backwards.
print(f'Sending window:   slots starting between '
      f'{(now - timedelta(minutes=grace)).strftime("%d-%m %H:%M")} and '
      f'{(now + timedelta(minutes=lead)).strftime("%d-%m %H:%M")}')
if lead > 240:
    print(f'                  (lead is {lead/60:.1f} hours -- set '
          f'REMINDER_LEAD_MINUTES=15 for the real run)')
print()

conn = get_db_connection()
rows = conn.execute('''
    SELECT c.name, c.email, c.phone, s.date, s.start_time, jc.job_name,
           b.candidate_id, b.job_id,
           n.status AS reminder_status, n.error AS reminder_error,
           cn.status AS call_status, cn.error AS call_error
    FROM bookings b
    JOIN candidates c
      ON b.candidate_id = c.candidate_id AND b.job_id = c.job_id
    JOIN slots s ON b.slot_id = s.id
    JOIN job_configs jc ON b.job_id = jc.job_id
    LEFT JOIN notifications n
      ON n.candidate_id = b.candidate_id AND n.job_id = b.job_id
     AND n.channel = ? AND n.kind = ?
    LEFT JOIN notifications cn
      ON cn.candidate_id = b.candidate_id AND cn.job_id = b.job_id
     AND cn.channel = ? AND cn.kind = ?
    ORDER BY s.date, s.start_time
''', (CHANNEL, KIND, CALL_CHANNEL, KIND)).fetchall()
conn.close()

if not rows:
    print('No bookings found.')
    print()
    print('The reminder only fires for a BOOKED slot. Upload a candidate,')
    print('then open their booking link from Admin > Candidates and book a')
    print('slot a few minutes in the future.')
    raise SystemExit(0)

def describe(status, error, delta_min, channel_lead, enabled=True,
             blocked_reason=None):
    """One channel's state for a booking, in plain words."""
    if status == 'sent':
        return 'SENT'
    if status == 'failed':
        return f'FAILED - {error}'
    if status == 'skipped':
        return f'SKIPPED - {error}'
    if status:
        return status.upper()
    if not enabled:
        return blocked_reason or 'disabled'
    if -grace <= delta_min <= channel_lead:
        return 'DUE NOW -- run the worker'
    if delta_min > channel_lead:
        return f'waiting ({delta_min - channel_lead} min)'
    return 'missed (slot too far past)'


print(f'{"Candidate":20} {"Slot":17} {"In":>9}  {"Email":<26} Call')
print('-' * 104)

for r in rows:
    try:
        slot_dt = datetime.strptime(
            f'{r["date"]} {r["start_time"]}', '%d-%m-%Y %H:%M')
    except ValueError:
        continue

    delta_min = int(round((slot_dt - now).total_seconds() / 60))
    when = f'{delta_min} min' if delta_min >= 0 else f'{-delta_min} ago'

    email_state = describe(r['reminder_status'], r['reminder_error'],
                           delta_min, lead)

    # The call has its own lead time and can be switched off per job.
    job_cfg = get_job_call_config(r['job_id'])
    call_lead = job_call_lead_minutes(r['job_id'], job_cfg)
    call_on = job_calls_enabled(r['job_id'], job_cfg)
    if not r['phone']:
        call_state = 'no phone number'
    else:
        call_state = describe(r['call_status'], r['call_error'], delta_min,
                              call_lead, enabled=call_on,
                              blocked_reason='calls off (CALLS_ENABLED)')

    name = (r['name'] or '')[:18]
    print(f'{name:20} {r["date"]} {r["start_time"]:5} {when:>9}  '
          f'{email_state[:25]:<26} {call_state}')

print()
print(f'Call lead: {calls_lead_display} minutes   '
      f'Calls enabled: {"yes" if calls_on_globally else "no (CALLS_ENABLED=false)"}')
print()
print('To send/place what is due now:  python reminder_worker.py --once')
print('To preview without sending:     python reminder_worker.py --once --dry-run')
