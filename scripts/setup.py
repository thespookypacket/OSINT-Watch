"""Generate a private deployment configuration without printing credentials."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
destination = root / ".env"
if destination.exists():
    raise SystemExit(
        ".env already exists; edit it directly. No credentials were changed."
    )
text = (root / ".env.example").read_text()
for key in (
    "POSTGRES_PASSWORD",
    "WATCH_GIS_PASSWORD",
    "WATCH_ADMIN_PASSWORD",
    "WATCH_SPIDERFOOT_TOKEN",
):
    text = text.replace(f"{key}=\n", f"{key}={secrets.token_urlsafe(32)}\n")
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as output:
    output.write(text)
print(
    "Created .env with unique credentials (mode 0600). Read WATCH_ADMIN_PASSWORD there to sign in."
)
