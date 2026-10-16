"""Task 28: security headers on every response.

Only frame-ancestors is set in CSP (no script/style restrictions), so Google
Identity, the Telegram login widget (their iframes inside our page) and fonts keep
working. Our own pages must not be framed by others (clickjacking).
"""
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


async def security_headers(request, call_next):
    response = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response
