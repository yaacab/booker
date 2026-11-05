"""Bound selected request bodies before Starlette parses them."""

from tempfile import SpooledTemporaryFile

from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from booker_api.config import settings
from booker_api.ical import MAX_ICAL_BYTES

MULTIPART_OVERHEAD_BYTES = 65_536


class AttachmentBodyLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        parts = scope.get("path", "").split("/")
        if scope["type"] != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return
        attachment = (
            len(parts) == 4
            and parts[1] == "bookings"
            and bool(parts[2])
            and parts[3] == "attachments"
        )
        ical_import = scope.get("path") == "/calendar/ical/import"
        if not attachment and not ical_import:
            await self.app(scope, receive, send)
            return

        # JSON may escape every source byte as six ASCII bytes; leave room for fields.
        limit = (
            settings.max_upload_bytes + MULTIPART_OVERHEAD_BYTES
            if attachment
            else MAX_ICAL_BYTES * 6 + MULTIPART_OVERHEAD_BYTES
        )
        error_detail = "Файл слишком большой" if attachment else "iCal слишком большой"
        for name, value in scope.get("headers", ()):
            if name.lower() == b"content-length" and value.isdigit() and int(value) > limit:
                await self._too_large(scope, receive, send, error_detail)
                return

        with SpooledTemporaryFile(max_size=65_536) as body:
            received = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                if message["type"] != "http.request":
                    continue
                chunk = message.get("body", b"")
                received += len(chunk)
                if received > limit:
                    await self._too_large(scope, receive, send, error_detail)
                    return
                await run_in_threadpool(body.write, chunk)
                if not message.get("more_body", False):
                    break

            await run_in_threadpool(body.seek, 0)
            delivered = False

            async def replay_receive():
                nonlocal delivered
                chunk = await run_in_threadpool(body.read, 65_536)
                if chunk:
                    return {"type": "http.request", "body": chunk, "more_body": True}
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": b"", "more_body": False}
                return await receive()

            await self.app(scope, replay_receive, send)

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send, detail: str) -> None:
        response = JSONResponse({"detail": detail}, status_code=413)
        await response(scope, receive, send)
