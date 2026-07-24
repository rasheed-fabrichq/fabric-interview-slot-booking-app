"""
Email utility for sending booking confirmation emails via AWS SES.
"""
import boto3
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


# The confirmation email body lives in email_templates/ so the markup can
# be edited without touching Python. Placeholder names must match the
# substitutions in send_booking_confirmation below.
TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'email_templates', 'kosmic_slot_confirmed.html')


def _load_template():
    with open(TEMPLATE_PATH, encoding='utf-8') as f:
        return f.read()


CONFIRMATION_EMAIL_TEMPLATE = _load_template()


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

    Every candidate-visible value is substituted into the template; nothing
    about the slot is hardcoded in the HTML.

    Returns: (success: bool, error_message: str | None)
    """
    effective_company = company_name or _cfg('EMAIL_COMPANY_NAME', 'Fabric')
    reply_to_addr = _cfg('EMAIL_REPLY_TO', 'support@fabrichq.ai')
    duration_text = f'{duration_minutes} Minutes' if duration_minutes else ''
    subject = (f"CONFIRMED: Your KOSMIC AI Interaction – "
               f"{slot_date} {start_time} IST")

    html_content = CONFIRMATION_EMAIL_TEMPLATE
    for token, value in (
        ('{{Candidate Name}}', candidate_name),
        ('{{Case Study Name}}', job_name),
        ('{{Slot Date}}', f'{day_of_week}, {slot_date}'),
        ('{{Start Time}}', start_time),
        ('{{End Time}}', end_time),
        ('{{Duration}}', duration_text),
        ('{{Unique Interaction Link}}', interview_link_with_expiry),
    ):
        html_content = html_content.replace(token, value)

    # A renamed placeholder in the template would otherwise reach the
    # candidate as literal "{{...}}" text -- and if it were the link, with
    # no way to join at all.
    leftover = re.findall(r'{{[^}]+}}', html_content)
    if leftover:
        msg = f"Email template has unsubstituted placeholders: {leftover}"
        logger.error(msg)
        print(f"[SES] ERROR: {msg}")
        return False, msg

    return send_raw_email(
        mail_to=candidate_email,
        subject=subject,
        html_content=html_content,
        reply_to=[reply_to_addr],
        company_name=effective_company,
    )
