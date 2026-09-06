"""Private fixed-policy CLI bridge: never accept modules or shell arguments from callers."""

import ipaddress
import os
import re
import secrets
import subprocess
import tempfile
import threading

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(docs_url=None, openapi_url=None)
lock = threading.Lock()


class Scan(BaseModel):
    target: str
    asset_id: str


@app.post("/scan")
def scan(body: Scan, authorization: str = Header(default="")):
    token = os.environ.get("WATCH_SPIDERFOOT_TOKEN", "")
    if not token or not secrets.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(401)
    try:
        ipaddress.ip_address(body.target)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,251}[A-Za-z0-9]", body.target):
            raise HTTPException(422, "Invalid domain or IP") from None
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "A scan is already running")
    try:
        with tempfile.TemporaryFile() as output:
            result = subprocess.run(
                [
                    "python",
                    "sf.py",
                    "-s",
                    body.target,
                    "-u",
                    "passive",
                    "-o",
                    "json",
                    "-q",
                    "-max-threads",
                    "2",
                ],
                stdout=output,
                stderr=subprocess.DEVNULL,
                timeout=210,
                check=False,
            )
            if result.returncode:
                raise HTTPException(502, "SpiderFoot scan failed")
            output.seek(0)
            text = output.read(2_000_001)
            if len(text) > 2_000_000:
                raise HTTPException(502, "Scan output exceeds limit")
            return {
                "target": body.target,
                "mode": "passive",
                "output": text.decode("utf-8", errors="replace"),
            }
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Scan exceeded time limit") from None
    finally:
        lock.release()
