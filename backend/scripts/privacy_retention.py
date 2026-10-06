"""Preview bounded retention cleanup; --apply is an explicit operator mutation."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import session_scope  # noqa: E402
from app.services.retention import RetentionService  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resolve", help="Exact retention record UUID, following manual effect review")
    parser.add_argument("--resolution", choices=("confirmed", "not_sent", "accepted_unknown"))
    args = parser.parse_args()
    if bool(args.resolve) != bool(args.resolution):
        parser.error("--resolve and --resolution must be supplied together")
    if args.resolve and args.apply and input("Confirm retention record UUID: ") != args.resolve:
        raise SystemExit("Retention decision not applied")
    with session_scope() as session:
        service = RetentionService(session)
        result = (
            service.resolve_tombstone(args.resolve, args.resolution, apply=args.apply)
            if args.resolve
            else service.run(limit=args.limit, apply=args.apply)
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
