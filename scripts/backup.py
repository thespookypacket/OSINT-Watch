"""Create a consistent database dump; configuration/secrets must be backed up separately."""

import argparse
import os
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("path", type=Path)
args = parser.parse_args()
args.path.parent.mkdir(parents=True, exist_ok=True)
fd = os.open(args.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    with os.fdopen(fd, "wb") as output:
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "db",
                "pg_dump",
                "-U",
                "watch",
                "-d",
                "watch",
                "-Fc",
            ],
            stdout=output,
            check=True,
        )
except BaseException:
    args.path.unlink(missing_ok=True)
    raise
print(f"Backup saved: {args.path}")
