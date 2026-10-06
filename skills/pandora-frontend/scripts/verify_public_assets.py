"""Read-only HTTP verification of public files, MIME types, hashes and missing 404s."""

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MIME = {
    ".mp4": {"video/mp4"}, ".webm": {"video/webm"},
    ".webp": {"image/webp"}, ".avif": {"image/avif"},
    ".png": {"image/png"}, ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"},
    ".svg": {"image/svg+xml"}, ".css": {"text/css"},
    ".js": {"text/javascript", "application/javascript"}, ".woff2": {"font/woff2"},
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, target):
        raise HTTPError(request.full_url, code, "Asset redirects require an explicit final base URL", headers, file)


def relative_path(value: str, root: Path) -> tuple[str, Path]:
    name = value.replace("\\", "/")
    part = PurePosixPath(name)
    if part.is_absolute() or any(item in {"..", "."} for item in part.parts) or not part.parts or any(char in name for char in "?#\r\n"):
        raise ValueError("Use an ordinary relative public-asset path")
    target = (root / Path(*part.parts)).resolve()
    if not target.is_relative_to(root) or target.suffix.lower() not in MIME:
        raise ValueError("Asset must remain within the public directory and have a supported static type")
    return part.as_posix(), target


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--public-dir", required=True)
    parser.add_argument("--asset", action="append", required=True)
    parser.add_argument("--missing")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--max-file-bytes", type=int, default=50_000_000)
    args = parser.parse_args()
    base = urlsplit(args.base_url)
    if base.scheme not in {"http", "https"} or not base.hostname or base.username or base.password or base.query or base.fragment:
        raise ValueError("Use an explicit HTTP(S) base URL without credentials, query or fragment")
    if not 0 < args.timeout <= 60:
        raise ValueError("Timeout must be greater than zero and at most 60 seconds")
    if not 0 < args.max_file_bytes <= 500_000_000:
        raise ValueError("Choose a positive file bound no larger than 500 MB")
    root = Path(args.public_dir).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("The public path must be a directory")
    origin = args.base_url.rstrip("/") + "/"
    failures = 0
    opener = build_opener(NoRedirect)
    for value in args.asset:
        name, path = relative_path(value, root)
        if path.stat().st_size > args.max_file_bytes:
            raise ValueError("Asset exceeds the configured byte bound")
        expected = path.read_bytes()
        try:
            with opener.open(Request(origin + quote(name, safe="/"), method="GET"), timeout=args.timeout) as response:
                body = response.read(len(expected) + 1)
                status = response.status
                mime = response.headers.get_content_type().lower()
                valid = status == 200 and mime in MIME[path.suffix.lower()] and body == expected
                print(f"{'PASS' if valid else 'FAIL'} {name}: HTTP {status}, {mime}, {len(body)} bytes, sha256={hashlib.sha256(body).hexdigest()}")
                failures += not valid
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            print(f"FAIL {name}: {type(error).__name__}; no response content printed")
            failures += 1
    if args.missing:
        name, path = relative_path(args.missing, root)
        if path.exists():
            raise ValueError("The missing-file probe must not exist locally")
        try:
            with opener.open(Request(origin + quote(name, safe="/"), method="GET"), timeout=args.timeout) as response:
                print(f"FAIL missing {name}: HTTP {response.status}; expected 404")
                failures += 1
        except HTTPError as error:
            valid = error.code == 404
            print(f"{'PASS' if valid else 'FAIL'} missing {name}: HTTP {error.code}")
            failures += not valid
        except (URLError, TimeoutError, OSError) as error:
            print(f"FAIL missing {name}: {type(error).__name__}; 404 not established")
            failures += 1
    print(f"Checked {len(args.asset)} public assets; {failures} failed checks")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        sys.exit(f"Asset verification failed ({type(error).__name__}); request/file contents withheld")
