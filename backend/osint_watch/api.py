import json
import logging
from contextlib import asynccontextmanager

from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg import sql

from .config import settings
from .db import connection, migrate
from .models import LoginIn
from .security import bootstrap_user, hasher, issue_token, rate_limit, require
from .worker import seed_sources


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    with connection() as conn:
        bootstrap_user(conn)
        if settings().gis_password:
            conn.execute(
                sql.SQL("ALTER ROLE watch_gis PASSWORD {}").format(
                    sql.Literal(settings().gis_password)
                )
            )
    seed_sources()
    yield


app = FastAPI(
    title="OSINT Watch API",
    version="0.1.0",
    lifespan=lifespan,
    description="Public-source hazard monitoring. All geographic coordinates are WGS84 longitude, latitude. Severity is 0 (unknown) to 4; source confidence is independent.",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        {"error": {"code": exc.status_code, "message": exc.detail}},
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logging.getLogger("watch.api").error(
        json.dumps({"event": "request_failed", "error_type": type(exc).__name__})
    )
    return JSONResponse(
        {"error": {"code": 500, "message": "Request failed. Check service health and retry."}},
        status_code=500,
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        {"error": {"code": 422, "message": "Check the supplied fields", "fields": errors}},
        status_code=422,
    )


@app.middleware("http")
async def response_headers(request: Request, call_next):
    if int(request.headers.get("content-length", "0")) > 5 * 1024 * 1024:
        return JSONResponse(
            {"error": {"code": 413, "message": "Request exceeds 5 MB"}}, status_code=413
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health():
    with connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/api/v1/auth/login")
def login(body: LoginIn, request: Request, response: Response):
    with connection() as conn:
        rate_limit(conn, "login:" + (request.client.host if request.client else "unknown"), 10)
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username=%s", (body.username,)).fetchone()
        try:
            valid = hasher.verify(user["password_hash"], body.password) if user else False
        except VerificationError:
            valid = False
        if not valid:
            raise HTTPException(401, "Username or password is incorrect")
        credential = issue_token(conn, body.username, ["admin"], 0.5, "session")
    response.set_cookie(
        "watch_session",
        credential["token"],
        httponly=True,
        secure=settings().secure_cookies,
        samesite="strict",
        max_age=43200,
        path="/",
    )
    return {"username": body.username}


@app.post("/api/v1/auth/logout")
def logout(response: Response, credential=Depends(require())):
    with connection() as conn:
        conn.execute("UPDATE credentials SET revoked_at=now() WHERE id=%s", (credential["id"],))
    response.delete_cookie("watch_session", path="/")
    return {"ok": True}


@app.get("/api/v1/auth/me")
def me(credential=Depends(require())):
    return {"scopes": credential["scopes"]}


@app.get("/api/v1/settings")
def public_settings(credential=Depends(require())):
    cfg = settings()
    return {
        "basemap_url": cfg.basemap_url,
        "ai_enabled": bool(cfg.ollama_url),
        "spiderfoot_enabled": bool(cfg.spiderfoot_url),
        "raw_retention_days": cfg.raw_retention_days,
        "retention_days": cfg.retention_days,
        "version": "0.1.0",
    }


@app.get("/api/v1/gis-auth", include_in_schema=False)
def gis_auth(credential=Depends(require())):
    return {"ok": True}


from .routes_events import router as events_router  # noqa: E402
from .routes_resources import router as resources_router  # noqa: E402

app.include_router(events_router, prefix="/api/v1")
app.include_router(resources_router, prefix="/api/v1")
