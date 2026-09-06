"""Restore into a NEW database only. Switching the app is a separate explicit action."""

import argparse
import re
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("path", type=Path)
parser.add_argument("--database", required=True)
args = parser.parse_args()
if not re.fullmatch(r"watch_restore_[a-z0-9_]+", args.database):
    raise SystemExit(
        "New database name must start with watch_restore_ and contain lowercase letters, digits, underscores."
    )
base = ["docker", "compose", "exec", "-T", "db"]
subprocess.run(base + ["createdb", "-U", "watch", args.database], check=True)
with args.path.open("rb") as data:
    subprocess.run(
        base
        + [
            "pg_restore",
            "-U",
            "watch",
            "-d",
            args.database,
            "--no-owner",
            "--exit-on-error",
        ],
        stdin=data,
        check=True,
    )
print(f"Restored into {args.database}. Existing workspace was not modified.")
