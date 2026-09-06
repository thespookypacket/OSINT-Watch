from .db import connection

with connection() as conn:
    healthy = conn.execute(
        "SELECT 1 FROM worker_health WHERE id='worker' AND heartbeat>now()-interval '20 minutes'"
    ).fetchone()
    raise SystemExit(0 if healthy else 1)
