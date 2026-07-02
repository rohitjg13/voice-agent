"""Pure-ASGI middleware. Kept off FastAPI's BaseHTTPMiddleware so SSE
streaming responses pass through untouched."""

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

import structlog

logger = structlog.get_logger()

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_TOO_LARGE_BODY = json.dumps({"detail": "Request body too large"}).encode()


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Reject request bodies over `max_bytes`.

    Fast path: Content-Length header (all standard JSON clients send it).
    Slow path: counts chunked bodies as they arrive so a client can't dodge
    the limit by omitting the header.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = -1
                if declared > self.max_bytes or declared < 0:
                    await self._reject(send, scope)
                    return
                break

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not response_started:
                await self._reject(send, scope)
            else:
                raise

    async def _reject(self, send: Send, scope: Scope) -> None:
        logger.warning(
            "request_body_too_large",
            path=scope.get("path"),
            limit=self.max_bytes,
        )
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_TOO_LARGE_BODY)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _TOO_LARGE_BODY})
