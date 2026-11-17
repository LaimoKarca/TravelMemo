"""Read-only public smoke checks; never requests a login email."""

import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

if len(sys.argv) != 2:
    raise SystemExit("Usage: python deploy/check-public.py https://travel.example.com")
base = sys.argv[1]


def check(path, expected, method="GET", payload=None, origin=None, headers=None):
    request_headers = {
        'User-Agent': 'TravelMemo-DeploymentCheck/0.2 (+https://github.com/LaimoKarca/TravelMemo)',
        **(headers or {}),
    }
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    if origin:
        request_headers["Origin"] = origin
    request = Request(
        base + path,
        method=method,
        headers=request_headers,
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as exc:
        response = exc
    with response:
        status, data = response.status, response.read()
    if status != expected:
        raise SystemExit(f"FAIL {method} {path}: {status}, expected {expected}")
    print(f"PASS {method} {path}: {status}")
    return data


assert b"TravelMemo" in check("/", 200)
assert json.loads(check("/api/v1/health/live", 200))["status"] == "ok"
assert json.loads(check("/api/v1/health/ready", 200))["database"] is True
check("/api/v1/auth/me", 401)
check("/api/v1/trips", 401)
check("/api/docs", 404)
check(
    "/api/v1/auth/request-code",
    403,
    method="POST",
    payload={"email": "audit@example.com"},
    origin="https://untrusted.example.com",
)
check("/api/v1/health/live?probe=tm-normal", 200)
check("/api/v1/health/live?probe=tm-spoof", 200, headers={"X-Forwarded-For": "203.0.113.99"})
print("Public checks passed; no login email sent.")
