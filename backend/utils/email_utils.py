import smtplib
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from backend.config import (
    EMAIL_ASSET_BASE_URL,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_SERVER,
    SMTP_USER,
)


LOGO_DIR = Path(__file__).resolve().parents[2] / "frontend" / "logo"
INLINE_IMAGES = {
    "lovelace-logo": LOGO_DIR / "logo.png",
    "lovelace-wordmark": LOGO_DIR / "project_lovelace.png",
}


def _is_public_https_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    local_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
    return parsed.scheme == "https" and bool(host) and host not in local_hosts and not host.endswith(".local")


def _email_asset_base_url(base_url: str) -> Optional[str]:
    candidate = (EMAIL_ASSET_BASE_URL or base_url).rstrip("/")
    if _is_public_https_url(candidate):
        return candidate
    return None


def _inline_images_available() -> bool:
    return all(path.is_file() for path in INLINE_IMAGES.values())


def _image_src(asset_base_url: Optional[str], content_id: str, filename: str) -> str:
    if asset_base_url:
        return f"{asset_base_url}/frontend/logo/{filename}"
    return f"cid:{content_id}"


def _text_brand_header_html() -> str:
    return """
                                <div style="font-size: 24px; font-weight: 700; color: #ffffff; line-height: 1.2;">Project Lovelace</div>
                                <div style="font-size: 10px; font-weight: 600; letter-spacing: 0.18em; color: #ffffff; opacity: 0.6; text-transform: uppercase; margin-top: 8px;">Research & Intelligence</div>
    """


def _brand_header_html(asset_base_url: Optional[str], use_inline_images: bool) -> str:
    if not asset_base_url and not use_inline_images:
        return _text_brand_header_html()

    logo_url = _image_src(asset_base_url, "lovelace-logo", "logo.png")
    wordmark_url = _image_src(asset_base_url, "lovelace-wordmark", "project_lovelace.png")
    return f"""
                                <table border="0" cellpadding="0" cellspacing="0" role="presentation" style="margin: 0 auto 10px auto; border-collapse: collapse;">
                                    <tr>
                                        <td valign="middle" style="padding: 0 10px 0 0;">
                                            <img src="{logo_url}" alt="Project Lovelace logo" width="48" height="48" border="0" style="display: block; width: 48px; height: 48px; border-radius: 12px; border: 0;">
                                        </td>
                                        <td valign="middle" style="padding: 0;">
                                            <img src="{wordmark_url}" alt="Project Lovelace" width="150" border="0" style="display: block; width: 150px; height: auto; border: 0;">
                                        </td>
                                    </tr>
                                </table>
                                <div style="font-size: 10px; font-weight: 600; letter-spacing: 0.18em; color: #ffffff; opacity: 0.6; text-transform: uppercase;">Research & Intelligence</div>
    """


def _attach_inline_images(message: MIMEMultipart) -> None:
    for content_id, path in INLINE_IMAGES.items():
        with path.open("rb") as image_file:
            image = MIMEImage(image_file.read())
        image.add_header("Content-ID", f"<{content_id}>")
        image.add_header("Content-Disposition", "inline")
        message.attach(image)


def send_verification_email(to_email: str, token: str, base_url: str):
    if not SMTP_USER or not SMTP_PASSWORD:
        print("SMTP credentials not configured. Skipping email.")
        return

    subject = "Activate your Project Lovelace account"
    public_base_url = base_url.rstrip("/")
    verification_link = f"{public_base_url}/api/auth/verify/{token}"
    asset_base_url = _email_asset_base_url(base_url)
    use_inline_images = asset_base_url is None and _inline_images_available()
    header_html = _brand_header_html(asset_base_url, use_inline_images)
    text_content = (
        "Confirm your research identity\n\n"
        "Welcome to Project Lovelace. To finish setting up your account, "
        "verify your email address by opening this link:\n\n"
        f"{verification_link}\n\n"
        "This link will expire in 24 hours. If you did not create an account "
        "with Project Lovelace, you can safely ignore this email."
    )
    
    # Using inlined styles and table-based layout for maximum compatibility across all email clients
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #f4f2ef; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f4f2ef; padding: 40px 20px;">
            <tr>
                <td align="center">
                    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; background-color: #fcfbf9; border: 1px solid #e0ddd7; border-radius: 16px; overflow: hidden; border-collapse: separate;">
                        <!-- Header -->
                        <tr>
                            <td align="center" style="background-color: #182321; padding: 22px 20px;">
{header_html}
                            </td>
                        </tr>
                        <!-- Content -->
                        <tr>
                            <td style="padding: 45px 40px; background-color: #fcfbf9;">
                                <h2 style="margin: 0 0 20px 0; color: #182321; font-size: 22px; font-weight: 700; line-height: 1.2;">Confirm your research identity</h2>
                                <p style="margin: 0 0 30px 0; color: #4a4a4a; font-size: 16px; line-height: 1.6;">
                                    Welcome to Project Lovelace. To finish setting up your account and begin your research, please verify your email address by clicking the button below.
                                </p>
                                <table border="0" cellpadding="0" cellspacing="0" width="100%">
                                    <tr>
                                        <td align="center">
                                            <a href="{verification_link}" style="display: inline-block; padding: 16px 36px; background-color: #d95f39; color: #ffffff; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(217, 95, 57, 0.2);">Verify Email Address</a>
                                        </td>
                                    </tr>
                                </table>
                                <p style="margin: 35px 0 0 0; color: #8c8c8c; font-size: 14px; line-height: 1.5;">
                                    This link will expire in 24 hours. If you did not create an account with Project Lovelace, you can safely ignore this email.
                                </p>
                                <div style="margin: 30px 0; border-top: 1px solid #e0ddd7;"></div>
                                <p style="margin: 0; color: #a0a0a0; font-size: 12px; line-height: 1.5; word-break: break-all;">
                                    If the button above doesn't work, copy and paste this link into your browser:<br>
                                    <a href="{verification_link}" style="color: #d95f39; text-decoration: none;">{verification_link}</a>
                                </p>
                            </td>
                        </tr>
                        <!-- Footer -->
                        <tr>
                            <td align="center" style="padding: 24px; background-color: #f4f2ef; color: #8c8c8c; font-size: 12px;">
                                &copy; 2026 Project Lovelace. All rights reserved.
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    message = MIMEMultipart("related")
    message["Subject"] = subject
    message["From"] = f"PROJECT LOVELACE <{SMTP_USER}>"
    message["To"] = to_email

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(text_content, "plain"))
    alternative.attach(MIMEText(html_content, "html"))
    message.attach(alternative)

    if use_inline_images:
        _attach_inline_images(message)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, message.as_string())
            print(f"Verification email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")
