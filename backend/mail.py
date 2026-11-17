import html
import smtplib
import ssl
from email.message import EmailMessage

from backend.auth import AuthError


def _render_otp_html(code: str, expiry_minutes: int, public_url: str = "") -> str:
    safe_code = html.escape(str(code).strip())
    safe_minutes = html.escape(str(expiry_minutes))

    url_block = ""
    trimmed_url = public_url.strip() if public_url else ""
    if trimmed_url.startswith(("http://", "https://")):
        safe_url = html.escape(trimmed_url, quote=True)
        url_block = (
            '\n              <table role="presentation" border="0" cellpadding="0" cellspacing="0"'
            ' style="margin-top: 20px;">\n'
            "                <tr>\n"
            '                  <td align="center" style="border-radius: 6px;'
            ' background-color: #A95535;">\n'
            f'                    <a href="{safe_url}" target="_blank" rel="noopener noreferrer"'
            ' style="font-size: 14px; font-weight: 600; color: #FFFFFF; text-decoration: none;'
            ' padding: 10px 22px; border-radius: 6px; display: inline-block;">'
            "前往 TravelMemo</a>\n"
            "                  </td>\n"
            "                </tr>\n"
            "              </table>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TravelMemo 登入驗證碼</title>
</head>
<body style="margin: 0; padding: 0; background-color: #F6F1E7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'PingFang TC', 'Microsoft JhengHei', sans-serif; -webkit-font-smoothing: antialiased; word-break: break-word;">
  <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="background-color: #F6F1E7; width: 100%; margin: 0; padding: 36px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="max-width: 520px; background-color: #FBF8F1; border-radius: 8px; border: 1px solid #DCD1BF; overflow: hidden;">
          <tr>
            <td style="height: 4px; background-color: #A95535; line-height: 4px; font-size: 4px;">&nbsp;</td>
          </tr>
          <tr>
            <td style="padding: 32px 32px 28px 32px;">
              <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom: 24px;">
                <tr>
                  <td align="left" style="vertical-align: middle;">
                    <span style="font-size: 18px; font-weight: 700; color: #453A32; letter-spacing: -0.2px;">TravelMemo</span>
                  </td>
                  <td align="right" style="vertical-align: middle;">
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" style="display: inline-table;">
                      <tr>
                        <td style="width: 8px; height: 8px; border-radius: 50%; background-color: #A95535; vertical-align: middle;"></td>
                        <td style="width: 20px; border-top: 2px dashed #DCD1BF; vertical-align: middle;"></td>
                        <td style="width: 8px; height: 8px; border-radius: 50%; background-color: #E0B65B; vertical-align: middle;"></td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <h1 style="margin: 0 0 12px 0; font-size: 20px; font-weight: 700; color: #453A32; line-height: 1.4;">登入驗證碼</h1>
              <p style="margin: 0 0 24px 0; font-size: 14px; color: #453A32; line-height: 1.6; opacity: 0.85;">
                請輸入以下驗證碼登入。
              </p>

              <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-bottom: 24px;">
                <tr>
                  <td align="center" style="background-color: #F6F1E7; border: 1px solid #DCD1BF; border-radius: 6px; padding: 20px 16px;">
                    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Consolas, Monaco, monospace; font-size: 32px; font-weight: 700; letter-spacing: 6px; color: #453A32; user-select: all; -webkit-user-select: all; text-align: center; display: inline-block;">
                      {safe_code}
                    </div>
                  </td>
                </tr>
              </table>

              <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="border-left: 3px solid #A95535; padding-left: 12px;">
                    <p style="margin: 0 0 4px 0; font-size: 14px; font-weight: 600; color: #453A32; line-height: 1.5;">
                      有效時間為 {safe_minutes} 分鐘。
                    </p>
                    <p style="margin: 0; font-size: 13px; color: #766859; line-height: 1.5;">
                      若非本人操作，請忽略此信。
                    </p>
                  </td>
                </tr>
              </table>{url_block}

              <table role="presentation" width="100%" border="0" cellpadding="0" cellspacing="0" style="margin-top: 24px; border-top: 1px solid #DCD1BF;">
                <tr>
                  <td style="padding-top: 16px;">
                    <p style="margin: 0; font-size: 12px; color: #766859; line-height: 1.5;">
                      TravelMemo &middot; 旅程手記
                    </p>
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


def smtp_sender(settings):
    def send(email, code):
        if not settings.smtp_host:
            raise AuthError(503, "尚未設定寄信服務。")
        expiry_minutes = settings.otp_seconds // 60
        public_url = getattr(settings, "public_url", "")

        message = EmailMessage()
        message["Subject"] = "TravelMemo 登入驗證碼"
        message["From"] = settings.smtp_from
        message["To"] = email
        message.set_content(
            f"你的 TravelMemo 驗證碼是：{code}\n"
            f"有效時間為 {expiry_minutes} 分鐘。\n"
            "若非本人操作，請忽略此信。"
        )
        html_content = _render_otp_html(code, expiry_minutes, public_url)
        message.add_alternative(html_content, subtype="html")

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
