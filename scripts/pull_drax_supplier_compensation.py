"""Pull all daily Elexon SAA-I014 party-level cashflows for HAVEN (Drax Energy Solutions)
from P415 go-live (2024-11-07) through the latest settled date and write
reports/drax_haven_daily_sccp.csv.
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import sqlite3
import zipfile
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
SAA_BASE_URL = "https://data.elexon.co.uk/saa/api/v1/i014"
START_DATE = dt.date(2024, 11, 7)
PARTY_ID = "HAVEN"

OUT_CSV = REPO_ROOT / "reports" / "drax_haven_daily_sccp.csv"
DB_PATH = REPO_ROOT / "data" / "vtp_analysis.db"
DB_ZIP = REPO_ROOT / "data" / "vtp_analysis_db.zip"

# Verified quarterly Supplier Sourcing Cost (£/MWh) from Elexon SAA-I014 settlement-period-level
QUARTERLY_SSC: dict[tuple[int, int], float] = {
    (2024, 4): 93.15,
    (2025, 1): 91.58,
    (2025, 2): 99.95,
    (2025, 3): 90.91,
    (2025, 4): 89.47,
    (2026, 1): 87.21,
    (2026, 2): 82.26,
    (2026, 3): 98.53,
    (2026, 4): 106.47,
}


def ssc_for_date(date_str: str) -> float:
    d = dt.date.fromisoformat(date_str)
    q = (d.month - 1) // 3 + 1
    return QUARTERLY_SSC[(d.year, q)]


def preferred_runs(date_str: str) -> tuple[str, ...]:
    age = (dt.date.today() - dt.date.fromisoformat(date_str)).days
    if age >= 425:
        return ("RF", "R3", "R2", "R1", "SF", "II")
    if age >= 215:
        return ("R3", "RF", "R2", "R1", "SF", "II")
    if age >= 120:
        return ("R2", "R3", "R1", "SF", "RF", "II")
    if age >= 55:
        return ("R1", "R2", "SF", "R3", "II", "RF")
    if age >= 22:
        return ("SF", "R1", "II", "R2", "R3", "RF")
    return ("II", "SF", "R1", "R2", "R3", "RF")


def load_cached() -> dict[str, dict]:
    records: dict[str, dict] = {}
    if OUT_CSV.exists():
        with OUT_CSV.open(newline="") as f:
            for row in csv.DictReader(f):
                records[row["date"]] = {
                    "date": row["date"],
                    "run_type": row["run_type"],
                    "sccp": float(row["sccp"]),
                    "scvp": float(row["scvp"]),
                }
    db_file = DB_PATH
    tmp_db: Path | None = None
    if not db_file.exists() and DB_ZIP.exists():
        tmp_db = Path("/tmp/vtp_analysis_drax_cache.db")
        if not tmp_db.exists():
            with zipfile.ZipFile(DB_ZIP) as zf:
                name = next(n for n in zf.namelist() if n.endswith(".db"))
                tmp_db.write_bytes(zf.read(name))
        db_file = tmp_db
    if db_file.exists():
        conn = sqlite3.connect(db_file)
        for d, run_type, sccp, scvp in conn.execute(
            "SELECT settlement_date, run_type, sccp, scvp "
            "FROM party_daily_settlement WHERE party_id = ?",
            (PARTY_ID,),
        ):
            records.setdefault(
                d,
                {
                    "date": d,
                    "run_type": run_type,
                    "sccp": float(sccp or 0.0),
                    "scvp": float(scvp or 0.0),
                },
            )
        conn.close()
    return records


async def fetch_day(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, date_str: str
) -> dict | None:
    async with sem:
        for run_type in preferred_runs(date_str):
            url = f"{SAA_BASE_URL}/party-level/{date_str}/{run_type}"
            for attempt in range(4):
                try:
                    resp = await client.get(
                        url, headers={"Accept": "application/json"}, timeout=30.0
                    )
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt < 3:
                        await asyncio.sleep(0.8 * (attempt + 1))
                        continue
                    break
                if resp.status_code == 200:
                    payload = resp.json()
                    sccp = 0.0
                    scvp = 0.0
                    for p in payload.get("bscParties") or []:
                        if p.get("bscPartyId") == PARTY_ID:
                            sccp = float(p.get("sccp") or 0.0)
                            scvp = float(p.get("scvp") or 0.0)
                            break
                    return {
                        "date": date_str,
                        "run_type": run_type,
                        "sccp": sccp,
                        "scvp": scvp,
                    }
                if resp.status_code in (400, 404):
                    break
                if resp.status_code >= 500 or resp.status_code == 429:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                break
        return None


async def main() -> None:
    records = load_cached()
    end_date = dt.date.today() - dt.timedelta(days=1)
    all_dates: list[str] = []
    cur = START_DATE
    while cur <= end_date:
        all_dates.append(cur.isoformat())
        cur += dt.timedelta(days=1)

    missing = [d for d in all_dates if d not in records]
    print(
        f"Range: {START_DATE}..{end_date} ({len(all_dates)}d) | "
        f"Cached: {len(records)} | To fetch: {len(missing)}"
    )

    if missing:
        sem = asyncio.Semaphore(12)
        limits = httpx.Limits(max_connections=16, max_keepalive_connections=14)
        async with httpx.AsyncClient(limits=limits) as client:
            tasks = [fetch_day(client, sem, d) for d in missing]
            for coro in asyncio.as_completed(tasks):
                res = await coro
                if res is not None:
                    records[res["date"]] = res

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in sorted(records):
        r = records[d]
        ssc = ssc_for_date(d)
        implied_mwh = r["sccp"] / ssc if ssc else 0.0
        rows.append(
            {
                "date": d,
                "run_type": r["run_type"],
                "sccp": f"{r['sccp']:.4f}",
                "scvp": f"{r['scvp']:.4f}",
                "ssc": f"{ssc:.2f}",
                "implied_mwh": f"{implied_mwh:.4f}",
            }
        )

    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["date", "run_type", "sccp", "scvp", "ssc", "implied_mwh"]
        )
        writer.writeheader()
        writer.writerows(rows)

    pos_mwh = sum(float(r["implied_mwh"]) for r in rows if float(r["sccp"]) > 0.005)
    neg_mwh = sum(float(r["implied_mwh"]) for r in rows if float(r["sccp"]) < -0.005)
    tot_sccp = sum(float(r["sccp"]) for r in rows)
    tot_scvp = sum(float(r["scvp"]) for r in rows)
    print(f"Wrote {len(rows)} rows to {OUT_CSV}")
    print(
        f"Turn-Down: +{pos_mwh:,.2f} MWh | Turn-Up: {neg_mwh:,.2f} MWh | "
        f"Net sccp: £{tot_sccp:,.2f} | scvp: £{tot_scvp:,.2f}"
    )


if __name__ == "__main__":
    asyncio.run(main())
