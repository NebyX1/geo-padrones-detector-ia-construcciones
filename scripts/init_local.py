"""Create fresh local secrets without reading sample/.env or printing credentials."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(".env ya existe; no se modificó.")
text = (root / ".env.example").read_text(encoding="utf-8")
replacements = {
    "change-me-generate-at-least-32-random-characters": secrets.token_urlsafe(48),
    "change-me-generate-separately": secrets.token_urlsafe(48),
    "change-me-generate-a-private-password": secrets.token_hex(24),
    "change-me-access-key": secrets.token_hex(12),
    "change-me-generate-a-private-secret": secrets.token_urlsafe(36),
}
for before, after in replacements.items():
    text = text.replace(before, after)
target.write_text(text, encoding="utf-8")
print("Configuración local privada creada en .env; no compartir ni versionar.")
