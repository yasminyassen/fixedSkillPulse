import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

from app.core.config import settings

logger = logging.getLogger(__name__)

SENDGRID_SMTP_HOST = "smtp.sendgrid.net"
SENDGRID_SMTP_PORT = 587
FROM_DISPLAY_NAME = "SkillPulse"
VERIFICATION_SUBJECT = "Verify your SkillPulse account"
RESET_PASSWORD_SUBJECT = "Reset Your SkillPulse Password"


class EmailDeliveryError(Exception):
    """Raised when an outbound email cannot be delivered."""


def _from_domain() -> str:
    if "@" in settings.FROM_EMAIL:
        return settings.FROM_EMAIL.split("@", 1)[1]
    return "skillpulse.app"


def _build_plain_text_body(verification_code: str) -> str:
    return (
        "Welcome to SkillPulse\n"
        "=====================\n\n"
        "Thank you for creating an account. To complete your registration, "
        "enter the verification code below on the SkillPulse verification page.\n\n"
        f"Verification code: {verification_code}\n\n"
        "This code is required to activate your account. "
        "If you did not request this email, you can safely ignore it.\n\n"
        "— SkillPulse\n"
        "© 2026 SkillPulse. If you didn't request this email, you can safely ignore it."
    )


def _build_html_body(verification_code: str) -> str:
    logo_html = _build_logo_html()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{VERIFICATION_SUBJECT}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@800;900&display=swap');
  </style>
</head>
<body style="margin:0;padding:0;background-color:#0f0c1a;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background-color:#0f0c1a;margin:0;padding:0;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
               style="max-width:520px;background-color:#1a1528;border:1px solid #2d2640;border-radius:12px;">
          <tr>
            <td align="center" style="padding:32px 32px 16px 32px;">
              {logo_html}
            </td>
          </tr>
          <tr>
            <td style="padding:8px 32px 24px 32px;">
              <p style="margin:0 0 16px 0;font-size:16px;line-height:1.6;color:#e2e8f0;">
                Welcome to SkillPulse. Thank you for creating an account.
              </p>
              <p style="margin:0;font-size:15px;line-height:1.6;color:#cbd5e1;">
                Enter the verification code below to activate your account and get started
                with your skill analysis journey.
              </p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:8px 32px 28px 32px;">
              <table role="presentation" cellspacing="0" cellpadding="0" border="0"
                     style="width:100%;max-width:360px;background-color:#0f0c1a;
                            border:1px solid #7c3aed;border-radius:10px;">
                <tr>
                  <td align="center" style="padding:24px 20px;">
                    <p style="margin:0 0 8px 0;font-size:12px;letter-spacing:0.08em;
                              text-transform:uppercase;color:#f472b6;">
                      Your verification code
                    </p>
                    <p style="margin:0;font-size:32px;font-weight:700;letter-spacing:8px;
                              color:#ffffff;font-family:'Courier New',Courier,monospace;">
                      {verification_code}
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:0 32px 28px 32px;">
              <p style="margin:0;font-size:13px;line-height:1.6;color:#94a3b8;">
                If you did not create a SkillPulse account, no action is required.
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 28px 32px;border-top:1px solid #2d2640;">
              <p style="margin:0;font-size:12px;line-height:1.5;color:#64748b;text-align:center;">
                &copy; 2026 SkillPulse. If you didn&apos;t request this email, you can safely ignore it.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_verification_email(to_email: str, verification_code: str) -> MIMEMultipart:
    message = MIMEMultipart("alternative")
    message["Subject"] = VERIFICATION_SUBJECT
    message["From"] = formataddr((FROM_DISPLAY_NAME, settings.FROM_EMAIL))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=_from_domain())
    message["X-Mailer"] = "SkillPulse"

    plain_part = MIMEText(_build_plain_text_body(verification_code), "plain", "utf-8")
    html_part = MIMEText(_build_html_body(verification_code), "html", "utf-8")

    message.attach(plain_part)
    message.attach(html_part)

    return message


def _build_logo_html() -> str:
    return """<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="display:inline-table;border-collapse:collapse;">
  <tr>
    <td valign="bottom" style="width:4px;height:24px;padding:0 2px 0 0;"><span style="display:block;width:4px;height:10px;background-color:#7c3aed;"></span></td>
    <td valign="bottom" style="width:4px;height:24px;padding:0 2px 0 0;"><span style="display:block;width:4px;height:16px;background-color:#a855f7;"></span></td>
    <td valign="bottom" style="width:4px;height:24px;padding:0 2px 0 0;"><span style="display:block;width:4px;height:24px;background-color:#c4b5fd;"></span></td>
    <td valign="bottom" style="width:4px;height:24px;padding:0 2px 0 0;"><span style="display:block;width:4px;height:18px;background-color:#f472b6;"></span></td>
    <td valign="bottom" style="width:4px;height:24px;padding:0 2px 0 0;"><span style="display:block;width:4px;height:12px;background-color:#e879f9;opacity:0.7;"></span></td>
    <td valign="bottom" style="width:4px;height:24px;padding:0;"><span style="display:block;width:4px;height:7px;background-color:#c4b5fd;opacity:0.4;"></span></td>
    <td valign="bottom" style="padding:0 0 0 12px;font-size:24px;font-weight:900;font-family:'Syne','Arial Black',Impact,sans-serif;line-height:24px;letter-spacing:0.35px;white-space:nowrap;">
      <span style="color:#c4b5fd;font-weight:900;font-family:'Syne','Arial Black',Impact,sans-serif;">Skill</span><span style="color:#ffffff;font-weight:900;font-family:'Syne','Arial Black',Impact,sans-serif;">Pulse</span>
    </td>
  </tr>
</table>"""


def _build_reset_plain_text_body(reset_link: str) -> str:
    return (
        "Reset Your SkillPulse Password\n"
        "==============================\n\n"
        "We received a request to reset your SkillPulse password. "
        "Use the link below to create a new password. This link expires in 30 minutes.\n\n"
        f"{reset_link}\n\n"
        "If you did not request this email, ignore it safely.\n\n"
        "© 2026 SkillPulse. If you didn't request this email, ignore it safely."
    )


def _build_reset_html_body(reset_link: str) -> str:
    logo_html = _build_logo_html()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{RESET_PASSWORD_SUBJECT}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@800;900&display=swap');
  </style>
</head>
<body style="margin:0;padding:0;background-color:#0f0c1a;font-family:Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#0f0c1a;margin:0;padding:0;">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width:560px;background-color:#1a1528;border:1px solid #2d2640;border-radius:12px;">
          <tr>
            <td align="center" style="padding:34px 32px 18px 32px;">
              {logo_html}
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:4px 32px 12px 32px;">
              <h1 style="margin:0;color:#ffffff;font-size:26px;line-height:1.25;font-weight:700;">
                Reset Your SkillPulse Password
              </h1>
            </td>
          </tr>
          <tr>
            <td style="padding:8px 36px 26px 36px;">
              <p style="margin:0;font-size:16px;line-height:1.6;color:#e2e8f0;text-align:center;">
                We received a request to reset your password. Use the secure link below to choose a new one. This link expires in 30 minutes.
              </p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:4px 32px 34px 32px;">
              <a href="{reset_link}" style="display:inline-block;background-color:#7c3aed;color:#ffffff;text-decoration:none;font-size:15px;font-weight:700;padding:15px 28px;border-radius:10px;border:1px solid #a855f7;">
                Reset Password
              </a>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 28px 32px;border-top:1px solid #2d2640;">
              <p style="margin:0;font-size:12px;line-height:1.5;color:#94a3b8;text-align:center;">
                &copy; 2026 SkillPulse. If you didn&apos;t request this email, ignore it safely.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _build_reset_password_email(to_email: str, token: str) -> MIMEMultipart:
    reset_link = f"http://localhost:5173/reset-password?token={token}"
    message = MIMEMultipart("alternative")
    message["Subject"] = RESET_PASSWORD_SUBJECT
    message["From"] = formataddr((FROM_DISPLAY_NAME, settings.FROM_EMAIL))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=_from_domain())
    message["X-Mailer"] = "SkillPulse"

    plain_part = MIMEText(_build_reset_plain_text_body(reset_link), "plain", "utf-8")
    html_part = MIMEText(_build_reset_html_body(reset_link), "html", "utf-8")

    message.attach(plain_part)
    message.attach(html_part)

    return message


def _send_sync(message: MIMEMultipart) -> None:
    try:
        with smtplib.SMTP(SENDGRID_SMTP_HOST, SENDGRID_SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login("apikey", settings.SENDGRID_API_KEY)
            server.send_message(message)
    except smtplib.SMTPException as exc:
        raise EmailDeliveryError(f"SMTP delivery failed: {exc}") from exc


async def send_verification_email(to_email: str, verification_code: str) -> None:
    """
    Send a verification code email via SendGrid SMTP.

    Builds a MIME multipart/alternative message with plain-text and HTML parts
    for better client compatibility and inbox placement.

    In development, falls back to console logging when SendGrid is not configured.
    """
    if not settings.SENDGRID_API_KEY or not settings.FROM_EMAIL:
        if settings.ENVIRONMENT == "development":
            print(f"[EMAIL VERIFICATION] Code for {to_email}: {verification_code}")
            return
        raise EmailDeliveryError("Email service is not configured")

    message = _build_verification_email(to_email, verification_code)

    try:
        await asyncio.to_thread(_send_sync, message)
    except EmailDeliveryError:
        raise
    except Exception as exc:
        logger.exception("Failed to send verification email to %s", to_email)
        raise EmailDeliveryError("Failed to send verification email") from exc


async def send_reset_password_email(email: str, token: str) -> None:
    """
    Send a password reset email via SendGrid SMTP.

    The raw token is delivered only to the user; the API stores a hashed token
    for validation.
    """
    if not settings.SENDGRID_API_KEY or not settings.FROM_EMAIL:
        if settings.ENVIRONMENT == "development":
            print(f"[PASSWORD RESET] Link for {email}: http://localhost:5173/reset-password?token={token}")
            return
        raise EmailDeliveryError("Email service is not configured")

    message = _build_reset_password_email(email, token)

    try:
        await asyncio.to_thread(_send_sync, message)
    except EmailDeliveryError:
        raise
    except Exception as exc:
        logger.exception("Failed to send reset password email to %s", email)
        raise EmailDeliveryError("Failed to send reset password email") from exc

