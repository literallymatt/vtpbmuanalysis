"""FastAPI server for GB VTP & Supplier Compensation Analytics."""

from __future__ import annotations

import asyncio
import csv
import io
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .analytics import (
    get_compensation,
    get_explorer,
    get_overview,
    get_parties,
    get_status,
    get_timing,
)
from .db import get_conn, init_db
from .forensics import compute_forensics
from .ingest import IngestProgress, ingest_date_range, sync_reference_data

@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(
    title="VTP Settlement Forensics API",
    version="0.1.0",
    lifespan=_lifespan,
    description=(
        "Analyses Great Britain Virtual Trading Party (P415) activities, supplier "
        "compensation flows, and EV baselining behaviour from Elexon SAA-I014 data."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_sync_state = IngestProgress()
_sync_lock = asyncio.Lock()


class SyncDatesRequest(BaseModel):
    start_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    include_bmu_sp: bool = True
    force: bool = False


def _resolve_date_window(
    start_date: str | None, end_date: str | None
) -> tuple[str, str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MIN(settlement_date) AS min_d, MAX(settlement_date) AS max_d "
            "FROM ingested_days WHERE has_bmu_sp = 1"
        ).fetchone()
        default_start = row["min_d"] or "2026-10-01"
        default_end = row["max_d"] or "2026-10-30"
    return start_date or default_start, end_date or default_end


@app.get("/api/status")
def api_status() -> dict[str, Any]:
    with get_conn() as conn:
        status = get_status(conn)
    return {**status, "sync": asdict(_sync_state)}


@app.get("/api/overview")
def api_overview(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict[str, Any]:
    s, e = _resolve_date_window(start_date, end_date)
    with get_conn() as conn:
        return get_overview(conn, s, e)


@app.get("/api/timing")
def api_timing(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    sec_party_id: str | None = Query(default=None),
) -> dict[str, Any]:
    s, e = _resolve_date_window(start_date, end_date)
    with get_conn() as conn:
        return get_timing(conn, s, e, sec_party_id=sec_party_id or None)


@app.get("/api/compensation")
def api_compensation(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    sec_party_id: str | None = Query(default=None),
    pri_party_id: str | None = Query(default=None),
) -> dict[str, Any]:
    s, e = _resolve_date_window(start_date, end_date)
    with get_conn() as conn:
        return get_compensation(
            conn,
            s,
            e,
            sec_party_id=sec_party_id or None,
            pri_party_id=pri_party_id or None,
        )


@app.get("/api/forensics")
def api_forensics(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict[str, Any]:
    s, e = _resolve_date_window(start_date, end_date)
    with get_conn() as conn:
        return compute_forensics(conn, s, e)


@app.get("/api/explorer")
def api_explorer(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    group_by: str = Query(default="bmu_pair", pattern="^(bmu_pair|raw)$"),
    sec_party_id: str | None = Query(default=None),
    pri_party_id: str | None = Query(default=None),
    gsp_group: str | None = Query(default=None),
    sp: int | None = Query(default=None, ge=1, le=50),
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    s, e = _resolve_date_window(start_date, end_date)
    with get_conn() as conn:
        return get_explorer(
            conn,
            s,
            e,
            group_by=group_by,
            sec_party_id=sec_party_id or None,
            pri_party_id=pri_party_id or None,
            gsp_group=gsp_group or None,
            sp=sp,
            search=search or None,
            limit=limit,
            offset=offset,
        )


@app.get("/api/explorer/export.csv")
def api_explorer_csv(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    group_by: str = Query(default="bmu_pair", pattern="^(bmu_pair|raw)$"),
    sec_party_id: str | None = Query(default=None),
    pri_party_id: str | None = Query(default=None),
    gsp_group: str | None = Query(default=None),
    sp: int | None = Query(default=None, ge=1, le=50),
    search: str | None = Query(default=None),
) -> StreamingResponse:
    s, e = _resolve_date_window(start_date, end_date)
    with get_conn() as conn:
        data = get_explorer(
            conn,
            s,
            e,
            group_by=group_by,
            sec_party_id=sec_party_id or None,
            pri_party_id=pri_party_id or None,
            gsp_group=gsp_group or None,
            sp=sp,
            search=search or None,
            limit=10000,
            offset=0,
        )
    buf = io.StringIO()
    items = data["items"]
    if items:
        writer = csv.DictWriter(buf, fieldnames=list(items[0].keys()))
        writer.writeheader()
        writer.writerows(items)
    buf.seek(0)
    filename = f"vtp_bmu_{group_by}_{s}_to_{e}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/parties")
def api_parties(
    role: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> dict[str, Any]:
    with get_conn() as conn:
        return get_parties(conn, role=role or None, search=search or None)


async def _run_sync_job(req: SyncDatesRequest) -> None:
    global _sync_state
    async with _sync_lock:
        def _update(p: IngestProgress) -> None:
            global _sync_state
            _sync_state = p

        await ingest_date_range(
            req.start_date,
            req.end_date,
            include_bmu_sp=req.include_bmu_sp,
            force=req.force,
            progress_cb=_update,
        )


@app.post("/api/sync/dates")
async def api_sync_dates(
    req: SyncDatesRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    if req.start_date > req.end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")
    if _sync_state.status == "running":
        raise HTTPException(status_code=409, detail="A sync job is already running")
    background_tasks.add_task(_run_sync_job, req)
    return {"accepted": True, "message": f"Started syncing {req.start_date} to {req.end_date}"}


@app.post("/api/sync/reference")
async def api_sync_reference() -> dict[str, Any]:
    counts = await sync_reference_data()
    return {"status": "ok", **counts}


@app.get("/api/sync/progress")
def api_sync_progress() -> dict[str, Any]:
    return asdict(_sync_state)


# Serve built frontend in production if present
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def _serve_spa(full_path: str) -> FileResponse:
        target = FRONTEND_DIST / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
