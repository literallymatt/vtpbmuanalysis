"""SQLite schema and connection management for Elexon SAA-I014 VTP analysis."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "vtp_analysis.db"


def get_db_path() -> Path:
    env_path = os.environ.get("VTP_DB_PATH")
    return Path(env_path) if env_path else DEFAULT_DB_PATH


def init_db(db_path: Path | None = None) -> None:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS parties (
                party_id TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                address TEXT DEFAULT '',
                roles_json TEXT DEFAULT '[]',
                is_vtp INTEGER DEFAULT 0,
                is_vlp INTEGER DEFAULT 0,
                is_amvlp INTEGER DEFAULT 0,
                is_supplier INTEGER DEFAULT 0,
                source TEXT DEFAULT 'bsc_signatories',
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bmus (
                elexon_bmu_id TEXT PRIMARY KEY,
                national_grid_bmu_id TEXT,
                bmu_name TEXT,
                bmu_type TEXT,
                lead_party_id TEXT,
                lead_party_name TEXT,
                fuel_type TEXT,
                gsp_group_id TEXT,
                gsp_group_name TEXT,
                demand_capacity REAL DEFAULT 0,
                generation_capacity REAL DEFAULT 0,
                pc_flag TEXT
            );

            CREATE TABLE IF NOT EXISTS ingested_days (
                settlement_date TEXT PRIMARY KEY,
                run_type TEXT NOT NULL,
                has_bmu_sp INTEGER DEFAULT 0,
                has_party_level INTEGER DEFAULT 0,
                has_sp_level INTEGER DEFAULT 0,
                created_date_time TEXT,
                ingested_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sp_market_data (
                settlement_date TEXT NOT NULL,
                sp INTEGER NOT NULL,
                run_type TEXT NOT NULL,
                ssc REAL DEFAULT 0,
                sbp REAL DEFAULT 0,
                ssp REAL DEFAULT 0,
                mpj REAL DEFAULT 0,
                tot_demand REAL DEFAULT 0,
                tot_gen REAL DEFAULT 0,
                nivj REAL DEFAULT 0,
                qcvj REAL DEFAULT 0,
                sccj REAL DEFAULT 0,
                scvj REAL DEFAULT 0,
                sdcj REAL DEFAULT 0,
                cmpj REAL DEFAULT 0,
                PRIMARY KEY (settlement_date, sp)
            );

            CREATE TABLE IF NOT EXISTS party_daily_settlement (
                settlement_date TEXT NOT NULL,
                party_id TEXT NOT NULL,
                run_type TEXT NOT NULL,
                sccp REAL DEFAULT 0,
                scvp REAL DEFAULT 0,
                caeip REAL DEFAULT 0,
                cbmp REAL DEFAULT 0,
                rcrcp REAL DEFAULT 0,
                cndp REAL DEFAULT 0,
                PRIMARY KEY (settlement_date, party_id)
            );

            CREATE TABLE IF NOT EXISTS bmu_sp_compensation (
                settlement_date TEXT NOT NULL,
                sp INTEGER NOT NULL,
                pri_bmu_id TEXT NOT NULL,
                sec_bmu_id TEXT NOT NULL,
                run_type TEXT NOT NULL,
                pri_party_id TEXT NOT NULL,
                sec_party_id TEXT NOT NULL,
                gsp_group TEXT DEFAULT '',
                vbmusdv REAL DEFAULT 0,
                sp_proportion REAL DEFAULT 0,
                qsd REAL DEFAULT 0,
                qcv REAL DEFAULT 0,
                ssc REAL DEFAULT 0,
                comp_cashflow REAL DEFAULT 0,
                PRIMARY KEY (settlement_date, sp, pri_bmu_id, sec_bmu_id)
            );

            CREATE INDEX IF NOT EXISTS idx_bmu_sp_date_sec
                ON bmu_sp_compensation (settlement_date, sec_party_id);
            CREATE INDEX IF NOT EXISTS idx_bmu_sp_date_pri
                ON bmu_sp_compensation (settlement_date, pri_party_id);
            CREATE INDEX IF NOT EXISTS idx_bmu_sp_sec_sp
                ON bmu_sp_compensation (sec_party_id, sp);
            CREATE INDEX IF NOT EXISTS idx_bmu_sp_sec_bmu
                ON bmu_sp_compensation (sec_bmu_id, settlement_date);
            CREATE INDEX IF NOT EXISTS idx_party_daily_party
                ON party_daily_settlement (party_id, settlement_date);
            CREATE INDEX IF NOT EXISTS idx_bmus_party
                ON bmus (lead_party_id);
            """
        )


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = db_path or get_db_path()
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
