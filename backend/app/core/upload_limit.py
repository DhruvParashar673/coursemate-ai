import re

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings
from app.core.security import InvalidTokenError, decode_access_token

_UPLOAD_PATH = re.compile(r"^/courses/[0-9a-fA-F]{24}/documents/?$")
_MULTIPART_OVERHEAD = 256 * 1024  # boundaries/headers on top of the file itself


class UploadGuardMiddleware:
    """Protects the PDF upload route *before* Starlette spools the multipart body to disk.

    Starlette caps only non-file form fields, so without this a huge (or unauthenticated) upload
    would be fully written to disk before any handler could reject it. This middleware:
      1. rejects requests without a validly signed, unexpired Bearer token (401, body never read);
      2. rejects a declared Content-Length over the limit (413, body never read);
      3. counts bytes as they stream in and aborts with 413 if the limit is exceeded
         (covers chunked uploads and lying Content-Length headers).
    Account existence is still checked by `get_current_user` afterwards.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    @staticmethod
    def _has_valid_token(authorization: str | None) -> bool:
        if not authorization:
            return False
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return False
        try:
            decode_access_token(token.strip())
        except InvalidTokenError:
            return False
        return True

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["method"] != "POST" or not _UPLOAD_PATH.match(scope["path"]):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}

        if not self._has_valid_token(headers.get("authorization")):
            response = JSONResponse(
                {"detail": "Invalid or missing authentication token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return

        max_mb = get_settings().MAX_UPLOAD_SIZE_MB
        limit = max_mb * 1024 * 1024 + _MULTIPART_OVERHEAD
        too_large = f"The PDF exceeds the {max_mb} MB limit"

        declared = headers.get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await JSONResponse({"detail": too_large}, status_code=413)(scope, receive, send)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=too_large)
            return message

        await self.app(scope, limited_receive, send)
