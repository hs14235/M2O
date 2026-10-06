"""Generate ignored local PostgreSQL configuration without printing secrets."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    root_env, backend_env = ROOT / ".env", ROOT / "backend" / ".env"
    if root_env.exists() or backend_env.exists():
        raise SystemExit("Existing configuration preserved. Edit it explicitly or choose a fresh worktree.")
    password = secrets.token_hex(32)
    root_env.write_text(
        f"POSTGRES_USER=meeting\nPOSTGRES_PASSWORD={password}\nPOSTGRES_DB=meeting_to_tasks\nPOSTGRES_PORT=55432\nAPP_PORT=8080\n",
        encoding="utf-8",
    )
    backend_env.write_text(
        f"DATABASE_URL=postgresql+psycopg://meeting:{password}@127.0.0.1:55432/meeting_to_tasks\nAPP_ENVIRONMENT=development\nAPP_ORIGIN=http://localhost:5173\nPUBLIC_DEMO_MODE=true\nEMBED_PROVIDER=hash\nOLLAMA_MODEL=\n",
        encoding="utf-8",
    )
    print("Generated ignored .env and backend/.env with separate local database credentials.")


if __name__ == "__main__":
    main()
