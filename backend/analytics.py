"""Analytical query engine for VTP timing, supplier compensation, and BMU explorer."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import defaultdict
from typing import Any

from .elexon import GSP_GROUP_NAMES, ROLE_DESCRIPTIONS

REGULATORY_MILESTONES = [
    {
        "date": "2024-11-07",
        "code": "P415",
        "label": "P415 live (VTP wholesale access)",
    },
    {
        "date": "2026-08-21",
        "code": "P511",
        "label": "P511 approved (>10MW gen barred)",
    },
]


def _sp_to_time(sp: int) -> str:
    hh = ((sp - 1) // 2) % 24
    mm = "00" if (sp - 1) % 2 == 0 else "30"
    return f"{hh:02d}:{mm}"


def _load_party_map(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in conn.execute(
        "SELECT party_id, company_name, roles_json, is_vtp, is_vlp, is_amvlp, is_supplier FROM parties"
    ):
        out[r["party_id"]] = {
            "party_id": r["party_id"],
            "company_name": r["company_name"],
            "roles": json.loads(r["roles_json"] or "[]"),
            "is_vtp": bool(r["is_vtp"]),
            "is_vlp": bool(r["is_vlp"]),
            "is_amvlp": bool(r["is_amvlp"]),
            "is_supplier": bool(r["is_supplier"]),
        }
    return out


def get_status(conn: sqlite3.Connection) -> dict[str, Any]:
    gran = conn.execute(
        """
        SELECT COUNT(*) AS n, MIN(settlement_date) AS min_d, MAX(settlement_date) AS max_d
        FROM ingested_days WHERE has_bmu_sp = 1
        """
    ).fetchone()
    macro = conn.execute(
        """
        SELECT COUNT(*) AS n, MIN(settlement_date) AS min_d, MAX(settlement_date) AS max_d
        FROM ingested_days WHERE has_party_level = 1
        """
    ).fetchone()
    parties_n = conn.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
    vtps_n = conn.execute("SELECT COUNT(*) FROM parties WHERE is_vtp = 1").fetchone()[0]
    bmus_n = conn.execute("SELECT COUNT(*) FROM bmus").fetchone()[0]
    rows_n = conn.execute("SELECT COUNT(*) FROM bmu_sp_compensation").fetchone()[0]

    run_breakdown = [
        {"run_type": r["run_type"], "days": r["n"]}
        for r in conn.execute(
            "SELECT run_type, COUNT(*) AS n FROM ingested_days WHERE has_bmu_sp = 1 GROUP BY run_type"
        )
    ]

    return {
        "granular_days": gran["n"],
        "granular_min_date": gran["min_d"],
        "granular_max_date": gran["max_d"],
        "macro_days": macro["n"],
        "macro_min_date": macro["min_d"],
        "macro_max_date": macro["max_d"],
        "parties_count": parties_n,
        "registered_vtps_count": vtps_n,
        "bmus_count": bmus_n,
        "bmu_sp_rows": rows_n,
        "run_breakdown": run_breakdown,
    }


def get_overview(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    party_map = _load_party_map(conn)

    # Granular window summary
    gran_days_rows = conn.execute(
        """
        SELECT settlement_date, run_type FROM ingested_days
        WHERE has_bmu_sp = 1 AND settlement_date BETWEEN ? AND ?
        ORDER BY settlement_date
        """,
        (start_date, end_date),
    ).fetchall()
    gran_days = len(gran_days_rows)

    bmu_agg = conn.execute(
        """
        SELECT
            COALESCE(SUM(qcv), 0) AS net_qcv,
            COALESCE(SUM(CASE WHEN qcv > 0 THEN qcv ELSE 0 END), 0) AS pos_qcv,
            COALESCE(SUM(CASE WHEN qcv < 0 THEN qcv ELSE 0 END), 0) AS neg_qcv,
            COALESCE(SUM(comp_cashflow), 0) AS total_comp,
            COUNT(DISTINCT CASE WHEN ABS(qcv) > 0.01 THEN sec_party_id END) AS active_vtps,
            COUNT(DISTINCT CASE WHEN ABS(qcv) > 0.01 THEN pri_party_id END) AS active_suppliers,
            COUNT(DISTINCT CASE WHEN ABS(qcv) > 0.01 THEN sec_bmu_id END) AS active_sbmus
        FROM bmu_sp_compensation
        WHERE settlement_date BETWEEN ? AND ?
        """,
        (start_date, end_date),
    ).fetchone()

    party_agg = conn.execute(
        """
        SELECT
            COALESCE(SUM(sccp), 0) AS net_sccp,
            COALESCE(SUM(CASE WHEN sccp > 0 THEN sccp ELSE 0 END), 0) AS pos_sccp,
            COALESCE(SUM(scvp), 0) AS total_scvp
        FROM party_daily_settlement
        WHERE settlement_date IN (
            SELECT settlement_date FROM ingested_days
            WHERE has_bmu_sp = 1 AND settlement_date BETWEEN ? AND ?
        )
        """,
        (start_date, end_date),
    ).fetchone()

    mkt_agg = conn.execute(
        """
        SELECT
            COALESCE(AVG(ssc), 0) AS avg_ssc,
            COALESCE(AVG(sbp), 0) AS avg_sbp,
            COALESCE(AVG(mpj), 0) AS avg_mpj
        FROM sp_market_data
        WHERE settlement_date IN (
            SELECT settlement_date FROM ingested_days
            WHERE has_bmu_sp = 1 AND settlement_date BETWEEN ? AND ?
        )
        """,
        (start_date, end_date),
    ).fetchone()

    # Exact reconciliation check on positive suppliers (BMU×SP vs party-level sccp)
    reconcile_rows = conn.execute(
        """
        WITH bmu_sup AS (
            SELECT pri_party_id AS party_id, SUM(comp_cashflow) AS bmu_comp
            FROM bmu_sp_compensation
            WHERE settlement_date IN (
                SELECT settlement_date FROM ingested_days
                WHERE has_bmu_sp = 1 AND settlement_date BETWEEN ? AND ?
            )
            GROUP BY pri_party_id
        ),
        pl_sup AS (
            SELECT party_id, SUM(sccp) AS pl_sccp
            FROM party_daily_settlement
            WHERE settlement_date IN (
                SELECT settlement_date FROM ingested_days
                WHERE has_bmu_sp = 1 AND settlement_date BETWEEN ? AND ?
            )
            GROUP BY party_id
        )
        SELECT b.party_id, b.bmu_comp, COALESCE(p.pl_sccp, 0) AS pl_sccp
        FROM bmu_sup b
        LEFT JOIN pl_sup p ON b.party_id = p.party_id
        WHERE b.bmu_comp > 100 AND COALESCE(p.pl_sccp, 0) > 100
        """,
        (start_date, end_date, start_date, end_date),
    ).fetchall()
    max_recon_diff = max(
        (abs(float(r["bmu_comp"]) - float(r["pl_sccp"])) for r in reconcile_rows),
        default=0.0,
    )

    total_comp = float(bmu_agg["total_comp"])
    total_scvp = float(party_agg["total_scvp"])
    market_recon_diff = abs(total_comp - total_scvp)
    daily_avg_comp = total_comp / max(1, gran_days)

    # Top VTPs in selected window
    top_vtps = []
    for r in conn.execute(
        """
        SELECT sec_party_id,
               SUM(qcv) AS net_qcv,
               SUM(CASE WHEN qcv > 0 THEN qcv ELSE 0 END) AS pos_qcv,
               SUM(CASE WHEN qcv < 0 THEN qcv ELSE 0 END) AS neg_qcv,
               SUM(comp_cashflow) AS comp_gbp,
               COUNT(DISTINCT sec_bmu_id) AS bmu_count
        FROM bmu_sp_compensation
        WHERE settlement_date BETWEEN ? AND ? AND ABS(qcv) > 1e-7
        GROUP BY sec_party_id
        ORDER BY ABS(comp_gbp) DESC
        LIMIT 12
        """,
        (start_date, end_date),
    ):
        pid = r["sec_party_id"]
        meta = party_map.get(pid, {})
        top_vtps.append(
            {
                "party_id": pid,
                "company_name": meta.get("company_name") or pid,
                "roles": meta.get("roles") or [],
                "bmu_count": r["bmu_count"],
                "net_qcv_mwh": round(float(r["net_qcv"]), 2),
                "pos_qcv_mwh": round(float(r["pos_qcv"]), 2),
                "neg_qcv_mwh": round(float(r["neg_qcv"]), 2),
                "comp_gbp": round(float(r["comp_gbp"]), 2),
                "share_pct": round(
                    float(r["comp_gbp"]) / total_comp * 100.0 if abs(total_comp) > 1 else 0.0,
                    1,
                ),
            }
        )

    # Top Supplier Winners & Losers (sccp - scvp)
    supplier_rows = conn.execute(
        """
        SELECT party_id,
               SUM(sccp) AS sccp,
               SUM(scvp) AS scvp,
               SUM(sccp - scvp) AS net_transfer
        FROM party_daily_settlement
        WHERE settlement_date IN (
            SELECT settlement_date FROM ingested_days
            WHERE has_bmu_sp = 1 AND settlement_date BETWEEN ? AND ?
        )
        GROUP BY party_id
        HAVING ABS(sccp) > 1 OR ABS(scvp) > 1
        ORDER BY net_transfer DESC
        """,
        (start_date, end_date),
    ).fetchall()

    def _fmt_sup(r: sqlite3.Row) -> dict[str, Any]:
        pid = r["party_id"]
        meta = party_map.get(pid, {})
        return {
            "party_id": pid,
            "company_name": meta.get("company_name") or pid,
            "sccp_gbp": round(float(r["sccp"]), 2),
            "scvp_gbp": round(float(r["scvp"]), 2),
            "net_gbp": round(float(r["net_transfer"]), 2),
        }

    top_winners = [_fmt_sup(r) for r in supplier_rows[:6]]
    top_payers = [_fmt_sup(r) for r in sorted(supplier_rows, key=lambda x: x["net_transfer"])[:6]]

    # Full macro timeline across ALL ingested days (party_daily_settlement + sp_market_data)
    macro_series = []
    for r in conn.execute(
        """
        WITH pl AS (
            SELECT settlement_date,
                   SUM(sccp) AS net_sccp,
                   SUM(CASE WHEN sccp > 0 THEN sccp ELSE 0 END) AS pos_sccp,
                   SUM(scvp) AS total_scvp,
                   SUM(CASE WHEN party_id = 'MERCURY' THEN sccp ELSE 0 END) AS octopus_sccp
            FROM party_daily_settlement
            GROUP BY settlement_date
        ),
        sp AS (
            SELECT settlement_date,
                   SUM(qcvj) AS total_qcvj,
                   AVG(sbp) AS avg_sbp,
                   AVG(ssc) AS avg_ssc
            FROM sp_market_data
            GROUP BY settlement_date
        )
        SELECT d.settlement_date, d.run_type, d.has_bmu_sp,
               COALESCE(pl.net_sccp, 0) AS net_sccp,
               COALESCE(pl.pos_sccp, 0) AS pos_sccp,
               COALESCE(pl.total_scvp, 0) AS total_scvp,
               COALESCE(pl.octopus_sccp, 0) AS octopus_sccp,
               COALESCE(sp.total_qcvj, 0) AS total_qcvj,
               COALESCE(sp.avg_sbp, 0) AS avg_sbp,
               COALESCE(sp.avg_ssc, 0) AS avg_ssc
        FROM ingested_days d
        LEFT JOIN pl ON d.settlement_date = pl.settlement_date
        LEFT JOIN sp ON d.settlement_date = sp.settlement_date
        WHERE d.has_party_level = 1
        ORDER BY d.settlement_date
        """
    ):
        macro_series.append(
            {
                "date": r["settlement_date"],
                "run_type": r["run_type"],
                "has_bmu_sp": bool(r["has_bmu_sp"]),
                "net_sccp_gbp": round(float(r["net_sccp"]), 2),
                "pos_sccp_gbp": round(float(r["pos_sccp"]), 2),
                "scvp_gbp": round(float(r["total_scvp"]), 2),
                "octopus_sccp_gbp": round(float(r["octopus_sccp"]), 2),
                "qcv_mwh": round(float(r["total_qcvj"]), 2),
                "avg_sbp": round(float(r["avg_sbp"]), 2),
                "avg_ssc": round(float(r["avg_ssc"]), 2),
            }
        )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "granular_days": gran_days,
        "summary": {
            "total_comp_gbp": round(total_comp, 2),
            "daily_avg_comp_gbp": round(daily_avg_comp, 2),
            "annualised_comp_gbp": round(daily_avg_comp * 365.0, 0),
            "net_qcv_mwh": round(float(bmu_agg["net_qcv"]), 2),
            "pos_qcv_mwh": round(float(bmu_agg["pos_qcv"]), 2),
            "neg_qcv_mwh": round(float(bmu_agg["neg_qcv"]), 2),
            "party_pos_sccp_gbp": round(float(party_agg["pos_sccp"]), 2),
            "party_net_sccp_gbp": round(float(party_agg["net_sccp"]), 2),
            "party_total_scvp_gbp": round(float(party_agg["total_scvp"]), 2),
            "max_reconciliation_diff_gbp": round(market_recon_diff, 4),
            "max_party_diff_gbp": round(max_recon_diff, 2),
            "active_vtps": int(bmu_agg["active_vtps"] or 0),
            "active_suppliers": int(bmu_agg["active_suppliers"] or 0),
            "active_sbmus": int(bmu_agg["active_sbmus"] or 0),
            "avg_ssc": round(float(mkt_agg["avg_ssc"]), 2),
            "avg_sbp": round(float(mkt_agg["avg_sbp"]), 2),
            "avg_mpj": round(float(mkt_agg["avg_mpj"]), 2),
        },
        "top_vtps": top_vtps,
        "top_winners": top_winners,
        "top_payers": top_payers,
        "macro_timeline": macro_series,
        "milestones": REGULATORY_MILESTONES,
    }


def get_timing(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    sec_party_id: str | None = None,
) -> dict[str, Any]:
    party_map = _load_party_map(conn)

    gran_dates = [
        r["settlement_date"]
        for r in conn.execute(
            """
            SELECT settlement_date FROM ingested_days
            WHERE has_bmu_sp = 1 AND settlement_date BETWEEN ? AND ?
            ORDER BY settlement_date
            """,
            (start_date, end_date),
        )
    ]
    n_days = max(1, len(gran_dates))
    wkday_n = max(1, sum(1 for d in gran_dates if dt.date.fromisoformat(d).weekday() < 5))
    wkend_n = max(1, sum(1 for d in gran_dates if dt.date.fromisoformat(d).weekday() >= 5))

    # Load SP market context
    sp_mkt: dict[tuple[str, int], dict[str, float]] = {}
    sp_avg_sbp: dict[int, list[float]] = defaultdict(list)
    sp_avg_mpj: dict[int, list[float]] = defaultdict(list)
    sp_avg_ssc: dict[int, list[float]] = defaultdict(list)
    for r in conn.execute(
        """
        SELECT settlement_date, sp, sbp, mpj, ssc
        FROM sp_market_data
        WHERE settlement_date BETWEEN ? AND ?
        """,
        (start_date, end_date),
    ):
        d = r["settlement_date"]
        sp = int(r["sp"])
        sp_mkt[(d, sp)] = {
            "sbp": float(r["sbp"] or 0.0),
            "mpj": float(r["mpj"] or 0.0),
            "ssc": float(r["ssc"] or 0.0),
        }
        if d in gran_dates and 1 <= sp <= 48:
            sp_avg_sbp[sp].append(float(r["sbp"] or 0.0))
            sp_avg_mpj[sp].append(float(r["mpj"] or 0.0))
            sp_avg_ssc[sp].append(float(r["ssc"] or 0.0))

    # Query BMU×SP grouped by (date, sp, sec_party_id)
    params: list[Any] = [start_date, end_date]
    vtp_filter = ""
    if sec_party_id:
        vtp_filter = " AND sec_party_id = ?"
        params.append(sec_party_id)

    day_sp_qcv: dict[tuple[str, int], float] = defaultdict(float)
    day_sp_comp: dict[tuple[str, int], float] = defaultdict(float)
    sp_pos: list[float] = [0.0] * 48
    sp_neg: list[float] = [0.0] * 48
    sp_comp: list[float] = [0.0] * 48
    sp_wkday: list[float] = [0.0] * 48
    sp_wkend: list[float] = [0.0] * 48
    dow_sp: dict[int, list[float]] = {i: [0.0] * 48 for i in range(7)}
    dow_counts: dict[int, int] = defaultdict(int)
    for d in gran_dates:
        dow_counts[dt.date.fromisoformat(d).weekday()] += 1

    vtp_totals: dict[str, float] = defaultdict(float)
    vtp_sp_map: dict[str, list[float]] = defaultdict(lambda: [0.0] * 48)

    for r in conn.execute(
        f"""
        SELECT settlement_date, sp, sec_party_id,
               SUM(qcv) AS net_qcv,
               SUM(CASE WHEN qcv > 0 THEN qcv ELSE 0 END) AS pos_qcv,
               SUM(CASE WHEN qcv < 0 THEN qcv ELSE 0 END) AS neg_qcv,
               SUM(comp_cashflow) AS comp_gbp
        FROM bmu_sp_compensation
        WHERE settlement_date BETWEEN ? AND ? {vtp_filter}
        GROUP BY settlement_date, sp, sec_party_id
        """,
        params,
    ):
        d = r["settlement_date"]
        sp = int(r["sp"])
        sec = r["sec_party_id"]
        qcv = float(r["net_qcv"] or 0.0)
        pq = float(r["pos_qcv"] or 0.0)
        nq = float(r["neg_qcv"] or 0.0)
        cash = float(r["comp_gbp"] or 0.0)

        day_sp_qcv[(d, sp)] += qcv
        day_sp_comp[(d, sp)] += cash
        vtp_totals[sec] += abs(cash)
        if 1 <= sp <= 48:
            idx = sp - 1
            sp_pos[idx] += pq
            sp_neg[idx] += nq
            sp_comp[idx] += cash
            vtp_sp_map[sec][idx] += qcv
            wd = dt.date.fromisoformat(d).weekday()
            dow_sp[wd][idx] += qcv
            if wd < 5:
                sp_wkday[idx] += qcv
            else:
                sp_wkend[idx] += qcv

    # Build 48-SP profile
    intraday = []
    for sp in range(1, 49):
        idx = sp - 1
        sbps = sp_avg_sbp.get(sp, [0.0])
        mps = sp_avg_mpj.get(sp, [0.0])
        sscs = sp_avg_ssc.get(sp, [0.0])
        intraday.append(
            {
                "sp": sp,
                "time": _sp_to_time(sp),
                "avg_pos_mwh": round(sp_pos[idx] / n_days, 2),
                "avg_neg_mwh": round(sp_neg[idx] / n_days, 2),
                "avg_net_mwh": round((sp_pos[idx] + sp_neg[idx]) / n_days, 2),
                "avg_comp_gbp": round(sp_comp[idx] / n_days, 2),
                "avg_weekday_mwh": round(sp_wkday[idx] / wkday_n, 2),
                "avg_weekend_mwh": round(sp_wkend[idx] / wkend_n, 2),
                "avg_sbp": round(sum(sbps) / len(sbps), 2),
                "avg_mpj": round(sum(mps) / len(mps), 2),
                "avg_ssc": round(sum(sscs) / len(sscs), 2),
                "is_ev_offpeak": sp <= 11 or sp == 48,
            }
        )

    # Heatmap rows: one per granular date with 48 values
    heatmap = []
    max_cell_mwh = 0.0
    for d in gran_dates:
        dow = dt.date.fromisoformat(d).strftime("%a")
        cells = []
        day_total_mwh = 0.0
        day_total_gbp = 0.0
        day_sbps = []
        for sp in range(1, 49):
            q = day_sp_qcv.get((d, sp), 0.0)
            c = day_sp_comp.get((d, sp), 0.0)
            mkt = sp_mkt.get((d, sp), {"sbp": 0.0, "mpj": 0.0, "ssc": 0.0})
            day_total_mwh += q
            day_total_gbp += c
            day_sbps.append(mkt["sbp"])
            if abs(q) > max_cell_mwh:
                max_cell_mwh = abs(q)
            cells.append(
                {
                    "sp": sp,
                    "qcv_mwh": round(q, 2),
                    "comp_gbp": round(c, 2),
                    "sbp": round(mkt["sbp"], 1),
                }
            )
        heatmap.append(
            {
                "date": d,
                "dow": dow,
                "is_weekend": dt.date.fromisoformat(d).weekday() >= 5,
                "total_qcv_mwh": round(day_total_mwh, 1),
                "total_comp_gbp": round(day_total_gbp, 0),
                "avg_sbp": round(sum(day_sbps) / max(1, len(day_sbps)), 1),
                "cells": cells,
            }
        )

    # Top VTP comparative 48-SP curves
    top_vtp_ids = [
        k for k, _ in sorted(vtp_totals.items(), key=lambda kv: kv[1], reverse=True)[:6]
    ]
    vtp_profiles = [
        {
            "party_id": vid,
            "company_name": party_map.get(vid, {}).get("company_name") or vid,
            "avg_sp_mwh": [round(v / n_days, 2) for v in vtp_sp_map[vid]],
        }
        for vid in top_vtp_ids
    ]

    # Day-of-week averages (Mon=0..Sun=6)
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow_matrix = [
        {
            "dow": dow_names[i],
            "days": dow_counts[i],
            "avg_sp_mwh": [
                round(dow_sp[i][sp_i] / max(1, dow_counts[i]), 2) for sp_i in range(48)
            ],
            "avg_daily_mwh": round(sum(dow_sp[i]) / max(1, dow_counts[i]), 1),
        }
        for i in range(7)
    ]

    # Available VTP filter choices
    vtp_choices = [
        {
            "party_id": vid,
            "company_name": party_map.get(vid, {}).get("company_name") or vid,
        }
        for vid, _ in sorted(vtp_totals.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "sec_party_id": sec_party_id,
        "granular_days": len(gran_dates),
        "max_cell_mwh": round(max_cell_mwh, 2),
        "intraday": intraday,
        "heatmap": heatmap,
        "vtp_profiles": vtp_profiles,
        "dow_matrix": dow_matrix,
        "vtp_choices": vtp_choices,
    }


def get_compensation(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    sec_party_id: str | None = None,
    pri_party_id: str | None = None,
) -> dict[str, Any]:
    party_map = _load_party_map(conn)

    # 1. Supplier-level mutualisation ledger (from party_daily_settlement + BMU attribution)
    pl_by_party: dict[str, dict[str, float]] = {}
    total_scvp = 0.0
    total_pos_sccp = 0.0
    for r in conn.execute(
        """
        SELECT party_id, SUM(sccp) AS sccp, SUM(scvp) AS scvp
        FROM party_daily_settlement
        WHERE settlement_date IN (
            SELECT settlement_date FROM ingested_days
            WHERE has_bmu_sp = 1 AND settlement_date BETWEEN ? AND ?
        )
        GROUP BY party_id
        HAVING ABS(sccp) > 0.01 OR ABS(scvp) > 0.01
        """,
        (start_date, end_date),
    ):
        sccp = float(r["sccp"] or 0.0)
        scvp = float(r["scvp"] or 0.0)
        pl_by_party[r["party_id"]] = {"sccp": sccp, "scvp": scvp}
        if scvp > 0:
            total_scvp += scvp
        if sccp > 0:
            total_pos_sccp += sccp

    bmu_by_supplier: dict[str, dict[str, float]] = defaultdict(
        lambda: {"comp": 0.0, "qcv": 0.0, "qsd": 0.0}
    )
    bmu_by_vtp: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "comp": 0.0,
            "qcv": 0.0,
            "pos_qcv": 0.0,
            "neg_qcv": 0.0,
            "qsd": 0.0,
            "bmus": set(),
            "suppliers": set(),
        }
    )
    pair_flows: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"comp": 0.0, "qcv": 0.0, "qsd": 0.0, "bmu_pairs": set()}
    )
    bm_only_pairs: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"qsd": 0.0, "qcv": 0.0, "bmus": set()}
    )

    params: list[Any] = [start_date, end_date]
    filters = []
    if sec_party_id:
        filters.append("sec_party_id = ?")
        params.append(sec_party_id)
    if pri_party_id:
        filters.append("pri_party_id = ?")
        params.append(pri_party_id)
    where_extra = (" AND " + " AND ".join(filters)) if filters else ""

    for r in conn.execute(
        f"""
        SELECT pri_party_id, sec_party_id, pri_bmu_id, sec_bmu_id,
               SUM(qcv) AS qcv,
               SUM(CASE WHEN qcv > 0 THEN qcv ELSE 0 END) AS pos_qcv,
               SUM(CASE WHEN qcv < 0 THEN qcv ELSE 0 END) AS neg_qcv,
               SUM(qsd) AS qsd,
               SUM(comp_cashflow) AS comp_gbp
        FROM bmu_sp_compensation
        WHERE settlement_date BETWEEN ? AND ? {where_extra}
        GROUP BY pri_party_id, sec_party_id, pri_bmu_id, sec_bmu_id
        """,
        params,
    ):
        pri = r["pri_party_id"]
        sec = r["sec_party_id"]
        qcv = float(r["qcv"] or 0.0)
        pq = float(r["pos_qcv"] or 0.0)
        nq = float(r["neg_qcv"] or 0.0)
        qsd = float(r["qsd"] or 0.0)
        comp = float(r["comp_gbp"] or 0.0)

        bmu_by_supplier[pri]["comp"] += comp
        bmu_by_supplier[pri]["qcv"] += qcv
        bmu_by_supplier[pri]["qsd"] += qsd

        if abs(qcv) > 1e-6:
            bmu_by_vtp[sec]["comp"] += comp
            bmu_by_vtp[sec]["qcv"] += qcv
            bmu_by_vtp[sec]["pos_qcv"] += pq
            bmu_by_vtp[sec]["neg_qcv"] += nq
            bmu_by_vtp[sec]["qsd"] += qsd
            bmu_by_vtp[sec]["bmus"].add(r["sec_bmu_id"])
            bmu_by_vtp[sec]["suppliers"].add(pri)

            pf = pair_flows[(sec, pri)]
            pf["comp"] += comp
            pf["qcv"] += qcv
            pf["qsd"] += qsd
            pf["bmu_pairs"].add((r["sec_bmu_id"], r["pri_bmu_id"]))
        elif abs(qsd) > 0.5:
            bm = bm_only_pairs[(sec, pri)]
            bm["qsd"] += qsd
            bm["qcv"] += qcv
            bm["bmus"].add(r["sec_bmu_id"])

    # Combine suppliers
    all_supplier_ids = set(pl_by_party.keys()) | set(bmu_by_supplier.keys())
    suppliers_ledger = []
    for pid in all_supplier_ids:
        pl = pl_by_party.get(pid, {"sccp": 0.0, "scvp": 0.0})
        bm = bmu_by_supplier.get(pid, {"comp": 0.0, "qcv": 0.0, "qsd": 0.0})
        sccp = pl["sccp"]
        scvp = pl["scvp"]
        net = sccp - scvp
        demand_share = (scvp / total_scvp * 100.0) if total_scvp > 0 and scvp > 0 else 0.0
        comp_share = (sccp / total_pos_sccp * 100.0) if total_pos_sccp > 0 and sccp > 0 else 0.0
        over_index = (comp_share / demand_share) if demand_share > 0.05 else 0.0
        meta = party_map.get(pid, {})
        suppliers_ledger.append(
            {
                "party_id": pid,
                "company_name": meta.get("company_name") or pid,
                "roles": meta.get("roles") or [],
                "sccp_gbp": round(sccp, 2),
                "scvp_gbp": round(scvp, 2),
                "net_transfer_gbp": round(net, 2),
                "bmu_attributed_comp_gbp": round(bm["comp"], 2),
                "bmu_qcv_mwh": round(bm["qcv"], 2),
                "reconciliation_diff_gbp": round(bm["comp"] - sccp, 2),
                "demand_share_pct": round(demand_share, 2),
                "comp_share_pct": round(comp_share, 2),
                "over_index_ratio": round(over_index, 2),
            }
        )
    suppliers_ledger.sort(key=lambda x: abs(x["sccp_gbp"]) + abs(x["scvp_gbp"]), reverse=True)

    # VTPs table
    tot_vtp_comp = sum(v["comp"] for v in bmu_by_vtp.values())
    vtps_summary = []
    for sec, d in sorted(bmu_by_vtp.items(), key=lambda kv: abs(kv[1]["comp"]), reverse=True):
        meta = party_map.get(sec, {})
        vtps_summary.append(
            {
                "party_id": sec,
                "company_name": meta.get("company_name") or sec,
                "roles": meta.get("roles") or [],
                "bmu_count": len(d["bmus"]),
                "supplier_count": len(d["suppliers"]),
                "qcv_mwh": round(d["qcv"], 2),
                "pos_qcv_mwh": round(d["pos_qcv"], 2),
                "neg_qcv_mwh": round(d["neg_qcv"], 2),
                "qsd_mwh": round(d["qsd"], 2),
                "comp_gbp": round(d["comp"], 2),
                "share_pct": round(
                    d["comp"] / tot_vtp_comp * 100.0 if abs(tot_vtp_comp) > 1 else 0.0, 2
                ),
            }
        )

    # VTP -> Supplier flow matrix
    flows = []
    for (sec, pri), d in sorted(
        pair_flows.items(), key=lambda kv: abs(kv[1]["comp"]), reverse=True
    )[:120]:
        vtp_tot = abs(bmu_by_vtp[sec]["comp"]) or 1.0
        flows.append(
            {
                "sec_party_id": sec,
                "sec_company_name": party_map.get(sec, {}).get("company_name") or sec,
                "pri_party_id": pri,
                "pri_company_name": party_map.get(pri, {}).get("company_name") or pri,
                "qcv_mwh": round(d["qcv"], 2),
                "comp_gbp": round(d["comp"], 2),
                "bmu_pair_count": len(d["bmu_pairs"]),
                "share_of_vtp_pct": round(abs(d["comp"]) / vtp_tot * 100.0, 1),
            }
        )

    # Non-P415 BM-only VLP actions (qsd != 0, qcv == 0)
    bm_only = [
        {
            "sec_party_id": sec,
            "sec_company_name": party_map.get(sec, {}).get("company_name") or sec,
            "pri_party_id": pri,
            "pri_company_name": party_map.get(pri, {}).get("company_name") or pri,
            "qsd_mwh": round(d["qsd"], 2),
            "bmu_count": len(d["bmus"]),
        }
        for (sec, pri), d in sorted(
            bm_only_pairs.items(), key=lambda kv: abs(kv[1]["qsd"]), reverse=True
        )[:25]
    ]

    return {
        "start_date": start_date,
        "end_date": end_date,
        "filters": {"sec_party_id": sec_party_id, "pri_party_id": pri_party_id},
        "totals": {
            "total_pos_sccp_gbp": round(total_pos_sccp, 2),
            "total_scvp_gbp": round(total_scvp, 2),
            "total_vtp_comp_gbp": round(tot_vtp_comp, 2),
        },
        "suppliers": suppliers_ledger[:60],
        "vtps": vtps_summary,
        "flows": flows,
        "bm_only_vlp_activity": bm_only,
    }


def get_explorer(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    group_by: str = "bmu_pair",
    sec_party_id: str | None = None,
    pri_party_id: str | None = None,
    gsp_group: str | None = None,
    sp: int | None = None,
    search: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    party_map = _load_party_map(conn)
    clauses = ["settlement_date BETWEEN ? AND ?"]
    params: list[Any] = [start_date, end_date]

    if sec_party_id:
        clauses.append("sec_party_id = ?")
        params.append(sec_party_id)
    if pri_party_id:
        clauses.append("pri_party_id = ?")
        params.append(pri_party_id)
    if gsp_group:
        clauses.append("gsp_group = ?")
        params.append(gsp_group.upper())
    if sp is not None:
        clauses.append("sp = ?")
        params.append(sp)
    if search:
        like = f"%{search.strip()}%"
        clauses.append(
            "(sec_bmu_id LIKE ? OR pri_bmu_id LIKE ? OR sec_party_id LIKE ? OR pri_party_id LIKE ?)"
        )
        params.extend([like, like, like, like])

    where_sql = " AND ".join(clauses)

    if group_by == "raw":
        total = conn.execute(
            f"SELECT COUNT(*) FROM bmu_sp_compensation WHERE {where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT settlement_date, sp, run_type, sec_party_id, sec_bmu_id,
                   pri_party_id, pri_bmu_id, gsp_group,
                   vbmusdv, sp_proportion, qsd, qcv, ssc, comp_cashflow
            FROM bmu_sp_compensation
            WHERE {where_sql}
            ORDER BY ABS(comp_cashflow) DESC, settlement_date DESC, sp ASC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        items = [
            {
                "settlement_date": r["settlement_date"],
                "sp": r["sp"],
                "time": _sp_to_time(r["sp"]),
                "run_type": r["run_type"],
                "sec_party_id": r["sec_party_id"],
                "sec_company_name": party_map.get(r["sec_party_id"], {}).get("company_name")
                or r["sec_party_id"],
                "sec_bmu_id": r["sec_bmu_id"],
                "pri_party_id": r["pri_party_id"],
                "pri_company_name": party_map.get(r["pri_party_id"], {}).get("company_name")
                or r["pri_party_id"],
                "pri_bmu_id": r["pri_bmu_id"],
                "gsp_group": r["gsp_group"],
                "gsp_name": GSP_GROUP_NAMES.get(r["gsp_group"], r["gsp_group"]),
                "vbmusdv_mwh": round(float(r["vbmusdv"]), 4),
                "sp_proportion": round(float(r["sp_proportion"]), 4),
                "qsd_mwh": round(float(r["qsd"]), 4),
                "qcv_mwh": round(float(r["qcv"]), 4),
                "ssc": round(float(r["ssc"]), 2),
                "comp_gbp": round(float(r["comp_cashflow"]), 2),
            }
            for r in rows
        ]
    else:
        total = conn.execute(
            f"""
            SELECT COUNT(*) FROM (
                SELECT 1 FROM bmu_sp_compensation
                WHERE {where_sql}
                GROUP BY sec_bmu_id, pri_bmu_id
            )
            """,
            params,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT sec_party_id, sec_bmu_id, pri_party_id, pri_bmu_id, gsp_group,
                   COUNT(*) AS active_sps,
                   COUNT(DISTINCT settlement_date) AS active_days,
                   SUM(qsd) AS qsd_mwh,
                   SUM(qcv) AS qcv_mwh,
                   SUM(CASE WHEN qcv > 0 THEN qcv ELSE 0 END) AS pos_qcv_mwh,
                   SUM(CASE WHEN qcv < 0 THEN qcv ELSE 0 END) AS neg_qcv_mwh,
                   AVG(ssc) AS avg_ssc,
                   SUM(comp_cashflow) AS comp_gbp
            FROM bmu_sp_compensation
            WHERE {where_sql}
            GROUP BY sec_party_id, sec_bmu_id, pri_party_id, pri_bmu_id, gsp_group
            ORDER BY ABS(comp_gbp) DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
        items = [
            {
                "sec_party_id": r["sec_party_id"],
                "sec_company_name": party_map.get(r["sec_party_id"], {}).get("company_name")
                or r["sec_party_id"],
                "sec_bmu_id": r["sec_bmu_id"],
                "pri_party_id": r["pri_party_id"],
                "pri_company_name": party_map.get(r["pri_party_id"], {}).get("company_name")
                or r["pri_party_id"],
                "pri_bmu_id": r["pri_bmu_id"],
                "gsp_group": r["gsp_group"],
                "gsp_name": GSP_GROUP_NAMES.get(r["gsp_group"], r["gsp_group"]),
                "active_days": r["active_days"],
                "active_sps": r["active_sps"],
                "qsd_mwh": round(float(r["qsd_mwh"]), 2),
                "qcv_mwh": round(float(r["qcv_mwh"]), 2),
                "pos_qcv_mwh": round(float(r["pos_qcv_mwh"]), 2),
                "neg_qcv_mwh": round(float(r["neg_qcv_mwh"]), 2),
                "avg_ssc": round(float(r["avg_ssc"]), 2),
                "comp_gbp": round(float(r["comp_gbp"]), 2),
            }
            for r in rows
        ]

    return {
        "group_by": group_by,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


def get_parties(
    conn: sqlite3.Connection,
    role: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    bmu_counts = {
        r["lead_party_id"]: r["n"]
        for r in conn.execute(
            "SELECT lead_party_id, COUNT(*) AS n FROM bmus WHERE lead_party_id != '' GROUP BY lead_party_id"
        )
    }
    active_sec = {
        r["sec_party_id"]: float(r["comp"])
        for r in conn.execute(
            "SELECT sec_party_id, SUM(comp_cashflow) AS comp FROM bmu_sp_compensation GROUP BY sec_party_id"
        )
    }

    clauses = ["1=1"]
    params: list[Any] = []
    if role:
        clauses.append("roles_json LIKE ?")
        params.append(f'%"{role.upper()}"%')
    if search:
        like = f"%{search.strip()}%"
        clauses.append("(party_id LIKE ? OR company_name LIKE ?)")
        params.extend([like, like])

    rows = conn.execute(
        f"""
        SELECT party_id, company_name, address, roles_json,
               is_vtp, is_vlp, is_amvlp, is_supplier, source
        FROM parties
        WHERE {' AND '.join(clauses)}
        ORDER BY is_vtp DESC, is_vlp DESC, company_name ASC
        """,
        params,
    ).fetchall()

    items = []
    for r in rows:
        pid = r["party_id"]
        roles = json.loads(r["roles_json"] or "[]")
        items.append(
            {
                "party_id": pid,
                "company_name": r["company_name"],
                "address": r["address"],
                "roles": roles,
                "is_vtp": bool(r["is_vtp"]),
                "is_vlp": bool(r["is_vlp"]),
                "is_amvlp": bool(r["is_amvlp"]),
                "is_supplier": bool(r["is_supplier"]),
                "bmu_count": bmu_counts.get(pid, 0),
                "vtp_comp_gbp": round(active_sec.get(pid, 0.0), 2),
                "source": r["source"],
            }
        )

    return {
        "total": len(items),
        "role_descriptions": ROLE_DESCRIPTIONS,
        "items": items,
    }
