"""Wire local environment files without printing or duplicating secrets."""
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    env = ROOT / ".env"
    if not env.exists():
        env.write_text((ROOT / ".env.example").read_text())
    content = env.read_text()
    has_secret = any(
        line.partition("=")[0].strip() == "JWT_SECRET"
        and line.partition("=")[2].strip().strip("\"'")
        for line in content.splitlines()
        if not line.lstrip().startswith("#")
    )
    if not has_secret:
        lines = [line for line in content.splitlines()
                 if line.partition("=")[0].strip() != "JWT_SECRET"]
        env.write_text("\n".join(lines) + "\nJWT_SECRET=" + secrets.token_hex(32) + "\n")
    env.chmod(0o600)
    server = ROOT / "server"
    client = ROOT / "client"
    server.mkdir(exist_ok=True)
    client.mkdir(exist_ok=True)
    link = server / ".env"
    if not link.exists() and not link.is_symlink():
        link.symlink_to("../.env")
    client_env = client / ".env.local"
    if not client_env.exists():
        client_env.write_text("NEXT_PUBLIC_API_URL=http://localhost:8000\n"
                              "NEXT_PUBLIC_WS_URL=ws://localhost:8000\n")
    print("Environment ready; credentials kept private.")


if __name__ == "__main__":
    main()
