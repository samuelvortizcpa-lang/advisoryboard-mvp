"""
Transactional email service using Resend.

Gracefully degrades when RESEND_API_KEY is not configured — email failures
never crash the main request.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    settings = get_settings()
    return bool(settings.resend_api_key and settings.resend_from_email)


def send_consent_request_email(
    to_email: str,
    client_name: str,
    preparer_name: str,
    preparer_firm: str | None,
    signing_url: str,
    expiry_days: int = 30,
) -> None:
    """
    Send a 7216 consent request email to a taxpayer via Resend.

    Raises on failure so the caller can decide how to handle it.
    """
    import resend

    settings = get_settings()
    if not settings.resend_api_key or not settings.resend_from_email:
        logger.warning("Resend not configured — skipping consent email to %s", to_email)
        return

    resend.api_key = settings.resend_api_key

    sender_label = preparer_firm or preparer_name
    subject = f"Action Required: Tax Return Information Consent \u2014 {sender_label}"

    html = _build_consent_email_html(
        client_name=client_name,
        preparer_name=preparer_name,
        preparer_firm=preparer_firm,
        signing_url=signing_url,
        expiry_days=expiry_days,
    )

    resend.Emails.send({
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    })

    logger.info("Consent request email sent to %s for client %s", to_email, client_name)


def send_consent_signed_notification(
    to_email: str,
    client_name: str,
    signer_name: str,
) -> None:
    """Notify the CPA that a client has signed the consent form."""
    import resend

    settings = get_settings()
    if not settings.resend_api_key or not settings.resend_from_email:
        return

    resend.api_key = settings.resend_api_key

    resend.Emails.send({
        "from": settings.resend_from_email,
        "to": [to_email],
        "subject": f"{client_name} has signed the Section 7216 consent form",
        "html": (
            f"<p>Good news — <strong>{client_name}</strong> has electronically "
            f"signed the IRC Section 7216 consent form.</p>"
            f"<p>Signed by: {signer_name}</p>"
            f"<p>You can view the signed consent record and PDF in your "
            f"<a href=\"{settings.frontend_url}/dashboard/clients\">AdvisoryBoard dashboard</a>.</p>"
            f"<p style=\"color:#888;font-size:12px;\">This notification was sent by "
            f"AdvisoryBoard (myadvisoryboard.space).</p>"
        ),
    })

    logger.info("Consent-signed notification sent to %s for client %s", to_email, client_name)


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------


def _build_consent_email_html(
    client_name: str,
    preparer_name: str,
    preparer_firm: str | None,
    signing_url: str,
    expiry_days: int,
) -> str:
    firm_line = f" at {preparer_firm}" if preparer_firm else ""
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:#f7f7f7;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f7f7f7;padding:40px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.1);">

<!-- Header -->
<tr><td style="background:#1e40af;padding:32px 40px;">
  <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:600;">
    {preparer_name}{firm_line} is requesting your consent
  </h1>
</td></tr>

<!-- Body -->
<tr><td style="padding:32px 40px;">
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    Dear {client_name},
  </p>
  <p style="margin:0 0 16px;color:#374151;font-size:15px;line-height:1.6;">
    As your tax professional, {preparer_name} uses a secure document management
    platform called AdvisoryBoard to better serve you. Federal law (IRC Section
    7216) requires your written consent before your tax return information can be
    used within this platform for services such as document analysis and meeting
    preparation.
  </p>
  <p style="margin:0 0 24px;color:#374151;font-size:15px;line-height:1.6;">
    <strong>This takes less than 2 minutes to complete.</strong>
  </p>

  <!-- CTA Button -->
  <table cellpadding="0" cellspacing="0" style="margin:0 auto 24px;">
  <tr><td style="background:#1e40af;border-radius:6px;">
    <a href="{signing_url}"
       style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:16px;font-weight:600;text-decoration:none;">
      Review &amp; Sign Consent Form
    </a>
  </td></tr>
  </table>

  <p style="margin:0 0 8px;color:#6b7280;font-size:13px;line-height:1.5;">
    This link expires in {expiry_days} days. If you have questions, contact
    {preparer_name} directly.
  </p>
</td></tr>

<!-- Footer -->
<tr><td style="padding:24px 40px;border-top:1px solid #e5e7eb;background:#f9fafb;">
  <p style="margin:0;color:#9ca3af;font-size:11px;line-height:1.5;">
    This consent request was sent by {preparer_name} via AdvisoryBoard
    (myadvisoryboard.space). If you did not expect this email, you may safely
    ignore it.
  </p>
</td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
