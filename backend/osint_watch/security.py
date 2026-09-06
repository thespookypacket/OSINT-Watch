import hashlib
import secrets
from datetime import timedelta
from typing import Any

from argon2 import PasswordHasher
from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Connection

from .config import settings
from .db import connection, required_row
from .models import now

hasher = PasswordHasher()
bearer_scheme = HTTPBearer(auto_error=False)
cookie_scheme = APIKeyCookie(name="watch_session", auto_error=False)


def bootstrap_user(conn: Connection[Any]) -> None:
    cfg = settings()
    if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
        return
    if len(cfg.admin_password) < 12:
        raise RuntimeError(
            "Set WATCH_ADMIN_PASSWORD to at least 12 characters before first startup"
        )
    conn.execute(
        "INSERT INTO users VALUES (%s,%s)", (cfg.admin_username, hasher.hash(cfg.admin_password))
    )


def issue_token(
    conn: Connection[Any], name: str, scopes: list[str], days: float, kind: str = "api"
) -> dict[str, Any]:
    token = "ow_" + secrets.token_urlsafe(32)
    row = required_row(
        conn.execute(
            "INSERT INTO credentials(name,digest,scopes,kind,expires_at) VALUES (%s,%s,%s,%s,%s) RETURNING id,expires_at",
            (
                name,
                hashlib.sha256(token.encode()).hexdigest(),
                scopes,
                kind,
                now() + timedelta(days=days),
            ),
        ).fetchone()
    )
    return {**row, "token": token, "scopes": scopes}


def rate_limit(conn: Connection[Any], key: str, limit: int) -> None:
    row = required_row(
        conn.execute(
            """INSERT INTO rate_limits(key,count) VALUES (%s,1) ON CONFLICT(key)
        DO UPDATE SET count=CASE WHEN rate_limits.window_at < now()-interval '1 minute' THEN 1 ELSE rate_limits.count+1 END,
        window_at=CASE WHEN rate_limits.window_at < now()-interval '1 minute' THEN now() ELSE rate_limits.window_at END
        RETURNING count""",
            (key,),
        ).fetchone()
    )
    if row["count"] > limit:
        conn.commit()
        raise HTTPException(
            429, "Request limit exceeded; retry in one minute", headers={"Retry-After": "60"}
        )


def require(scope: str = "read"):
    def dependency(
        request: Request,
        _bearer: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        _session: str | None = Depends(cookie_scheme),
    ) -> dict[str, Any]:
        authorization = request.headers.get("authorization", "")
        bearer = authorization[7:] if authorization.startswith("Bearer ") else None
        token = bearer or request.cookies.get("watch_session")
        if not token:
            raise HTTPException(401, "Sign in or supply a Bearer API token")
        if not bearer and request.method not in {"GET", "HEAD", "OPTIONS"}:
            if request.headers.get("origin") != settings().public_url.rstrip("/"):
                raise HTTPException(403, "Origin does not match WATCH_PUBLIC_URL")
        with connection() as conn:
            credential = conn.execute(
                "SELECT id,scopes,kind FROM credentials WHERE digest=%s AND revoked_at IS NULL AND expires_at>now()",
                (hashlib.sha256(token.encode()).hexdigest(),),
            ).fetchone()
            if not credential:
                raise HTTPException(401, "Credential expired or revoked")
            if scope not in credential["scopes"] and "admin" not in credential["scopes"]:
                raise HTTPException(403, f"This operation requires the {scope} scope")
            rate_limit(conn, str(credential["id"]), 300)
            return credential

    return dependency


def audit(conn: Connection[Any], actor: Any, action: str, object_id: Any = None) -> None:
    conn.execute(
        "INSERT INTO audit_log(actor,action,object_id) VALUES (%s,%s,%s)",
        (str(actor), action, str(object_id) if object_id is not None else None),
    )
