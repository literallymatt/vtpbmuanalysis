"""Direct SQLite data access, auto-extraction, CSV/Markdown exports, and background Elexon sync."""

from __future__ import annotations

import asyncio
import csv
import io
import shutil
import threading
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend.analytics import (
    get_compensation as _get_compensation,
    get_explorer as _get_explorer,
    get_overview as _get_overview,
    get_parties as _get_parties,
    get_status as _get_status,
    get_timing as _get_timing,
)
from backend.baseline_audit import (
    build_sbmu_audit_csv_rows as _build_sbmu_audit_csv_rows,
    compute_baseline_audit as _compute_baseline_audit,
    render_policy_briefing_md as _render_policy_briefing_md,
)
from backend.db import DEFAULT_DB_PATH, get_conn, get_db_path, init_db
from backend.forensics import compute_forensics as _compute_forensics
from backend.ingest import IngestProgress, ingest_date_range, sync_reference_data

# ---------------------------------------------------------------------------
# Database bootstrap (auto-extract bundled zip on first run)
# ---------------------------------------------------------------------------

_db_init_lock = threading.Lock()


def ensure_db_ready(db_path: Path | None = None) -> Path:
    """Ensure the SQLite database exists (extracting data/vtp_analysis_db.zip if needed) and is migrated."""
    with _db_init_lock:
        path = Path(db_path) if db_path is not None else get_db_path()
        if not path.exists():
            zip_candidates = [
                path.parent / "vtp_analysis_db.zip",
                DEFAULT_DB_PATH.parent / "vtp_analysis_db.zip",
            ]
            for zip_path in zip_candidates:
                if zip_path.is_file():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path = path.with_suffix(".db.extracting")
                    try:
                        with zipfile.ZipFile(zip_path, "r") as zf:
                            db_members = [
                                m for m in zf.namelist() if m.endswith(".db")
                            ]
                            member = (
                                "vtp_analysis.db"
                                if "vtp_analysis.db" in db_members
                                else (db_members[0] if db_members else None)
                            )
                            if member is not None:
                                with zf.open(member) as src, open(
                                    tmp_path, "wb"
                                ) as dst:
                                    shutil.copyfileobj(src, dst)
                                tmp_path.replace(path)
                    finally:
                        if tmp_path.exists():
                            tmp_path.unlink(missing_ok=True)
                    break
        init_db(path)
        return path


# ---------------------------------------------------------------------------
# Date window resolvers
# ---------------------------------------------------------------------------


def resolve_date_window(
    start_date: str | None = None,
    end_date: str | None = None,
    db_path: Path | None = None,
) -> tuple[str, str]:
    """Return (start_date, end_date) defaulting to the granular BMU×SP coverage in SQLite."""
    if start_date and end_date:
        return start_date, end_date
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT MIN(settlement_date) AS min_d, MAX(settlement_date) AS max_d "
            "FROM ingested_days WHERE has_bmu_sp = 1"
        ).fetchone()
        default_start = row["min_d"] or "2026-10-01"
        default_end = row["max_d"] or "2026-10-30"
    return start_date or default_start, end_date or default_end


def resolve_baseline_window(
    start_date: str | None = None,
    end_date: str | None = None,
    db_path: Path | None = None,
) -> tuple[str, str]:
    """Return (start_date, end_date) defaulting to the SBMU baseline coverage in SQLite."""
    if start_date and end_date:
        return start_date, end_date
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT MIN(settlement_date) AS min_d, MAX(settlement_date) AS max_d "
            "FROM ingested_days WHERE has_sbmu_baselines = 1"
        ).fetchone()
        min_d, max_d = row["min_d"], row["max_d"]
        if not min_d or not max_d:
            fb = conn.execute(
                "SELECT MIN(settlement_date) AS min_d, MAX(settlement_date) AS max_d "
                "FROM sbmu_baseline_sp"
            ).fetchone()
            min_d = min_d or fb["min_d"]
            max_d = max_d or fb["max_d"]
        if not min_d or not max_d:
            gran = conn.execute(
                "SELECT MIN(settlement_date) AS min_d, MAX(settlement_date) AS max_d "
                "FROM ingested_days WHERE has_bmu_sp = 1"
            ).fetchone()
            min_d = min_d or gran["min_d"] or "2026-10-01"
            max_d = max_d or gran["max_d"] or "2026-10-30"
    return start_date or min_d, end_date or max_d


# ---------------------------------------------------------------------------
# Thread-safe background Elexon sync runner
# ---------------------------------------------------------------------------

_sync_lock = threading.Lock()
_sync_state = IngestProgress()
_sync_thread: threading.Thread | None = None


def get_sync_progress() -> dict[str, Any]:
    """Return a snapshot dict of the current background sync state."""
    with _sync_lock:
        return asdict(_sync_state)


def start_sync_dates(
    start_date: str,
    end_date: str,
    include_bmu_sp: bool = True,
    include_baselines: bool = False,
    force: bool = False,
) -> tuple[bool, str]:
    """Launch background Elexon SAA-I014 ingestion in a daemon thread."""
    global _sync_state, _sync_thread
    if not start_date or not end_date:
        return False, "Both start_date and end_date are required."
    if start_date > end_date:
        return False, "Start date must be on or before end date."

    with _sync_lock:
        if _sync_state.status == "running":
            return False, "A sync job is already running."
        _sync_state = IngestProgress(
            status="running",
            message=f"Starting sync for {start_date} to {end_date}...",
        )

    def _update(progress: IngestProgress) -> None:
        global _sync_state
        with _sync_lock:
            _sync_state = progress

    def _worker() -> None:
        global _sync_state
        try:
            asyncio.run(
                ingest_date_range(
                    start_date,
                    end_date,
                    include_bmu_sp=include_bmu_sp,
                    include_baselines=include_baselines,
                    force=force,
                    progress_cb=_update,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            with _sync_lock:
                _sync_state.status = "error"
                _sync_state.message = f"Sync failed: {exc}"

    _sync_thread = threading.Thread(target=_worker, name="elexon-sync", daemon=True)
    _sync_thread.start()
    return True, f"Ingestion started for {start_date} to {end_date}. Progress appears in the top bar."


def run_sync_reference() -> dict[str, Any]:
    """Synchronously refresh BSC Signatories and BMRS BMUs from Elexon."""
    counts = asyncio.run(sync_reference_data())
    return {"status": "ok", **counts}


# ---------------------------------------------------------------------------
# Analytics & Forensics wrappers
# ---------------------------------------------------------------------------


def get_status(db_path: Path | None = None) -> dict[str, Any]:
    """Return DB coverage stats plus live sync progress."""
    with get_conn(db_path) as conn:
        status = _get_status(conn)
    return {**status, "sync": get_sync_progress()}


def get_overview(
    start_date: str | None = None,
    end_date: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    s, e = resolve_date_window(start_date, end_date, db_path=db_path)
    with get_conn(db_path) as conn:
        return _get_overview(conn, s, e)


def get_timing(
    start_date: str | None = None,
    end_date: str | None = None,
    sec_party_id: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    s, e = resolve_date_window(start_date, end_date, db_path=db_path)
    with get_conn(db_path) as conn:
        return _get_timing(conn, s, e, sec_party_id=sec_party_id or None)


def get_compensation(
    start_date: str | None = None,
    end_date: str | None = None,
    sec_party_id: str | None = None,
    pri_party_id: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    s, e = resolve_date_window(start_date, end_date, db_path=db_path)
    with get_conn(db_path) as conn:
        return _get_compensation(
            conn,
            s,
            e,
            sec_party_id=sec_party_id or None,
            pri_party_id=pri_party_id or None,
        )


def compute_forensics(
    start_date: str | None = None,
    end_date: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    s, e = resolve_date_window(start_date, end_date, db_path=db_path)
    with get_conn(db_path) as conn:
        return _compute_forensics(conn, s, e)


def compute_baseline_audit(
    start_date: str | None = None,
    end_date: str | None = None,
    sec_party_id: str | None = None,
    sec_bmu_id: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    s, e = resolve_baseline_window(start_date, end_date, db_path=db_path)
    with get_conn(db_path) as conn:
        return _compute_baseline_audit(
            conn,
            s,
            e,
            sec_party_id=sec_party_id or None,
            sec_bmu_id=sec_bmu_id or None,
        )


def build_sbmu_audit_csv_rows(
    start_date: str | None = None,
    end_date: str | None = None,
    sec_party_id: str | None = None,
    sec_bmu_id: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    s, e = resolve_baseline_window(start_date, end_date, db_path=db_path)
    with get_conn(db_path) as conn:
        return _build_sbmu_audit_csv_rows(
            conn,
            s,
            e,
            sec_party_id=sec_party_id or None,
            sec_bmu_id=sec_bmu_id or None,
        )


def render_policy_briefing_md(audit_data: dict[str, Any]) -> str:
    return _render_policy_briefing_md(audit_data)


def export_baseline_audit_csv(
    start_date: str | None = None,
    end_date: str | None = None,
    sec_party_id: str | None = None,
    sec_bmu_id: str | None = None,
    db_path: Path | None = None,
) -> tuple[str, str]:
    """Return (filename, csv_content) for the SBMU Baseline Audit CSV download."""
    s, e = resolve_baseline_window(start_date, end_date, db_path=db_path)
    rows = build_sbmu_audit_csv_rows(
        s, e, sec_party_id=sec_party_id, sec_bmu_id=sec_bmu_id, db_path=db_path
    )
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buf.write(
            "start_date,end_date,party_id,company_name,sec_bmu_id,gsp_group,methodology_class\n"
        )
    filename = f"vtp_baseline_audit_{s}_to_{e}.csv"
    return filename, buf.getvalue()


def export_baseline_briefing_md(
    start_date: str | None = None,
    end_date: str | None = None,
    sec_party_id: str | None = None,
    sec_bmu_id: str | None = None,
    db_path: Path | None = None,
) -> tuple[str, str]:
    """Return (filename, markdown_content) for the Policy Briefing Markdown download."""
    s, e = resolve_baseline_window(start_date, end_date, db_path=db_path)
    audit_data = compute_baseline_audit(
        s, e, sec_party_id=sec_party_id, sec_bmu_id=sec_bmu_id, db_path=db_path
    )
    md_text = render_policy_briefing_md(audit_data)
    filename = f"vtp_baseline_policy_briefing_{s}_to_{e}.md"
    return filename, md_text


def get_explorer(
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: str = "bmu_pair",
    sec_party_id: str | None = None,
    pri_party_id: str | None = None,
    gsp_group: str | None = None,
    sp: int | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
    db_path: Path | None = None,
) -> dict[str, Any]:
    s, e = resolve_date_window(start_date, end_date, db_path=db_path)
    with get_conn(db_path) as conn:
        return _get_explorer(
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


def export_explorer_csv(
    start_date: str | None = None,
    end_date: str | None = None,
    group_by: str = "bmu_pair",
    sec_party_id: str | None = None,
    pri_party_id: str | None = None,
    gsp_group: str | None = None,
    sp: int | None = None,
    search: str | None = None,
    db_path: Path | None = None,
) -> tuple[str, str]:
    """Return (filename, csv_content) for the Explorer CSV download."""
    s, e = resolve_date_window(start_date, end_date, db_path=db_path)
    data = get_explorer(
        s,
        e,
        group_by=group_by,
        sec_party_id=sec_party_id,
        pri_party_id=pri_party_id,
        gsp_group=gsp_group,
        sp=sp,
        search=search,
        limit=10000,
        offset=0,
        db_path=db_path,
    )
    buf = io.StringIO()
    items = data.get("items", [])
    if items:
        writer = csv.DictWriter(buf, fieldnames=list(items[0].keys()))
        writer.writeheader()
        writer.writerows(items)
    filename = f"vtp_bmu_{group_by}_{s}_to_{e}.csv"
    return filename, buf.getvalue()


def get_parties(
    role: str | None = None,
    search: str | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    with get_conn(db_path) as conn:
        return _get_parties(conn, role=role or None, search=search or None)
