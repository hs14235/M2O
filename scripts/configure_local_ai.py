"""Enable the isolated Ollama Compose service and native development connection."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def update(path, values):
    if not path.exists():
        raise ValueError("Run configure_local.py before configuring local inference")
    lines = path.read_text().splitlines()
    keys = set(values)
    lines = [line for line in lines if line.partition("=")[0] not in keys]
    lines.extend(key + "=" + value for key, value in values.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    update(ROOT / ".env", {"OLLAMA_MODEL": "qwen2.5:1.5b", "OLLAMA_CONTAINER_URL": "http://ollama:11434"})
    update(
        ROOT / "backend" / ".env", {"OLLAMA_MODEL": "qwen2.5:1.5b", "OLLAMA_URL": "http://127.0.0.1:11435"}
    )
    print("Local AI settings enabled. Restart API/worker containers after the model is available.")


if __name__ == "__main__":
    main()
