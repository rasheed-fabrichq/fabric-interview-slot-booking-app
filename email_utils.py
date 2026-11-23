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


# The confirmation email is edited in Admin > Email Templates and stored
# in the settings table. Until one is saved there, the built-in default
# is used: the file named by CONFIRMATION_EMAIL_TEMPLATE in .env (in
# email_templates/) with CONFIRMATION_EMAIL_SUBJECT, else the generic
# default below.
TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'email_templates')
DEFAULT_TEMPLATE_FILE = 'sprinto_slot_confirmed.html'
DEFAULT_SUBJECT = ('Sprinto – Your Case Study Interview Assessment Details | '
                   '{{Slot Date}}, {{Start Time}} IST')

# Settings-table keys for the saved template.
SUBJECT_SETTING = 'confirmation_email_subject'
BODY_SETTING = 'confirmation_email_body'

# Every placeholder the confirmation email can use, with help text for
# the editor. Anything else is rejected on save.
PLACEHOLDERS = {
    '{{Candidate Name}}': "Candidate's full name",
    '{{Candidate Email}}': "Candidate's email address",
    '{{Job Name}}': 'Job the candidate booked, as named in Admin > Jobs',
    '{{Company Name}}': 'EMAIL_COMPANY_NAME from .env',
    '{{Slot Date}}': 'Day and date, e.g. Tuesday, 24-11-2026',
    '{{Date}}': 'Date only, e.g. 24-11-2026',
    '{{Day}}': 'Weekday, e.g. Tuesday',
    '{{Start Time}}': 'Slot start, e.g. 10:00 AM',
    '{{End Time}}': 'Slot end, e.g. 10:30 AM',
    '{{Duration}}': 'Slot length, e.g. 30 Minutes',
    '{{Assessment Link}}': "The candidate's interview link, valid for their slot",
    '{{Unique Interview Link}}': 'Same as {{Assessment Link}}',
    '{{Support Email}}': 'EMAIL_SUPPORT from .env, else EMAIL_REPLY_TO',
}

# Values a preview or test email is rendered with.
SAMPLE_VALUES = {
    'candidate_name': 'Priya Sharma',
    'candidate_email': 'priya.sharma@example.com',
    'job_name': 'Backend Engineer',
    'slot_date': '24-11-2026',
    'day_of_week': 'Tuesday',
    'start_time': '10:00 AM',
    'end_time': '10:30 AM',
    'interview_link': ('https://app.fabrichq.ai/jobs/sample/?candidate_id=sample'
                       '&start_time=2026-11-24T10:00&end_time=2026-11-24T10:30'),
    'duration_minutes': 30,
}


def get_default_template():
    """The built-in subject and body, used until one is saved."""
    filename = _cfg('CONFIRMATION_EMAIL_TEMPLATE') or DEFAULT_TEMPLATE_FILE
    with open(os.path.join(TEMPLATE_DIR, filename), encoding='utf-8') as f:
        body = f.read()
    return {'subject': _cfg('CONFIRMATION_EMAIL_SUBJECT') or DEFAULT_SUBJECT,
            'body': body}


def get_confirmation_template():
    """The template to send: the saved one, else the default.

    Read at send time, so a save in the admin panel applies to the next
    email without a restart.
    """
    from database import get_setting
    subject = get_setting(SUBJECT_SETTING)
    body = get_setting(BODY_SETTING)
    if subject and body:
        return {'subject': subject, 'body': body, 'is_custom': True}
    template = get_default_template()
    template['is_custom'] = False
    return template


def find_unknown_placeholders(text):
    """Placeholders in text that would not be filled in."""
    return [token for token in sorted(set(re.findall(r'{{[^}]+}}', text or '')))
            if token not in PLACEHOLDERS]


def _sender_settings():
    reply_to = _cfg('EMAIL_REPLY_TO', 'support@fabrichq.ai')
    return {
        'company_name': _cfg('EMAIL_COMPANY_NAME', 'Fabric'),
        'reply_to': reply_to,
        'support_email': _cfg('EMAIL_SUPPORT', '') or reply_to,
    }


def build_values(candidate_name, candidate_email, job_name, slot_date,
                 day_of_week, start_time, end_time, interview_link,
                 duration_minutes=None, company_name=None):
    """Placeholder values for one confirmation email."""
    sender = _sender_settings()
    return {
        '{{Candidate Name}}': candidate_name,
        '{{Candidate Email}}': candidate_email,
        '{{Company Name}}': company_name or sender['company_name'],
        '{{Job Name}}': job_name,
        '{{Slot Date}}': f'{day_of_week}, {slot_date}',
        '{{Date}}': slot_date,
        '{{Day}}': day_of_week,
        '{{Start Time}}': start_time,
        '{{End Time}}': end_time,
        '{{Duration}}': f'{duration_minutes} Minutes' if duration_minutes else '',
        '{{Assessment Link}}': interview_link,
        '{{Unique Interview Link}}': interview_link,
        '{{Support Email}}': sender['support_email'],
    }


def _fill(text, values, escape=False):
    """Substitute placeholders and check none were missed.

    A misspelt placeholder would otherwise reach the candidate as literal
    "{{...}}" text -- and if it were the link, with no way to join at
    all. escape HTML-escapes values, for the body: a name with "&" or "<"
    would otherwise break the markup. Returns (text, error).
    """
    for token, value in values.items():
        value = str(value) if value else ''
        text = text.replace(token, html.escape(value) if escape else value)
    leftover = re.findall(r'{{[^}]+}}', text)
    if leftover:
        return None, f"Email template has unknown placeholders: {leftover}"
    return text, None


def render_email(template, values):
    """Render a template's subject and body. Returns (subject, html, error)."""
    subject, error = _fill(template['subject'], values)
    if error:
        return None, None, error
    body, error = _fill(template['body'], values, escape=True)
    if error:
        return None, None, error
    return subject, body, None


def render_sample(template):
    """Render a template with sample candidate data."""
    v = SAMPLE_VALUES
    values = build_values(v['candidate_name'], v['candidate_email'],
                          v['job_name'], v['slot_date'], v['day_of_week'],
                          v['start_time'], v['end_time'], v['interview_link'],
                          v['duration_minutes'])
    return render_email(template, values)


def send_test_email(to_address, template):
    """Send a template, filled with sample data, to an admin."""
    subject, body, error = render_sample(template)
    if error:
        return False, error
    sender = _sender_settings()
    return send_raw_email(
        mail_to=to_address,
        subject=f'[TEST] {subject}',
        html_content=body,
        reply_to=[sender['reply_to']],
        company_name=sender['company_name'],
    )


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
                               interview_link_with_expiry, company_name=None,
                               duration_minutes=None):
    """
    Send a booking confirmation email to a candidate after they book a slot.

    Uses the template from Admin > Email Templates, else the default.

    Returns: (success: bool, error_message: str | None)
    """
    values = build_values(candidate_name, candidate_email, job_name,
                          slot_date, day_of_week, start_time, end_time,
                          interview_link_with_expiry, duration_minutes,
                          company_name)
    subject, html_content, error = render_email(
        get_confirmation_template(), values)
    if error:
        logger.error(error)
        print(f"[SES] ERROR: {error}")
        return False, error

    sender = _sender_settings()
    return send_raw_email(
        mail_to=candidate_email,
        subject=subject,
        html_content=html_content,
        reply_to=[sender['reply_to']],
        company_name=values['{{Company Name}}'],
    )
