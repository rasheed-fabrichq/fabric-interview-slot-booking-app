"""
Email utility for sending booking confirmation emails via AWS SES.
"""
import boto3
import html
import logging
import os
import re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def _cfg(key, default=''):
    """Read a config value from env at call time (after dotenv is loaded)."""
    return os.environ.get(key, default)


TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'email_templates')

# What a job is sent when it has no template of its own. Company name,
# support address and links are placeholders, so these defaults carry no
# client branding.
DEFAULT_TEMPLATES = {
    'confirmation': {
        'file': 'default_slot_confirmed.html',
        'subject': ('{{Company Name}}: Your AI Interview is Confirmed '
                    '\u2013 {{Date}}, {{Start Time}} IST'),
    },
    'reminder': {
        'file': 'default_slot_reminder.html',
        'subject': ('Reminder: Your {{Company Name}} AI Interview starts '
                    'at {{Start Time}} IST ({{Date}})'),
    },
}

# Every placeholder a template may use, with the help text the admin
# editor shows. Templates are checked against this on save, so a typo
# is caught there rather than when a candidate's email fails to send.
PLACEHOLDERS = {
    '{{Candidate Name}}': "Candidate's full name",
    '{{Candidate Email}}': "Candidate's email address",
    '{{Job Name}}': 'Job title as configured',
    '{{Company Name}}': "The job's company name",
    '{{Slot Date}}': 'Day and date, e.g. Thursday, 20-11-2025',
    '{{Date}}': 'Date only, e.g. 20-11-2025',
    '{{Day}}': 'Weekday, e.g. Thursday',
    '{{Start Time}}': 'Slot start, e.g. 10:00 AM',
    '{{End Time}}': 'Slot end, e.g. 10:30 AM',
    '{{Duration}}': 'Slot length, e.g. 30 Minutes',
    '{{Assessment Link}}': "The candidate's interview link for this slot",
    '{{Unique Interview Link}}': 'Same as {{Assessment Link}}',
    '{{FAQ Document Link}}': "The job's FAQ link",
    '{{Support Email}}': "The job's support email address",
    '{{Minutes Until}}': 'Reminder only: minutes until the slot starts',
}

# Placeholders that only have a value for some kinds.
KIND_ONLY_PLACEHOLDERS = {'{{Minutes Until}}': 'reminder'}

DEFAULT_SUPPORT_EMAIL = 'support@fabrichq.ai'

# Candidate-facing FAQ, used when a job does not set its own. Override
# with FAQ_DOCUMENT_LINK in .env.
DEFAULT_FAQ_LINK = (
    'https://docs.google.com/document/d/'
    '1xVZV7QoXUbp6csqoBzrn2Xd42e2n4F5edm3t6q-_hxs/edit?usp=sharing')


def _load_template_file(filename):
    with open(os.path.join(TEMPLATE_DIR, filename), encoding='utf-8') as f:
        return f.read()


def get_default_template(kind):
    """The built-in subject and body for a kind."""
    default = DEFAULT_TEMPLATES[kind]
    return {'subject': default['subject'],
            'body': _load_template_file(default['file'])}


def get_template(job_id, kind):
    """The job's own template for a kind, else the default.

    Read at send time, so an edit in the admin panel applies to the
    next email without restarting the app or the reminder worker.
    """
    from database import get_job_email_template
    custom = get_job_email_template(job_id, kind) if job_id else None
    if custom:
        return {'subject': custom['subject'], 'body': custom['body'],
                'is_custom': True}
    template = get_default_template(kind)
    template['is_custom'] = False
    return template


def _split_addresses(raw):
    return [addr.strip() for addr in (raw or '').split(',') if addr.strip()]


def get_job_branding(job_id):
    """Resolved sender and branding values for a job.

    Each value is the job's own setting if it has one, else the .env
    default, else a built-in default -- so a job set up with nothing
    still sends a complete email.
    """
    from database import get_job_communication
    job = (get_job_communication(job_id) if job_id else None) or {}

    return {
        'company_name': (job.get('company_name')
                         or _cfg('EMAIL_COMPANY_NAME', 'Fabric')),
        'reply_to': (job.get('email_reply_to')
                     or _cfg('EMAIL_REPLY_TO', DEFAULT_SUPPORT_EMAIL)),
        # CC falls back to env only when the job has never set one; a
        # job can't clear an env CC except by setting its own.
        'cc': _split_addresses(job.get('email_cc')
                               or _cfg('EMAIL_CONFIRMATION_CC', '')),
        'support_email': (job.get('support_email')
                          or _cfg('EMAIL_REPLY_TO', DEFAULT_SUPPORT_EMAIL)),
        'faq_link': (job.get('faq_link')
                     or _cfg('FAQ_DOCUMENT_LINK', DEFAULT_FAQ_LINK)),
    }


def find_unknown_placeholders(text, kind):
    """Placeholders in text that would not be filled for this kind."""
    unknown = []
    for token in sorted(set(re.findall(r'{{[^}]+}}', text or ''))):
        only_for = KIND_ONLY_PLACEHOLDERS.get(token)
        if token not in PLACEHOLDERS or (only_for and only_for != kind):
            unknown.append(token)
    return unknown


def build_substitutions(kind, branding, candidate_name, candidate_email,
                        job_name, slot_date, day_of_week, start_time,
                        end_time, interview_link, duration_minutes=None,
                        minutes_until=None):
    """Placeholder values for one email."""
    values = {
        '{{Candidate Name}}': candidate_name,
        '{{Candidate Email}}': candidate_email,
        '{{Job Name}}': job_name,
        '{{Company Name}}': branding['company_name'],
        '{{Slot Date}}': f'{day_of_week}, {slot_date}',
        '{{Date}}': slot_date,
        '{{Day}}': day_of_week,
        '{{Start Time}}': start_time,
        '{{End Time}}': end_time,
        '{{Duration}}': (f'{duration_minutes} Minutes'
                         if duration_minutes else ''),
        '{{Assessment Link}}': interview_link,
        '{{Unique Interview Link}}': interview_link,
        '{{FAQ Document Link}}': branding['faq_link'],
        '{{Support Email}}': branding['support_email'],
    }
    if kind == 'reminder':
        values['{{Minutes Until}}'] = str(minutes_until or 0)
    return values


def _render(template, substitutions, escape=False):
    """Substitute {{Placeholder}} tokens and verify none were missed.

    A renamed placeholder in the template would otherwise reach the
    candidate as literal "{{...}}" text -- and if it were the link, with
    no way to join at all. Returns (text, error).

    escape HTML-escapes the values, for bodies: a company or candidate
    name with "&" or "<" would otherwise break the markup.
    """
    rendered = template
    for token, value in substitutions.items():
        value = str(value) if value else ''
        rendered = rendered.replace(
            token, html.escape(value) if escape else value)

    leftover = re.findall(r'{{[^}]+}}', rendered)
    if leftover:
        msg = f"Email template has unsubstituted placeholders: {leftover}"
        logger.error(msg)
        print(f"[SES] ERROR: {msg}")
        return None, msg
    return rendered, None


def render_email(template, substitutions):
    """Render a template's subject and body. Returns (subject, html, error)."""
    subject, error = _render(template['subject'], substitutions)
    if error:
        return None, None, error
    body, error = _render(template['body'], substitutions, escape=True)
    if error:
        return None, None, error
    return subject, body, None


# Values a preview or test email is rendered with.
SAMPLE_VALUES = {
    'candidate_name': 'Priya Sharma',
    'candidate_email': 'priya.sharma@example.com',
    'slot_date': '20-11-2026',
    'day_of_week': 'Friday',
    'start_time': '10:00 AM',
    'end_time': '10:30 AM',
    'interview_link': 'https://app.fabrichq.ai/interview/sample/?candidate_id=sample',
    'duration_minutes': 30,
    'minutes_until': 15,
}


def render_sample(job_id, job_name, kind, template=None):
    """Render a template with sample data. Returns (subject, html, error).

    template defaults to what the job would send today; pass one to
    preview unsaved edits.
    """
    template = template or get_template(job_id, kind)
    values = build_substitutions(kind, get_job_branding(job_id),
                                 job_name=job_name, **SAMPLE_VALUES)
    return render_email(template, values)


def send_test_email(job_id, job_name, kind, to_address, template=None):
    """Send a sample-data rendering of a template to an admin."""
    subject, body, error = render_sample(job_id, job_name, kind, template)
    if error:
        return False, error
    branding = get_job_branding(job_id)
    return send_raw_email(
        mail_to=to_address,
        subject=f'[TEST] {subject}',
        html_content=body,
        reply_to=[branding['reply_to']],
        company_name=branding['company_name'],
    )


# MessageId of the most recent successful send. Read immediately after
# a send via last_message_id(); it is overwritten by the next one.
_last_message_id = {'id': None}


def last_message_id():
    """SES MessageId of the last successful send, or None."""
    return _last_message_id.get('id')


def send_raw_email(mail_to, subject, html_content, reply_to=None, company_name=None,
                   cc=None):
    """
    Send an HTML email via AWS SES using raw MIME.

    cc: an address or list of addresses to copy. They are visible to the
    recipient in the Cc header and must also be listed in Destinations,
    since SES delivers to that list rather than parsing the headers.

    Returns: (success: bool, error_message: str | None)
    """
    access_key = _cfg('AWS_SES_ACCESS_KEY_ID')
    secret_key = _cfg('AWS_SES_SECRET_ACCESS_KEY')
    region = _cfg('AWS_SES_REGION', 'ap-south-1')
    sender_email = _cfg('AWS_SES_EMAIL', 'noreply@fabrichq.ai')

    print(f"[SES] Preparing to send email to={mail_to} subject='{subject}'")
    print(f"[SES] Config: region={region} sender={sender_email} access_key_set={bool(access_key)} secret_key_set={bool(secret_key)}")

    if not access_key or not secret_key:
        logger.error("AWS SES credentials not configured. Set AWS_SES_ACCESS_KEY_ID and AWS_SES_SECRET_ACCESS_KEY env vars.")
        print("[SES] ERROR: credentials missing, cannot send email")
        return False, "AWS SES credentials not configured"

    try:
        client = boto3.client(
            "ses",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        sender_name = f"Team {company_name}" if company_name else f"Team {_cfg('EMAIL_COMPANY_NAME', 'Fabric')}"
        sender = sender_email
        print(f"[SES] Sending as '{sender_name} <{sender}>'...")

        cc_list = [cc] if isinstance(cc, str) else list(cc or [])
        cc_list = [addr.strip() for addr in cc_list if addr and addr.strip()]

        msg = MIMEMultipart("mixed")
        msg["From"] = f"{sender_name} <{sender}>"
        msg["To"] = mail_to
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = subject
        if reply_to:
            if isinstance(reply_to, list):
                msg["Reply-To"] = ", ".join(reply_to)
            else:
                msg["Reply-To"] = reply_to

        msg_body = MIMEMultipart("alternative")
        html_part = MIMEText(html_content.encode("utf-8"), "html", "utf-8")
        msg_body.attach(html_part)
        msg.attach(msg_body)

        response = client.send_raw_email(
            Source=f"{sender_name} <{sender}>",
            Destinations=[mail_to] + cc_list,
            RawMessage={"Data": msg.as_string()},
        )
        print(f"[SES] Email sent successfully to {mail_to}. MessageId: {response['MessageId']}")
        logger.info(f"Email sent to {mail_to}. MessageId: {response['MessageId']}")
        # The MessageId is the only handle on a specific send -- it is
        # what an SES bounce notification refers back to, and what
        # support needs to trace one candidate's email. Recorded on the
        # last-send record rather than returned, so the (success, error)
        # contract every existing caller unpacks stays unchanged.
        _last_message_id['id'] = response['MessageId']
        return True, None

    except ClientError as e:
        error_msg = e.response["Error"]["Message"]
        logger.error(f"SES ClientError sending to {mail_to}: {error_msg}")
        print(f"[SES] ClientError sending to {mail_to}: {error_msg}")
        return False, error_msg
    except Exception as e:
        logger.error(f"Unexpected error sending email to {mail_to}: {str(e)}")
        print(f"[SES] Unexpected exception sending to {mail_to}: {e}")
        return False, str(e)


def send_booking_confirmation(candidate_name, candidate_email, job_name,
                               slot_date, day_of_week, start_time, end_time,
                               interview_link_with_expiry, job_id=None,
                               duration_minutes=None):
    """
    Send a booking confirmation email to a candidate after they book a slot.

    The subject, body, sender name, reply-to and CC all come from the
    job's configuration, falling back to the defaults.

    Returns: (success: bool, error_message: str | None)
    """
    branding = get_job_branding(job_id)
    values = build_substitutions(
        'confirmation', branding, candidate_name, candidate_email, job_name,
        slot_date, day_of_week, start_time, end_time,
        interview_link_with_expiry, duration_minutes=duration_minutes)

    subject, html_content, error = render_email(
        get_template(job_id, 'confirmation'), values)
    if error:
        return False, error

    return send_raw_email(
        mail_to=candidate_email,
        subject=subject,
        html_content=html_content,
        reply_to=[branding['reply_to']],
        company_name=branding['company_name'],
        cc=branding['cc'],
    )


def send_slot_reminder(candidate_name, candidate_email, job_name,
                       slot_date, day_of_week, start_time, end_time,
                       interview_link_with_expiry, minutes_until,
                       job_id=None, duration_minutes=None):
    """Send the shortly-before-your-slot reminder to a candidate.

    minutes_until is the rounded gap between now and the slot start, so
    the subject and heading match what the candidate actually sees
    rather than a hardcoded "15".

    Returns: (success: bool, error_message: str | None)
    """
    branding = get_job_branding(job_id)
    values = build_substitutions(
        'reminder', branding, candidate_name, candidate_email, job_name,
        slot_date, day_of_week, start_time, end_time,
        interview_link_with_expiry, duration_minutes=duration_minutes,
        minutes_until=minutes_until)

    subject, html_content, error = render_email(
        get_template(job_id, 'reminder'), values)
    if error:
        return False, error

    return send_raw_email(
        mail_to=candidate_email,
        subject=subject,
        html_content=html_content,
        reply_to=[branding['reply_to']],
        company_name=branding['company_name'],
    )
