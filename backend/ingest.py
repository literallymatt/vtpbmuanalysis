"""Async Elexon SAA-I014, BMRS BMU, and BSC Signatories ingestion pipeline."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from .db import get_conn, init_db
from .elexon import (
    RUN_TYPE_PRIORITY,
    extract_gsp_group,
    fetch_bmu_reference,
    fetch_bsc_signatories,
    fetch_i014_dataset,
    resolve_best_run_type,
)

RUN_RANK = {rt: i for i, rt in enumerate(RUN_TYPE_PRIORITY)}


@dataclass
class IngestProgress:
    status: str = "idle"
    total_days: int = 0
    completed_days: int = 0
    skipped_days: int = 0
    failed_days: list[str] = field(default_factory=list)
    current_date: str = ""
    message: str = ""
    started_at: str = ""
    finished_at: str = ""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _safe_float(val: object, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


async def sync_reference_data(
    client: httpx.AsyncClient | None = None,
    db_path: Path | None = None,
) -> dict[str, int]:
    """Fetch and persist live BSC Signatories and BMRS BM Unit reference data."""
    init_db(db_path)
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(follow_redirects=True)
    try:
        signatories, bmus = await asyncio.gather(
            fetch_bsc_signatories(client),
            fetch_bmu_reference(client),
        )
    finally:
        if owns_client:
            await client.aclose()

    now = _utc_now()
    with get_conn(db_path) as conn:
        for s in signatories:
            conn.execute(
                """
                INSERT INTO parties (
                    party_id, company_name, address, roles_json,
                    is_vtp, is_vlp, is_amvlp, is_supplier, source, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'bsc_signatories', ?)
                ON CONFLICT(party_id) DO UPDATE SET
                    company_name = excluded.company_name,
                    address = excluded.address,
                    roles_json = excluded.roles_json,
                    is_vtp = excluded.is_vtp,
                    is_vlp = excluded.is_vlp,
                    is_amvlp = excluded.is_amvlp,
                    is_supplier = excluded.is_supplier,
                    source = 'bsc_signatories',
                    updated_at = excluded.updated_at
                """,
                (
                    s.party_id,
                    s.company_name,
                    s.address,
                    json.dumps(s.roles),
                    int(s.is_vtp),
                    int(s.is_vlp),
                    int(s.is_amvlp),
                    int(s.is_supplier),
                    now,
                ),
            )

        bmu_rows = []
        fallback_parties: dict[str, str] = {}
        for b in bmus:
            elexon_id = b.get("elexonBmUnit")
            if not elexon_id:
                continue
            lead_id = (b.get("leadPartyId") or "").strip()
            lead_name = (b.get("leadPartyName") or "").strip()
            if lead_id and lead_name:
                fallback_parties[lead_id] = lead_name
            bmu_rows.append(
                (
                    elexon_id,
                    b.get("nationalGridBmUnit"),
                    b.get("bmUnitName"),
                    b.get("bmUnitType"),
                    lead_id,
                    lead_name,
                    b.get("fuelType"),
                    b.get("gspGroupId"),
                    b.get("gspGroupName"),
                    _safe_float(b.get("demandCapacity")),
                    _safe_float(b.get("generationCapacity")),
                    b.get("productionOrConsumptionFlag"),
                )
            )

        conn.executemany(
            """
            INSERT INTO bmus (
                elexon_bmu_id, national_grid_bmu_id, bmu_name, bmu_type,
                lead_party_id, lead_party_name, fuel_type, gsp_group_id,
                gsp_group_name, demand_capacity, generation_capacity, pc_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(elexon_bmu_id) DO UPDATE SET
                national_grid_bmu_id = excluded.national_grid_bmu_id,
                bmu_name = excluded.bmu_name,
                bmu_type = excluded.bmu_type,
                lead_party_id = excluded.lead_party_id,
                lead_party_name = excluded.lead_party_name,
                fuel_type = excluded.fuel_type,
                gsp_group_id = excluded.gsp_group_id,
                gsp_group_name = excluded.gsp_group_name,
                demand_capacity = excluded.demand_capacity,
                generation_capacity = excluded.generation_capacity,
                pc_flag = excluded.pc_flag
            """,
            bmu_rows,
        )

        # Backfill any party IDs that exist in BMRS BMU reference but not signatories
        for pid, pname in fallback_parties.items():
            conn.execute(
                """
                INSERT OR IGNORE INTO parties (
                    party_id, company_name, address, roles_json,
                    is_vtp, is_vlp, is_amvlp, is_supplier, source, updated_at
                ) VALUES (?, ?, '', '[]', 0, 0, 0, 0, 'bmrs_reference', ?)
                """,
                (pid, pname, now),
            )

    return {"signatories": len(signatories), "bmus": len(bmu_rows)}


def _should_skip_day(
    settlement_date: str,
    include_bmu_sp: bool,
    force: bool,
    db_path: Path | None = None,
) -> bool:
    if force:
        return False
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT run_type, has_bmu_sp, has_party_level, has_sp_level "
            "FROM ingested_days WHERE settlement_date = ?",
            (settlement_date,),
        ).fetchone()
        if not row:
            return False
        if include_bmu_sp and not row["has_bmu_sp"]:
            return False
        return bool(row["has_party_level"] and row["has_sp_level"])


async def ingest_day(
    client: httpx.AsyncClient,
    settlement_date: str,
    include_bmu_sp: bool = True,
    force: bool = False,
    db_path: Path | None = None,
) -> dict[str, object]:
    """Fetch and store SAA-I014 data for a single settlement date."""
    if _should_skip_day(settlement_date, include_bmu_sp, force, db_path):
        return {"date": settlement_date, "status": "skipped"}

    resolved = await resolve_best_run_type(client, settlement_date)
    if resolved is None:
        return {"date": settlement_date, "status": "unavailable"}

    run_type, party_payload = resolved
    tasks = [
        fetch_i014_dataset(client, "settlement-period-level", settlement_date, run_type)
    ]
    if include_bmu_sp:
        tasks.append(
            fetch_i014_dataset(
                client, "primary-secondary-bm-unit-level", settlement_date, run_type
            )
        )
    results = await asyncio.gather(*tasks)
    sp_payload = results[0]
    ps_payload = results[1] if include_bmu_sp else None

    header = party_payload.get("settlementReportHeader", {})
    created_dt = header.get("createdDateTime", "")
    now = _utc_now()

    # Build SP market rows & SSC lookup
    ssc_by_sp: dict[int, float] = {}
    sp_rows = []
    for sp_item in sp_payload.get("settlementPeriods", []):
        sp_num = int(sp_item["sp"])
        info = sp_item.get("settlementPeriodInformation", {})
        ssc = _safe_float(info.get("ssc"))
        ssc_by_sp[sp_num] = ssc
        sp_rows.append(
            (
                settlement_date,
                sp_num,
                run_type,
                ssc,
                _safe_float(info.get("sbp")),
                _safe_float(info.get("ssp")),
                _safe_float(info.get("mpj")),
                _safe_float(info.get("totDemand")),
                _safe_float(info.get("totGen")),
                _safe_float(info.get("nivj")),
                _safe_float(info.get("qcvj")),
                _safe_float(info.get("sccj")),
                _safe_float(info.get("scvj")),
                _safe_float(info.get("sdcj")),
                _safe_float(info.get("cmpj")),
            )
        )

    # Party daily settlement rows (only persist active/non-zero compensation or imbalance)
    party_rows = []
    for p in party_payload.get("bscParties", []):
        sccp = _safe_float(p.get("sccp"))
        scvp = _safe_float(p.get("scvp"))
        caeip = _safe_float(p.get("caeip"))
        cbmp = _safe_float(p.get("cbmp"))
        rcrcp = _safe_float(p.get("rcrcp"))
        cndp = _safe_float(p.get("cndp"))
        if any(abs(v) > 1e-6 for v in (sccp, scvp, caeip, cbmp, rcrcp, cndp)):
            party_rows.append(
                (
                    settlement_date,
                    p["bscPartyId"],
                    run_type,
                    sccp,
                    scvp,
                    caeip,
                    cbmp,
                    rcrcp,
                    cndp,
                )
            )

    # Granular Primary-Secondary BMU × SP rows
    bmu_sp_rows = []
    if ps_payload is not None:
        for pair in ps_payload.get("primarySecondaryBMUnits", []):
            pri_party = pair.get("priBscPartyId") or ""
            pri_bmu = pair.get("priBmuId") or ""
            sec_party = pair.get("secBscPartyId") or ""
            sec_bmu = pair.get("secBmuId") or ""
            gsp = extract_gsp_group(sec_bmu) or extract_gsp_group(pri_bmu)
            for row in pair.get("primarySecondaryBMUnitLevelData", []):
                sp_num = int(row["sp"])
                vbmusdv = _safe_float(row.get("vbmusdviji2"))
                sp_prop = _safe_float(row.get("spiji2"))
                qsd = _safe_float(row.get("qsdiji2"))
                qcv = _safe_float(row.get("qcviji2"))
                if abs(qcv) < 1e-9 and abs(qsd) < 1e-9 and abs(vbmusdv) < 1e-9:
                    continue
                ssc = ssc_by_sp.get(sp_num, 0.0)
                bmu_sp_rows.append(
                    (
                        settlement_date,
                        sp_num,
                        pri_bmu,
                        sec_bmu,
                        run_type,
                        pri_party,
                        sec_party,
                        gsp,
                        vbmusdv,
                        sp_prop,
                        qsd,
                        qcv,
                        ssc,
                        qcv * ssc,
                    )
                )

    with get_conn(db_path) as conn:
        conn.execute(
            "DELETE FROM sp_market_data WHERE settlement_date = ?", (settlement_date,)
        )
        conn.executemany(
            """
            INSERT INTO sp_market_data (
                settlement_date, sp, run_type, ssc, sbp, ssp, mpj,
                tot_demand, tot_gen, nivj, qcvj, sccj, scvj, sdcj, cmpj
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sp_rows,
        )

        conn.execute(
            "DELETE FROM party_daily_settlement WHERE settlement_date = ?",
            (settlement_date,),
        )
        conn.executemany(
            """
            INSERT INTO party_daily_settlement (
                settlement_date, party_id, run_type, sccp, scvp, caeip, cbmp, rcrcp, cndp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            party_rows,
        )

        if ps_payload is not None:
            conn.execute(
                "DELETE FROM bmu_sp_compensation WHERE settlement_date = ?",
                (settlement_date,),
            )
            conn.executemany(
                """
                INSERT INTO bmu_sp_compensation (
                    settlement_date, sp, pri_bmu_id, sec_bmu_id, run_type,
                    pri_party_id, sec_party_id, gsp_group,
                    vbmusdv, sp_proportion, qsd, qcv, ssc, comp_cashflow
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                bmu_sp_rows,
            )

        existing = conn.execute(
            "SELECT has_bmu_sp FROM ingested_days WHERE settlement_date = ?",
            (settlement_date,),
        ).fetchone()
        has_bmu_sp = 1 if (ps_payload is not None or (existing and existing["has_bmu_sp"])) else 0

        conn.execute(
            """
            INSERT INTO ingested_days (
                settlement_date, run_type, has_bmu_sp, has_party_level,
                has_sp_level, created_date_time, ingested_at
            ) VALUES (?, ?, ?, 1, 1, ?, ?)
            ON CONFLICT(settlement_date) DO UPDATE SET
                run_type = excluded.run_type,
                has_bmu_sp = MAX(ingested_days.has_bmu_sp, excluded.has_bmu_sp),
                has_party_level = 1,
                has_sp_level = 1,
                created_date_time = excluded.created_date_time,
                ingested_at = excluded.ingested_at
            """,
            (settlement_date, run_type, has_bmu_sp, created_dt, now),
        )

    return {
        "date": settlement_date,
        "status": "ingested",
        "run_type": run_type,
        "bmu_sp_rows": len(bmu_sp_rows),
        "party_rows": len(party_rows),
    }


def date_list(start_date: str, end_date: str, step_days: int = 1) -> list[str]:
    start = dt.date.fromisoformat(start_date)
    end = dt.date.fromisoformat(end_date)
    out: list[str] = []
    cur = start
    while cur <= end:
        out.append(cur.isoformat())
        cur += dt.timedelta(days=step_days)
    return out


async def ingest_date_range(
    start_date: str,
    end_date: str,
    include_bmu_sp: bool = True,
    step_days: int = 1,
    concurrency: int = 4,
    force: bool = False,
    db_path: Path | None = None,
    progress_cb: Callable[[IngestProgress], None] | None = None,
) -> IngestProgress:
    """Ingest a range of settlement dates concurrently with polite rate limits."""
    init_db(db_path)
    dates = date_list(start_date, end_date, step_days)
    prog = IngestProgress(
        status="running",
        total_days=len(dates),
        started_at=_utc_now(),
        message=f"Syncing {len(dates)} settlement days ({start_date} to {end_date})",
    )
    if progress_cb:
        progress_cb(prog)

    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def _worker(d: str) -> None:
            async with sem:
                prog.current_date = d
                try:
                    res = await ingest_day(
                        client,
                        d,
                        include_bmu_sp=include_bmu_sp,
                        force=force,
                        db_path=db_path,
                    )
                    if res["status"] == "skipped":
                        prog.skipped_days += 1
                    elif res["status"] == "unavailable":
                        prog.failed_days.append(f"{d} (not published yet)")
                except Exception as exc:  # noqa: BLE001
                    prog.failed_days.append(f"{d} ({type(exc).__name__})")
                finally:
                    prog.completed_days += 1
                    if progress_cb:
                        progress_cb(prog)

        await asyncio.gather(*(_worker(d) for d in dates))

    prog.status = "completed"
    prog.finished_at = _utc_now()
    prog.message = (
        f"Processed {prog.completed_days}/{prog.total_days} days "
        f"({prog.skipped_days} cached, {len(prog.failed_days)} unavailable/failed)."
    )
    if progress_cb:
        progress_cb(prog)
    return prog


async def _cli_main() -> None:
    parser = argparse.ArgumentParser(description="Ingest live Elexon SAA-I014 VTP data.")
    parser.add_argument("--sync-ref", action="store_true", help="Sync BSC Signatories & BMUs")
    parser.add_argument("--start", type=str, help="Start settlement date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End settlement date (YYYY-MM-DD)")
    parser.add_argument(
        "--macro-only",
        action="store_true",
        help="Only ingest party-level + SP-level (skip large BMU×SP files)",
    )
    parser.add_argument("--step", type=int, default=1, help="Day step interval (default 1)")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    init_db()
    if args.sync_ref:
        counts = await sync_reference_data()
        print(f"Reference sync complete: {counts}")

    if args.start and args.end:
        def _log(p: IngestProgress) -> None:
            if p.completed_days % 5 == 0 or p.completed_days == p.total_days:
                print(
                    f"[{p.completed_days}/{p.total_days}] latest={p.current_date} "
                    f"skipped={p.skipped_days} failed={len(p.failed_days)}"
                )

        res = await ingest_date_range(
            args.start,
            args.end,
            include_bmu_sp=not args.macro_only,
            step_days=args.step,
            concurrency=args.concurrency,
            force=args.force,
            progress_cb=_log,
        )
        print(res.message)


if __name__ == "__main__":
    asyncio.run(_cli_main())
