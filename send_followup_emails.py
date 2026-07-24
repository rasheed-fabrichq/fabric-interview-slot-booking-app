"""
Send the KOSMIC Round 1 follow-up invitation to candidates who have not
booked a slot yet.

Everything is configured in the CONFIG block below -- edit it, then run:

    python send_followup_emails.py

The input CSV is the export from Admin > Candidates > "Export Non-Booked"
(/admin/export-pending), which has the columns:

    Name, Email, Candidate ID, Status, Slot Booking Link

SEND is False by default, which makes the run a dry run: it validates
every row, writes a rendered preview, and reports exactly who would be
mailed without sending anything. Set SEND = True to send for real.

Every successful send is appended to SENT_LOG. Re-running skips anyone
already in that log, so an interrupted run can be resumed without
mailing anyone twice.
"""
# dotenv MUST be loaded before email_utils, which reads os.environ for
# the SES credentials.
from dotenv import load_dotenv
load_dotenv()

import csv
import os
import re
import sys
import time
from datetime import datetime

from email_utils import send_raw_email


# ---------------------------------------------------------------------
# CONFIG -- edit these
# ---------------------------------------------------------------------

# The CSV exported from Admin > Candidates > Export Non-Booked.
CSV_PATH = os.path.expanduser('~/Downloads/candidates_pending_clicked (1).csv')

# False = dry run, nothing is sent. Set to True to actually send.
SEND = False

SUBJECT = 'Reminder: Book Your KOSMIC Round 1 AI Interaction Slot'

# Redirect every email to this address instead of the candidate, for a
# live test. Set to None for the real run.
#   e.g. TEST_EMAIL = 'hariom@fabrichq.ai'
TEST_EMAIL = None

# Only send to candidates with this status: 'pending', 'clicked', or
# None for both. The two groups differ -- 'clicked' candidates already
# opened their link and stopped -- so you may want to run them
# separately with different SUBJECT wording.
STATUS_FILTER = None

# Send to at most this many candidates, for a cautious first batch.
# None = no limit.
LIMIT = None

# Send only to these addresses from the CSV, for a live test with a real
# candidate's content. Empty list = no filter.
#   e.g. ONLY_EMAILS = ['someone@example.com']
ONLY_EMAILS = []

# Copied on every email. Visible to the candidate in the Cc header, so
# each of the 119 recipients sees these addresses -- and each of these
# addresses receives one copy per candidate. Set to [] for no CC.
CC_EMAILS = ['support@fabrichq.ai', 'abdul.rasheed@fabrichq.ai']

# Seconds to wait between sends, to stay under the SES rate limit.
DELAY_SECONDS = 0.5

# Progress log of successful sends. Re-running skips addresses listed
# here, which is what makes an interrupted run safe to resume.
SENT_LOG = 'followup_sent.log'

# ---------------------------------------------------------------------


TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'email_templates', 'kosmic_followup.html')

PREVIEW_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'followup_preview.html')

REQUIRED_COLUMNS = ('Name', 'Email', 'Candidate ID', 'Slot Booking Link')

# Deliberately loose -- SES is the real authority on deliverability. This
# only catches blank cells and obvious paste damage.
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def load_template():
    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        return f.read()


def normalize_link(link, candidate_id):
    """Return the https booking link for a candidate.

    The export builds its link from request.host_url, so a CSV pulled from
    a local or plain-http session carries an http:// link that would reach
    candidates as an insecure URL.
    """
    link = (link or '').strip()
    if not link:
        return f'https://slot-booking.fabrichq.ai/book?candidate_id={candidate_id}'
    if link.startswith('http://'):
        link = 'https://' + link[len('http://'):]
    return link


def read_candidates(csv_path, status_filter=None):
    """Parse the export into (candidates, skipped) lists.

    Rows missing a name, email or candidate id are collected as skipped
    rather than silently dropped, so the dry run can surface them.
    """
    candidates, skipped = [], []

    with open(csv_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)

        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(
                f"ERROR: {csv_path} is missing required column(s): {', '.join(missing)}\n"
                f"Found: {', '.join(reader.fieldnames or [])}\n"
                f"Expected the export from Admin > Candidates > Export Non-Booked.")

        seen_emails = set()

        for row_num, row in enumerate(reader, start=2):  # row 1 is the header
            name = (row.get('Name') or '').strip()
            email = (row.get('Email') or '').strip()
            candidate_id = (row.get('Candidate ID') or '').strip()
            status = (row.get('Status') or '').strip().lower()

            if not name or not email or not candidate_id:
                skipped.append((row_num, email or '(no email)', 'missing name, email or candidate id'))
                continue

            if not EMAIL_RE.match(email):
                skipped.append((row_num, email, 'malformed email address'))
                continue

            if status_filter and status != status_filter:
                continue

            # The same person can appear twice if they applied more than
            # once; one reminder each is enough.
            key = email.lower()
            if key in seen_emails:
                skipped.append((row_num, email, 'duplicate email, already included above'))
                continue
            seen_emails.add(key)

            candidates.append({
                'name': name,
                'email': email,
                'candidate_id': candidate_id,
                'status': status,
                'link': normalize_link(row.get('Slot Booking Link'), candidate_id),
                'row': row_num,
            })

    return candidates, skipped


def render(template, name, link):
    """Substitute a candidate into the template.

    A renamed placeholder would otherwise reach the candidate as literal
    "{{...}}" text, so an unsubstituted leftover is a hard failure.
    """
    html = template.replace('{{Candidate Name}}', name).replace('{{Registration Link}}', link)

    leftover = re.findall(r'{{[^}]+}}', html)
    if leftover:
        raise SystemExit(
            f"ERROR: template has unsubstituted placeholders: {leftover}\n"
            f"Check {TEMPLATE_PATH}")
    return html


def load_sent_log(path):
    """Emails already sent in a previous run, so a resume skips them."""
    if not os.path.exists(path):
        return set()
    sent = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) >= 2 and parts[1]:
                sent.add(parts[1].lower())
    return sent


def record_sent(path, email, candidate_id):
    with open(path, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')}\t{email}\t{candidate_id}\n")


def main():
    if not os.path.exists(CSV_PATH):
        raise SystemExit(f"ERROR: file not found: {CSV_PATH}\nCheck CSV_PATH at the top of this file.")

    template = load_template()
    candidates, skipped = read_candidates(CSV_PATH, STATUS_FILTER)

    if ONLY_EMAILS:
        wanted = {e.strip().lower() for e in ONLY_EMAILS}
        candidates = [c for c in candidates if c['email'].lower() in wanted]
        for m in wanted - {c['email'].lower() for c in candidates}:
            print(f"  WARNING: ONLY_EMAILS entry {m} is not in the CSV")

    # Resuming: anyone already mailed in a previous run is dropped here,
    # which is what makes a re-run safe after an interruption.
    already_sent = load_sent_log(SENT_LOG)
    resumed = [c for c in candidates if c['email'].lower() in already_sent]
    candidates = [c for c in candidates if c['email'].lower() not in already_sent]

    if LIMIT:
        candidates = candidates[:LIMIT]

    print(f"\nCSV:        {CSV_PATH}")
    print(f"Template:   {TEMPLATE_PATH}")
    print(f"Subject:    {SUBJECT}")
    if CC_EMAILS:
        print(f"CC:         {', '.join(CC_EMAILS)}  (on every email)")
    print(f"To send:    {len(candidates)} candidate(s)")
    if resumed:
        print(f"Skipped:    {len(resumed)} already in {SENT_LOG} from a previous run")
    if skipped:
        print(f"Bad rows:   {len(skipped)} skipped")
        for row_num, email, reason in skipped[:20]:
            print(f"              row {row_num}: {email} -- {reason}")
        if len(skipped) > 20:
            print(f"              ... and {len(skipped) - 20} more")
    if TEST_EMAIL:
        print(f"TEST MODE:  every email redirected to {TEST_EMAIL}")

    if not candidates:
        print("\nNothing to send.\n")
        return

    by_status = {}
    for c in candidates:
        by_status[c['status']] = by_status.get(c['status'], 0) + 1
    mix = ', '.join(f"{k or 'unknown'}={v}" for k, v in sorted(by_status.items()))
    print(f"Status mix: {mix}")

    if not SEND:
        print("\n--- DRY RUN (no email sent). Set SEND = True to send. ---\n")
        for c in candidates[:10]:
            print(f"  {c['name']} <{c['email']}>  [{c['status']}]")
            print(f"      {c['link']}")
        if len(candidates) > 10:
            print(f"  ... and {len(candidates) - 10} more")

        # Render one email so a broken template fails here, not mid-send.
        with open(PREVIEW_PATH, 'w', encoding='utf-8') as f:
            f.write(render(template, candidates[0]['name'], candidates[0]['link']))
        print(f"\nPreview for {candidates[0]['name']} written to:\n  {PREVIEW_PATH}")
        print("Open it in a browser to check the content and the link.\n")
        return

    print(f"\n--- SENDING to {len(candidates)} candidate(s) ---\n")

    sent = 0
    failures = []

    for i, c in enumerate(candidates, start=1):
        html = render(template, c['name'], c['link'])
        recipient = TEST_EMAIL or c['email']

        print(f"[{i}/{len(candidates)}] {c['name']} <{recipient}>")
        ok, err = send_raw_email(
            mail_to=recipient,
            subject=SUBJECT,
            html_content=html,
            reply_to=[os.environ.get('EMAIL_REPLY_TO', 'support@fabrichq.ai')],
            company_name=os.environ.get('EMAIL_COMPANY_NAME', 'Kearney'),
            cc=CC_EMAILS,
        )

        if ok:
            sent += 1
            # Not logged in test mode -- the candidate never got it, so a
            # later real run must not skip them.
            if not TEST_EMAIL:
                record_sent(SENT_LOG, c['email'], c['candidate_id'])
        else:
            failures.append((c['name'], c['email'], err))
            print(f"      FAILED: {err}")

        if DELAY_SECONDS and i < len(candidates):
            time.sleep(DELAY_SECONDS)

    print(f"\n--- DONE ---")
    print(f"Sent:   {sent}")
    print(f"Failed: {len(failures)}")
    for name, email, err in failures:
        print(f"  {name} <{email}>: {err}")
    if not TEST_EMAIL and sent:
        print(f"\nProgress logged to {SENT_LOG}. Re-running skips these candidates.")
    if failures:
        sys.exit(1)


if __name__ == '__main__':
    main()
