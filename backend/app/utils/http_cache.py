async def api_no_store(request, call_next):
    """API JSON must never be cached by the browser (iOS Safari reused stale chat polls)."""
    response = await call_next(request)
    if request.url.path.startswith("/api/") and "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-store"
    return response
