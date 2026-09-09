"""Per-request server duration and database query counts.

Audit finding B13 recorded signed-in navigations of roughly 8-19 seconds,
but was careful that those figures came through browser automation and are
"not instrumented browser performance metrics". This module supplies the
missing server-side half so the beta dataset can be measured rather than
estimated: how long the handler took, how many queries it issued, and how
much of the time those queries accounted for.

Off unless `REQUEST_TIMING_ENABLED` is set, and it only ever writes a log
line -- no request behaviour changes either way.
"""

from __future__ import annotations

import json
import logging
import time

from flask import g, request
from sqlalchemy import event

logger = logging.getLogger("icc.timing")


def _register_query_counter(engine) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        conn.info.setdefault("query_start_time", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        started = conn.info.get("query_start_time")
        elapsed = time.perf_counter() - started.pop() if started else 0.0
        if not hasattr(g, "_query_count"):
            return  # a query outside a request context: CLI, migration, job
        g._query_count += 1
        g._query_seconds += elapsed


def register_request_timing(app, db) -> None:
    if not app.config.get("REQUEST_TIMING_ENABLED"):
        return

    slow_threshold_ms = app.config.get("REQUEST_TIMING_SLOW_MS", 0)

    with app.app_context():
        _register_query_counter(db.engine)

    @app.before_request
    def _start_timer():
        g._request_start = time.perf_counter()
        g._query_count = 0
        g._query_seconds = 0.0

    @app.after_request
    def _log_timing(response):
        started = getattr(g, "_request_start", None)
        if started is None:
            return response
        duration_ms = (time.perf_counter() - started) * 1000
        if duration_ms < slow_threshold_ms:
            return response
        logger.info(json.dumps({
            "event": "request_timing",
            "endpoint": request.endpoint,
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": round(duration_ms, 1),
            "query_count": getattr(g, "_query_count", 0),
            "query_ms": round(getattr(g, "_query_seconds", 0.0) * 1000, 1),
        }))
        return response
