import hashlib
import hmac
import secrets
import smtplib
import time
from uuid import NAMESPACE_URL, uuid5


class AuthError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


class AuthService:
    def __init__(self, settings, store, sender, clock=time.time):
        self.settings, self.store, self.sender, self.clock = settings, store, sender, clock

    def digest(self, value):
        return hmac.new(
            self.settings.session_secret.encode(), value.encode(), hashlib.sha256
        ).hexdigest()

    def bucket(self, tx, name, limit, now, window=3600):
        key = "rate:" + self.digest(name)
        record = tx.get(key) or {}
        hits = [t for t in record.get("hits", []) if t > now - window]
        if len(hits) >= limit:
            return False
        tx.put(key, {"hits": hits + [now], "expires_at": now + window})
        return True

    def request_code(self, email, ip):
        now = self.clock()
        key = "otp:" + self.digest(email)
        code = f"{secrets.randbelow(1000000):06d}"
        error = None
        with self.store.atomic() as tx:
            ip_ok = self.bucket(tx, "send-ip:" + ip, self.settings.ip_hourly_limit, now)
            mail_ok = self.bucket(tx, "send-email:" + email, self.settings.email_hourly_limit, now)
            cooldown_ok = self.bucket(
                tx, "resend:" + email, 1, now, window=self.settings.resend_seconds
            )
            if not ip_ok or not mail_ok or not cooldown_ok:
                error = AuthError(429, "請稍後再要求驗證碼。")
            elif email in self.settings.emails:
                tx.put(
                    key,
                    {
                        "digest": self.digest(email + ":" + code),
                        "attempts": 0,
                        "issued_at": now,
                        "expires_at": now + self.settings.otp_seconds,
                    },
                )
        if error:
            raise error
        if email in self.settings.emails:
            try:
                self.sender(email, code)
            except (OSError, smtplib.SMTPException, AuthError):
                # Do not delete a newer challenge issued by another request.
                with self.store.atomic() as tx:
                    current = tx.get(key)
                    if current and current["digest"] == self.digest(email + ":" + code):
                        tx.delete(key)
                raise AuthError(503, "驗證碼暫時無法寄送，請稍後再試。") from None

    def verify(self, email, code, ip):
        now = self.clock()
        result = None
        throttled = False
        with self.store.atomic() as tx:
            throttled = not self.bucket(
                tx, "verify-ip:" + ip, self.settings.verify_ip_hourly_limit, now
            )
            key = "otp:" + self.digest(email)
            record = tx.get(key)
            if (
                not throttled
                and email in self.settings.emails
                and record
                and record["expires_at"] > now
                and record["attempts"] < self.settings.otp_attempts
            ):
                record["attempts"] += 1
                tx.put(key, record)
                if hmac.compare_digest(record["digest"], self.digest(email + ":" + code)):
                    tx.delete(key)
                    user = {"id": str(uuid5(NAMESPACE_URL, "travelmemo:" + email)), "email": email}
                    tx.user(user["id"], email)
                    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                    tx.put(
                        "session:" + self.digest(token),
                        {
                            "user": user,
                            "csrf_token": csrf,
                            "expires_at": now + self.settings.session_days * 86400,
                        },
                    )
                    result = (token, user, csrf)
        if throttled:
            raise AuthError(429, "驗證次數過多，請稍後再試。")
        if result is None:
            raise AuthError(401, "驗證碼無效或已過期，請重新確認。")
        return result

    def session(self, token):
        if token and len(token) <= 128:
            with self.store.atomic() as tx:
                record = tx.get("session:" + self.digest(token))
                if (
                    record
                    and record["expires_at"] > self.clock()
                    and record["user"]["email"] in self.settings.emails
                ):
                    return record
        raise AuthError(401, "請先登入。")

    def logout(self, token, csrf):
        record = self.session(token)
        if not csrf or not hmac.compare_digest(record["csrf_token"], csrf):
            raise AuthError(403, "登入驗證已變更，請重新整理頁面。")
        with self.store.atomic() as tx:
            tx.delete("session:" + self.digest(token))
