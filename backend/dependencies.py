"""Shared session and CSRF checks for private application endpoints."""

import hmac

from fastapi import HTTPException, Request


def authenticate(auth, request: Request, write: bool = False) -> str:
    session = auth.session(request.cookies.get("travelmemo_session"))
    if write:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not hmac.compare_digest(session["csrf_token"], csrf):
            raise HTTPException(403, "登入驗證已變更，請重新整理頁面。")
    return session["user"]["id"]
