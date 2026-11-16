import smtplib
import ssl
from email.message import EmailMessage

from backend.auth import AuthError


def smtp_sender(settings):
    def send(email, code):
        if not settings.smtp_host:
            raise AuthError(503, "尚未設定寄信服務。")
        message = EmailMessage()
        message["Subject"] = "TravelMemo 登入驗證碼"
        message["From"] = settings.smtp_from
        message["To"] = email
        message.set_content(
            f"你的 TravelMemo 驗證碼是：{code}\n"
            f"有效時間為 {settings.otp_seconds // 60} 分鐘。\n"
            "若非本人操作，請忽略此信。"
        )
        factory = smtplib.SMTP_SSL if settings.smtp_tls == "ssl" else smtplib.SMTP
        kwargs = {"timeout": settings.smtp_timeout}
        if settings.smtp_tls == "ssl":
            kwargs["context"] = ssl.create_default_context()
        with factory(settings.smtp_host, settings.smtp_port, **kwargs) as client:
            if settings.smtp_tls == "starttls":
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_user and settings.smtp_auth:
                client.login(settings.smtp_user, settings.smtp_password)
            client.send_message(message)

    return send
