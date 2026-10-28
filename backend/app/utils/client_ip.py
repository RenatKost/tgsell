"""Client IP for rate limiting behind Railway's edge proxy.

Railway's edge APPENDS the real peer address to X-Forwarded-For, so the RIGHTMOST entry is
the one we can trust; everything to its left is client-supplied and spoofable. Falls back
to the socket peer (request.client.host) when the header is absent.
"""
from __future__ import annotations

from starlette.requests import Request


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for") or ""
    hops = [h.strip() for h in xff.split(",") if h.strip()]
    if hops:
        return hops[-1]
    return request.client.host if request.client else ""
