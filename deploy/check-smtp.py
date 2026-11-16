"""Run inside API container; authenticates only, never sends mail."""

import smtplib
import ssl

from backend.config import Settings

settings = Settings()
try:
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
        client.starttls(context=ssl.create_default_context())
        client.login(settings.smtp_user, settings.smtp_password)
    print("SMTP_AUTH_OK; no email sent")
except smtplib.SMTPAuthenticationError as exc:
    raise SystemExit(f"SMTP_AUTH_REJECTED status={exc.smtp_code}") from None
except (OSError, smtplib.SMTPException) as exc:
    raise SystemExit(f"SMTP_UNAVAILABLE type={type(exc).__name__}") from None
