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
from reminder_worker import get_lead_minutes, get_grace_minutes, CHANNEL, KIND

now = now_local()
lead = get_lead_minutes()
grace = get_grace_minutes()

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
    SELECT c.name, c.email, s.date, s.start_time, jc.job_name,
           n.status AS reminder_status, n.error AS reminder_error
    FROM bookings b
    JOIN candidates c
      ON b.candidate_id = c.candidate_id AND b.job_id = c.job_id
    JOIN slots s ON b.slot_id = s.id
    JOIN job_configs jc ON b.job_id = jc.job_id
    LEFT JOIN notifications n
      ON n.candidate_id = b.candidate_id AND n.job_id = b.job_id
     AND n.channel = ? AND n.kind = ?
    ORDER BY s.date, s.start_time
''', (CHANNEL, KIND)).fetchall()
conn.close()

if not rows:
    print('No bookings found.')
    print()
    print('The reminder only fires for a BOOKED slot. Upload a candidate,')
    print('then open their booking link from Admin > Candidates and book a')
    print('slot a few minutes in the future.')
    raise SystemExit(0)

print(f'{"Candidate":22} {"Slot":18} {"In":>8}  Reminder')
print('-' * 72)

for r in rows:
    try:
        slot_dt = datetime.strptime(
            f'{r["date"]} {r["start_time"]}', '%d-%m-%Y %H:%M')
    except ValueError:
        continue

    delta_min = int(round((slot_dt - now).total_seconds() / 60))
    when = f'{delta_min} min' if delta_min >= 0 else f'{-delta_min} ago'

    if r['reminder_status'] == 'sent':
        state = 'SENT'
    elif r['reminder_status'] == 'failed':
        state = f'FAILED - {r["reminder_error"]}'
    elif r['reminder_status'] == 'skipped':
        state = f'SKIPPED - {r["reminder_error"]}'
    elif r['reminder_status']:
        state = r['reminder_status'].upper()
    elif -grace <= delta_min <= lead:
        state = 'DUE NOW -- run the worker'
    elif delta_min > lead:
        state = f'waiting (due in {delta_min - lead} min)'
    else:
        state = 'missed (slot too far past)'

    name = (r['name'] or '')[:20]
    print(f'{name:22} {r["date"]} {r["start_time"]:5} {when:>8}  {state}')

print()
print('To send what is due now:   python reminder_worker.py --once')
print('To preview without sending: python reminder_worker.py --once --dry-run')
