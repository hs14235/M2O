"""Same-origin frontend serving for the bounded hosted demo container."""

from pathlib import Path
from urllib.parse import urlsplit

from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; media-src 'self'; object-src 'none'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
}


class HostedApplication:
    """Delegate API paths unchanged; static responses never alter API security headers."""

    def __init__(self, api: ASGIApp, static_root: Path, origin: str):
        self.api = api
        self.root = static_root.resolve()
        if not (self.root / "index.html").is_file():
            raise RuntimeError("Build the frontend before starting the hosted runtime")
        self.static = TrustedHostMiddleware(
            Starlette(routes=[Route("/{path:path}", self.file, methods=["GET", "HEAD"])]),
            allowed_hosts=[urlsplit(origin).hostname or "localhost", "localhost", "127.0.0.1", "testserver"],
        )

    async def file(self, request: Request) -> Response:
        relative = request.path_params["path"]
        candidate = (self.root / relative).resolve()
        if not candidate.is_relative_to(self.root):
            return Response(status_code=404, headers={**STATIC_HEADERS, "Cache-Control": "no-store"})
        if not candidate.is_file():
            # Only document navigation receives the SPA shell. Missing assets stay missing.
            if (
                Path(relative).suffix
                or relative.startswith(("assets/", "media/"))
                or "text/html" not in request.headers.get("accept", "")
            ):
                return Response(status_code=404, headers={**STATIC_HEADERS, "Cache-Control": "no-store"})
            candidate = self.root / "index.html"
        cache = "public, max-age=31536000, immutable" if relative.startswith("assets/") else "no-cache"
        return FileResponse(candidate, headers={**STATIC_HEADERS, "Cache-Control": cache})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if (
            scope["type"] != "http"
            or path == "/api"
            or path.startswith("/api/")
            or path
            in {
                "/healthz",
                "/readyz",
            }
        ):
            await self.api(scope, receive, send)
        else:
            await self.static(scope, receive, send)


def create_app() -> HostedApplication:
    import os

    from .main import app
    from .settings import settings

    return HostedApplication(app, Path(os.environ.get("M2O_STATIC_ROOT", "/app/static")), settings.app_origin)
