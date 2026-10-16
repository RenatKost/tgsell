"""HEAD support: serve HEAD as GET (same status/headers), strip the body (RFC 9110 §9.3.2)."""


class HeadAsGetMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "HEAD":
            return await self.app(scope, receive, send)
        scope = dict(scope, method="GET")

        async def send_no_body(message):
            if message["type"] == "http.response.body":
                if message.get("more_body", False):
                    return  # swallow streamed chunks; final empty message ends response
                message = {"type": "http.response.body", "body": b"", "more_body": False}
            await send(message)

        await self.app(scope, receive, send_no_body)
