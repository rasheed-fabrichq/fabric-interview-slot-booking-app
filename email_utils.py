"""
Email utility for sending booking confirmation emails via AWS SES.
"""
import boto3
import logging
import os
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

def _cfg(key, default=''):
    """Read a config value from env at call time (after dotenv is loaded)."""
    return os.environ.get(key, default)


CONFIRMATION_EMAIL_TEMPLATE = """<!DOCTYPE html>
<html lang="en" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="x-apple-disable-message-reformatting">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="color-scheme" content="light dark">
    <meta name="supported-color-schemes" content="light dark">
    <title>CONFIRMED: Your AI Interview Link & Details - Meesho</title>
    <!--[if mso]>
    <xml>
        <o:OfficeDocumentSettings>
            <o:AllowPNG/>
            <o:PixelsPerInch>96</o:PixelsPerInch>
        </o:OfficeDocumentSettings>
    </xml>
    <![endif]-->
    <style>
        :root {
            color-scheme: light dark;
            supported-color-schemes: light dark;
        }
        body {
            margin: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            background-color: #FDF4F9 !important; 
            color: #2D2D2F !important;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            -webkit-font-smoothing: antialiased;
        }
        .outer-wrapper {
            background-color: #FDF4F9 !important;
        }
        .forced-white-bg {
            background-color: #FFFFFF !important;
        }
        .content-cell {
            padding: 10px 45px 40px 45px !important;
        }
        .label {
            font-weight: 700;
            color: #662237;
        }
        .info-box {
            background-color: #FFF9FC !important;
            border: 1px solid #F1E1EB;
            border-radius: 12px;
            padding: 20px;
            margin-top: 10px;
        }
        .action-card {
            margin-top: 30px;
            border: 1px solid #F1E1EB !important;
            background-color: #FAFAFA !important;
            border-radius: 4px;
        }
        .action-sidebar {
            padding: 18px;
            border-left: 6px solid #662237 !important;
        }
        .checklist-item {
            margin-bottom: 8px;
            font-size: 13px;
            color: #444444;
        }
        .proctor-box {
            background-color: #FFF5F5 !important;
            border: 1px solid #FED7D7;
            border-radius: 8px;
            padding: 16px;
            margin: 25px 0;
        }
        @media screen and (max-width: 600px) {
            .content-cell { padding: 10px 20px 30px 20px !important; }
            .container-table { width: 95% !important; }
            .header-padding { padding: 40px 20px 15px 20px !important; }
        }
    </style>
</head>
<body style="background-color: #FDF4F9; margin: 0; padding: 0;">
    <table width="100%" border="0" cellspacing="0" cellpadding="0" role="presentation" class="outer-wrapper" style="background-color: #FDF4F9 !important;">
        <tr>
            <td align="center" style="padding: 40px 0;">
                
                <table align="center" cellpadding="0" cellspacing="0" border="0" role="presentation" class="container-table" style="width: 100%; max-width: 600px; margin: 0 auto; border-collapse: separate;">
                    <tr>
                        <td style="padding: 1px; background-color: #EEDBE6; border-radius: 16px;">
                            
                            <!-- Main Email Body -->
                            <table class="forced-white-bg" align="center" cellpadding="0" cellspacing="0" border="0" role="presentation" style="width: 100%; background-color: #FFFFFF !important; border-collapse: separate; border-radius: 15px; overflow: hidden;">
                                
                                <!-- Header Logo & Divider -->
                                <tr>
                                    <td class="header-padding" style="padding: 40px 45px 15px 45px;">
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                            <tr>
                                                <td align="left">
                                                    <img src="https://www.meesho.io/img/meesho-logo.png" alt="Meesho" height="38" style="display: block; border: 0; height: 38px; width: auto;">
                                                </td>
                                            </tr>
                                            <tr>
                                                <td style="padding-top: 25px;">
                                                    <div style="border-top: 2px dotted #E5E7EB; width: 100%; height: 1px;"></div>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                                <!-- Main Content -->
                                <tr>
                                    <td class="content-cell">
                                        <p style="font-size: 16px; margin-bottom: 20px;">Hi <span class="label">{{Candidate Name}}</span>,</p>
                                        
                                        <p style="font-size: 15px; line-height: 1.6; color: #444444 !important; margin-bottom: 24px;">
                                            Great news! Your AI Interview slot has been <strong>successfully confirmed</strong>. Please find your unique interview link and details below.
                                        </p>
                                        <!-- Session Details Box -->
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" class="info-box" style="margin-bottom: 24px;">
                                            <tr>
                                                <td>
                                                    <p style="margin: 0 0 12px 0; font-size: 14px; font-weight: 700; color: #662237; text-transform: uppercase; letter-spacing: 1px;">Your Session Details</p>
                                                    <p style="margin: 0; font-size: 15px; color: #2D2D2F;">
                                                        <strong>Date:</strong> 14th March, Saturday, 2026
                                                    </p>
                                                    <p style="margin: 8px 0; font-size: 15px; color: #2D2D2F;">
                                                        <strong>Time:</strong> {{Start Time}} - {{End Time}} IST
                                                    </p>
                                                    <p style="margin: 0; font-size: 15px; color: #2D2D2F;">
                                                        <strong>Duration:</strong> 40 Minutes
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                        <!-- UNIQUE LINK SECTION -->
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" class="action-card">
                                            <tr>
                                                <td class="action-sidebar">
                                                    <span style="color: #662237 !important; font-weight: 700; text-transform: uppercase; font-size: 11px; letter-spacing: 1.5px; display: block; margin-bottom: 12px;">YOUR UNIQUE INTERVIEW LINK</span>
                                                    
                                                    <div style="font-size: 14px; color: #444444 !important; line-height: 1.7;">
                                                        <p style="margin: 0 0 15px 0;">This link will only be active during your reserved window. Joining outside your scheduled time is not permitted.</p>
                                                        
                                                        <table cellpadding="0" cellspacing="0" border="0" role="presentation" style="margin: 10px 0 20px 0;">
                                                            <tr>
                                                                <td align="center" style="background-color: #662237 !important; padding: 14px 32px; border-radius: 4px;">
                                                                    <a href="{{Unique Interview Link}}" style="color: #FFFFFF !important; font-family: Arial, sans-serif; font-weight: 700; text-transform: uppercase; text-decoration: none; font-size: 13px; display: block; letter-spacing: 1px; white-space: nowrap;">
                                                                        Join AI Interview &nbsp; ›
                                                                    </a>
                                                                </td>
                                                            </tr>
                                                        </table>
                                                        
                                                        <p style="margin: 0; font-size: 12px; color: #86868B;"><strong>Note:</strong> Do not share this link with anyone. The session is auto-initiated.</p>
                                                    </div>
                                                </td>
                                            </tr>
                                        </table>
                                        <!-- Quick Checklist -->
                                        <div style="margin-top: 30px; padding: 0 5px;">
                                            <p style="font-size: 15px; font-weight: 700; color: #2D2D2F; margin-bottom: 12px;">Quick Checklist - Before You Join</p>
                                            <div class="checklist-item">• Use a <strong>laptop or desktop</strong> for the best experience.</div>
                                            <div class="checklist-item">• Make sure to <strong>connect your laptop to a power source</strong>.</div>
                                            <div class="checklist-item">• Ensure a strong, stable internet connection.</div>
                                            <div class="checklist-item">• Test your camera and microphone in advance.</div>
                                            <div class="checklist-item">• Join from a <strong>quiet, distraction-free environment</strong>.</div>
                                            <div class="checklist-item">• Join <strong>2-3 minutes before</strong> your start time - the session begins promptly.</div>
                                        </div>
                                        <!-- Proctoring Note Section -->
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation" class="proctor-box">
                                            <tr>
                                                <td>
                                                    <p style="margin: 0 0 8px 0; font-size: 14px; font-weight: 700; color: #C53030; text-transform: uppercase; letter-spacing: 0.5px;">PLEASE NOTE</p>
                                                    <p style="margin: 0; font-size: 14px; line-height: 1.5; color: #2D2D2F;">
                                                        This session is strictly monitored. Our system checks for AI usage, help from others, and any tab switching. Please be aware that <strong>40% of candidates</strong> are usually disqualified for not following these rules or trying to cheat.
                                                    </p>
                                                </td>
                                            </tr>
                                        </table>
                                        <!-- Verbatim Technical Issues Section -->
                                        <p style="font-size: 14px; line-height: 1.6; color: #444444; margin-top: 10px; margin-bottom: 15px;">
                                            <strong>Need Help?</strong> If you experience any technical issues at the time of joining, contact us at <span style="color: #662237; font-weight: 600;">support@fabrichq.ai</span>. Do not wait - time lost due to technical delays will not be compensated.
                                        </p>
                                        <!-- FAQ Document Section -->
                                        <p style="font-size: 14px; line-height: 1.6; color: #444444; margin-bottom: 20px;">
                                            You can also refer the FAQ document to troubleshoot:
                                            <br>
                                            <span style="font-size: 16px; line-height: 10px; vertical-align: middle; color: #662237; font-weight: 700; padding-right: 4px;">&#x27A1;</span>
                                            <a href="https://drive.google.com/file/d/1vnwxfTCFFMB4XO_c33_OiC8yL_Trp8Fg/view" style="color: #662237; font-weight: 600; text-decoration: underline;">AI Interview FAQ Document</a>.
                                        </p>
                                        <p style="font-size: 14px; color: #2D2D2F; font-weight: 600;">
                                            We wish you the very best. Give it your all!
                                        </p>
                                    </td>
                                </tr>
                                <!-- Footer -->
                                <tr>
                                    <td style="padding: 30px 45px; background-color: #FAFAFA !important; border-top: 1px solid #EEEEEE !important;">
                                        <p style="color: #999999 !important; font-size: 13px; margin-bottom: 4px;">Best regards,</p>
                                        <p style="color: #662237 !important; font-weight: 600; margin: 0; font-size: 16px; letter-spacing: 0.5px;">Campus Hiring Team - Meesho</p>
                                        
                                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top: 20px;">
                                            <tr>
                                                <td style="font-size: 11px; color: #BBBBBB !important; text-transform: uppercase; letter-spacing: 0.5px;">
                                                    Support: <span style="color: #662237 !important; text-decoration: underline;">support@fabrichq.ai</span>
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>"""


def send_raw_email(mail_to, subject, html_content, reply_to=None, company_name=None):
    """
    Send an HTML email via AWS SES using raw MIME.

    Returns: (success: bool, error_message: str | None)
    """
    access_key = _cfg('AWS_SES_ACCESS_KEY_ID')
    secret_key = _cfg('AWS_SES_SECRET_ACCESS_KEY')

    if not access_key or not secret_key:
        logger.error("AWS SES credentials not configured. Set AWS_SES_ACCESS_KEY_ID and AWS_SES_SECRET_ACCESS_KEY env vars.")
        return False, "AWS SES credentials not configured"

    try:
        client = boto3.client(
            "ses",
            region_name=_cfg('AWS_SES_REGION', 'ap-south-1'),
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        sender_name = f"Team {company_name}" if company_name else f"Team {_cfg('EMAIL_COMPANY_NAME', 'Fabric')}"
        sender = _cfg('AWS_SES_EMAIL', 'noreply@fabrichq.ai')

        msg = MIMEMultipart("mixed")
        msg["From"] = f"{sender_name} <{sender}>"
        msg["To"] = mail_to
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
            Destinations=[mail_to],
            RawMessage={"Data": msg.as_string()},
        )
        logger.info(f"Email sent to {mail_to}. MessageId: {response['MessageId']}")
        return True, None

    except ClientError as e:
        error_msg = e.response["Error"]["Message"]
        logger.error(f"SES ClientError sending to {mail_to}: {error_msg}")
        return False, error_msg
    except Exception as e:
        logger.error(f"Unexpected error sending email to {mail_to}: {str(e)}")
        return False, str(e)


def send_booking_confirmation(candidate_name, candidate_email, job_name,
                               slot_date, day_of_week, start_time, end_time,
                               interview_link_with_expiry, company_name=None):
    """
    Send a booking confirmation email to a candidate after they book a slot.

    Returns: (success: bool, error_message: str | None)
    """
    effective_company = company_name or _cfg('EMAIL_COMPANY_NAME', 'Fabric')
    reply_to_addr = _cfg('EMAIL_REPLY_TO', 'support@fabrichq.ai')
    subject = f"Interview With Meesho Confirmed – {slot_date} {start_time} IST"

    html_content = (CONFIRMATION_EMAIL_TEMPLATE
        .replace('{{Candidate Name}}', candidate_name)
        .replace('{{Slot Date}}', f'{slot_date} ({day_of_week})')
        .replace('{{Start Time}}', start_time)
        .replace('{{End Time}}', end_time)
        .replace('{{Unique Interview Link}}', interview_link_with_expiry)
    )

    return send_raw_email(
        mail_to=candidate_email,
        subject=subject,
        html_content=html_content,
        reply_to=[reply_to_addr],
        company_name=effective_company,
    )
