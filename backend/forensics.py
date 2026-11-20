"""Creative 6-Signal Forensic Engine for EV Charger Focus & Baselining Abuse Detection."""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from collections import defaultdict
from typing import Any

from .elexon import GSP_GROUP_NAMES

# Major GB domestic smart-EV tariff suppliers (Octopus Go/IOG, E.ON Next Drive,
# British Gas Electric Driver, OVO Charge Anytime, ScottishPower EV Optimise)
EV_TARIFF_SUPPLIERS = {"MERCURY", "NITTWO01", "BRITGAS", "OVOE", "SPSUP01"}
PRIMARY_EV_LEADERS = {"MERCURY", "NITTWO01", "BRITGAS"}

# Published cheap overnight EV charging windows (Settlement Periods 1-48) per supplier
SUPPLIER_EV_OFFPEAK_SPS: dict[str, set[int]] = {
    "MERCURY": set(range(1, 12)) | {48},   # Octopus Go / IOG: 23:30-05:30
    "NITTWO01": set(range(1, 15)),         # E.ON Next Drive: 00:00-07:00
    "BRITGAS": set(range(1, 11)),          # British Gas Electric Driver: 00:00-05:00
    "SPSUP01": set(range(1, 11)),          # ScottishPower EV Optimise: 00:00-05:00
    "OVOE": set(range(1, 12)) | {48},      # OVO Charge Anytime / overnight proxy
}

BOUNDARY_SUPPLIERS = ("MERCURY", "NITTWO01", "BRITGAS", "LENCO")


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx < 1e-9 or dy < 1e-9:
        return None
    return num / (dx * dy)


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, val))


def _shannon_entropy_norm(counts: dict[str, float], max_buckets: int = 14) -> float:
    total = sum(v for v in counts.values() if v > 0)
    if total <= 0 or max_buckets <= 1:
        return 0.0
    ent = 0.0
    for v in counts.values():
        if v > 0:
            p = v / total
            ent -= p * math.log(p)
    return min(1.0, ent / math.log(max_buckets))


def compute_forensics(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    """Compute transparent 6-signal EV focus & baselining anomaly scores for every active VTP."""
    # 1. Load party metadata
    party_meta: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT party_id, company_name, roles_json, is_vtp, is_vlp, is_amvlp, is_supplier FROM parties"
    ):
        party_meta[row["party_id"]] = {
            "company_name": row["company_name"],
            "roles": json.loads(row["roles_json"] or "[]"),
            "is_vtp": bool(row["is_vtp"]),
            "is_amvlp": bool(row["is_amvlp"]),
            "is_supplier": bool(row["is_supplier"]),
        }

    # 2. Compute true GB electricity demand share per supplier from mutualised scvp
    scvp_by_supplier: dict[str, float] = defaultdict(float)
    total_scvp = 0.0
    for row in conn.execute(
        """
        SELECT party_id, SUM(scvp) AS tot_scvp
        FROM party_daily_settlement
        WHERE settlement_date BETWEEN ? AND ? AND scvp > 0
        GROUP BY party_id
        """,
        (start_date, end_date),
    ):
        val = float(row["tot_scvp"] or 0.0)
        scvp_by_supplier[row["party_id"]] = val
        total_scvp += val

    gb_ev_supplier_share = (
        sum(scvp_by_supplier.get(s, 0.0) for s in EV_TARIFF_SUPPLIERS) / total_scvp
        if total_scvp > 0
        else 0.42
    )
    gb_octopus_share = (
        scvp_by_supplier.get("MERCURY", 0.0) / total_scvp if total_scvp > 0 else 0.13
    )

    # 3. Load SP market prices for the window
    sp_market: dict[tuple[str, int], dict[str, float]] = {}
    daily_prices: dict[str, dict[str, float]] = {}
    daily_sbp_acc: dict[str, list[float]] = defaultdict(list)
    daily_mp_acc: dict[str, list[float]] = defaultdict(list)
    daily_ssc_acc: dict[str, list[float]] = defaultdict(list)

    for row in conn.execute(
        """
        SELECT settlement_date, sp, ssc, sbp, ssp, mpj
        FROM sp_market_data
        WHERE settlement_date BETWEEN ? AND ?
        """,
        (start_date, end_date),
    ):
        d = row["settlement_date"]
        sp = int(row["sp"])
        sp_market[(d, sp)] = {
            "ssc": float(row["ssc"] or 0.0),
            "sbp": float(row["sbp"] or 0.0),
            "mpj": float(row["mpj"] or 0.0),
        }
        daily_sbp_acc[d].append(float(row["sbp"] or 0.0))
        daily_mp_acc[d].append(float(row["mpj"] or 0.0))
        daily_ssc_acc[d].append(float(row["ssc"] or 0.0))

    for d in daily_sbp_acc:
        sbps = daily_sbp_acc[d]
        mps = daily_mp_acc[d]
        sscs = daily_ssc_acc[d]
        daily_prices[d] = {
            "avg_sbp": sum(sbps) / len(sbps),
            "min_sbp": min(sbps),
            "max_sbp": max(sbps),
            "avg_mpj": sum(mps) / len(mps),
            "avg_ssc": sum(sscs) / len(sscs),
        }

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
    total_gran_days = len(gran_dates)

    # 4. Stream granular BMU×SP compensation rows and aggregate forensic features per VTP
    vtp_pos_qcv: dict[str, float] = defaultdict(float)
    vtp_neg_qcv: dict[str, float] = defaultdict(float)
    vtp_comp_cash: dict[str, float] = defaultdict(float)
    vtp_supplier_vol: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    vtp_supplier_cash: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    vtp_gsp_vol: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    vtp_base_bmu_vol: dict[str, float] = defaultdict(float)
    vtp_total_abs_vol: dict[str, float] = defaultdict(float)
    vtp_sp_pos: dict[str, list[float]] = defaultdict(lambda: [0.0] * 48)
    vtp_sp_neg: dict[str, list[float]] = defaultdict(lambda: [0.0] * 48)
    vtp_sp_wkday: dict[str, list[float]] = defaultdict(lambda: [0.0] * 48)
    vtp_sp_wkend: dict[str, list[float]] = defaultdict(lambda: [0.0] * 48)
    vtp_day_sp_qcv: dict[str, dict[tuple[str, int], float]] = defaultdict(
        lambda: defaultdict(float)
    )
    vtp_day_pos: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    vtp_day_neg: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    vtp_day_cash: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    vtp_bmus: dict[str, set[str]] = defaultdict(set)
    vtp_suffix_daily: dict[str, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )
    # Tariff-window & profitability accumulators
    vtp_ev_peak_qcv: dict[str, float] = defaultdict(float)
    vtp_ev_offpeak_qcv: dict[str, float] = defaultdict(float)
    vtp_wkday_midday_qcv: dict[str, float] = defaultdict(float)
    vtp_est_rev_mpj: dict[str, float] = defaultdict(float)
    vtp_peak_rev_mpj: dict[str, float] = defaultdict(float)
    vtp_below_ssc_mpj_qcv: dict[str, float] = defaultdict(float)
    vtp_below_ssc_mpj_rev: dict[str, float] = defaultdict(float)
    vtp_deadweight_gbp: dict[str, float] = defaultdict(float)
    vtp_sup_sp_pos: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {s: [0.0] * 48 for s in BOUNDARY_SUPPLIERS}
    )

    wkday_count = sum(1 for d in gran_dates if dt.date.fromisoformat(d).weekday() < 5)
    wkend_count = max(0, total_gran_days - wkday_count)

    for row in conn.execute(
        """
        SELECT settlement_date, sp, pri_bmu_id, sec_bmu_id, pri_party_id, sec_party_id,
               gsp_group, qcv, comp_cashflow
        FROM bmu_sp_compensation
        WHERE settlement_date BETWEEN ? AND ? AND ABS(qcv) > 1e-7
        """,
        (start_date, end_date),
    ):
        d = row["settlement_date"]
        sp = int(row["sp"])
        pri_bmu = row["pri_bmu_id"] or ""
        sec_bmu = row["sec_bmu_id"] or ""
        pri = row["pri_party_id"]
        sec = row["sec_party_id"]
        gsp = row["gsp_group"] or ""
        qcv = float(row["qcv"] or 0.0)
        cash = float(row["comp_cashflow"] or 0.0)
        abs_qcv = abs(qcv)
        is_wkday = dt.date.fromisoformat(d).weekday() < 5
        mkt = sp_market.get((d, sp))

        vtp_bmus[sec].add(sec_bmu)
        vtp_comp_cash[sec] += cash
        vtp_total_abs_vol[sec] += abs_qcv
        vtp_supplier_vol[sec][pri] += qcv
        vtp_supplier_cash[sec][pri] += cash
        if gsp:
            vtp_gsp_vol[sec][gsp] += abs_qcv
        if pri_bmu.startswith("2__"):
            vtp_base_bmu_vol[sec] += abs_qcv

        if qcv >= 0:
            vtp_pos_qcv[sec] += qcv
            vtp_day_pos[sec][d] += qcv
            mpj_val = mkt["mpj"] if mkt else 0.0
            ssc_val = mkt["ssc"] if mkt else 0.0
            vtp_est_rev_mpj[sec] += qcv * mpj_val
            if pri in SUPPLIER_EV_OFFPEAK_SPS:
                if sp in SUPPLIER_EV_OFFPEAK_SPS[pri]:
                    vtp_ev_offpeak_qcv[sec] += qcv
                else:
                    vtp_ev_peak_qcv[sec] += qcv
                    vtp_peak_rev_mpj[sec] += qcv * mpj_val
            if is_wkday and 19 <= sp <= 32:
                vtp_wkday_midday_qcv[sec] += qcv
            if mkt and mpj_val < ssc_val:
                vtp_below_ssc_mpj_qcv[sec] += qcv
                vtp_below_ssc_mpj_rev[sec] += qcv * mpj_val
                vtp_deadweight_gbp[sec] += qcv * (ssc_val - mpj_val)
            if pri in BOUNDARY_SUPPLIERS and 1 <= sp <= 48:
                vtp_sup_sp_pos[sec][pri][sp - 1] += qcv
        else:
            vtp_neg_qcv[sec] += qcv
            vtp_day_neg[sec][d] += qcv
        vtp_day_cash[sec][d] += cash

        vtp_day_sp_qcv[sec][(d, sp)] += qcv
        suffix = sec_bmu[-3:] if len(sec_bmu) >= 3 else sec_bmu
        vtp_suffix_daily[sec][suffix][d] += qcv

        if 1 <= sp <= 48:
            if qcv >= 0:
                vtp_sp_pos[sec][sp - 1] += qcv
            else:
                vtp_sp_neg[sec][sp - 1] += qcv
            if is_wkday:
                vtp_sp_wkday[sec][sp - 1] += qcv
            else:
                vtp_sp_wkend[sec][sp - 1] += qcv

    # 5. Compute forensic metrics & composite scores per VTP
    vtp_results: list[dict[str, Any]] = []
    market_total_comp = sum(vtp_comp_cash.values())

    for sec, abs_vol in sorted(
        vtp_total_abs_vol.items(), key=lambda kv: abs(vtp_comp_cash[kv[0]]), reverse=True
    ):
        if abs_vol < 0.05:
            continue

        meta = party_meta.get(sec, {})
        company_name = meta.get("company_name") or sec
        roles = meta.get("roles") or []
        is_amvlp = bool(meta.get("is_amvlp"))

        pos_vol = vtp_pos_qcv[sec]
        neg_vol = vtp_neg_qcv[sec]  # <= 0
        net_vol = pos_vol + neg_vol
        comp_cash = vtp_comp_cash[sec]

        # --- Signal 1: EV-Tariff Supplier Over-Representation ---
        tot_sup_abs = sum(abs(v) for v in vtp_supplier_vol[sec].values()) or 1.0
        ev_sup_vol = sum(
            max(0.0, vtp_supplier_vol[sec].get(s, 0.0)) for s in EV_TARIFF_SUPPLIERS
        )
        ev_sup_share = ev_sup_vol / tot_sup_abs
        octopus_vol = max(0.0, vtp_supplier_vol[sec].get("MERCURY", 0.0))
        octopus_share = octopus_vol / tot_sup_abs
        ev_lift = ev_sup_share / max(0.05, gb_ev_supplier_share)
        octopus_lift = octopus_share / max(0.02, gb_octopus_share)

        # EV affinity score: high when EV suppliers > 70% and Octopus lift > 2x
        ev_affinity_score = _clamp(
            (ev_sup_share * 65.0) + min(35.0, max(0.0, (octopus_lift - 0.8) * 12.0))
        )

        # --- Signal 2: National Domestic Footprint (14 GSPs + 2__ Base BMUs) ---
        gsp_vols = vtp_gsp_vol[sec]
        gsp_count = len([g for g, v in gsp_vols.items() if v > 0.01])
        gsp_entropy = _shannon_entropy_norm(gsp_vols, max_buckets=14)
        base_bmu_share = vtp_base_bmu_vol[sec] / abs_vol if abs_vol > 0 else 0.0
        domestic_footprint_score = _clamp(
            (gsp_count / 14.0) * 45.0 + gsp_entropy * 35.0 + base_bmu_share * 20.0
        )

        # Composite EV Focus Score (0-100)
        ev_focus_score = _clamp(
            ev_affinity_score * 0.55
            + domestic_footprint_score * 0.35
            + (10.0 if is_amvlp else 0.0)
        )

        # --- Signal 3: Energy Conservation Violation (One-Sided Turn-Down) ---
        one_sided_ratio = pos_vol / (pos_vol + abs(neg_vol)) if (pos_vol + abs(neg_vol)) > 0 else 0.5
        # Score ramps sharply from 75% to 100% one-sided positive turn-down
        conservation_score = _clamp((one_sided_ratio - 0.55) / 0.45 * 100.0)

        # --- Signal 4: Wholesale Price Insensitivity / Low-Price Farming ---
        vol_below_ssc = 0.0
        vol_below_60 = 0.0
        vol_negative_sbp = 0.0
        sp_vols_for_corr: list[float] = []
        sp_prices_for_corr: list[float] = []
        day_sp_map = vtp_day_sp_qcv[sec]
        for d in gran_dates:
            for sp in range(1, 49):
                q = day_sp_map.get((d, sp), 0.0)
                mkt = sp_market.get((d, sp))
                if not mkt:
                    continue
                sp_vols_for_corr.append(q)
                sp_prices_for_corr.append(mkt["sbp"])
                if q > 0:
                    if mkt["sbp"] < mkt["ssc"]:
                        vol_below_ssc += q
                    if mkt["sbp"] < 60.0:
                        vol_below_60 += q
                    if mkt["sbp"] < 0.0:
                        vol_negative_sbp += q

        pct_below_ssc = vol_below_ssc / pos_vol if pos_vol > 0 else 0.0
        pct_below_60 = vol_below_60 / pos_vol if pos_vol > 0 else 0.0
        pct_negative_sbp = vol_negative_sbp / pos_vol if pos_vol > 0 else 0.0
        sp_price_corr = _pearson(sp_vols_for_corr, sp_prices_for_corr)

        # Daily volume vs daily average SBP correlation
        daily_series = []
        d_vols: list[float] = []
        d_sbps: list[float] = []
        for d in gran_dates:
            dp = vtp_day_pos[sec].get(d, 0.0)
            dn = vtp_day_neg[sec].get(d, 0.0)
            dc = vtp_day_cash[sec].get(d, 0.0)
            pm = daily_prices.get(d, {})
            avg_sbp = pm.get("avg_sbp", 0.0)
            daily_series.append(
                {
                    "date": d,
                    "dow": dt.date.fromisoformat(d).strftime("%a"),
                    "pos_qcv_mwh": round(dp, 2),
                    "neg_qcv_mwh": round(dn, 2),
                    "net_qcv_mwh": round(dp + dn, 2),
                    "comp_gbp": round(dc, 2),
                    "avg_sbp": round(avg_sbp, 2),
                    "min_sbp": round(pm.get("min_sbp", 0.0), 2),
                    "avg_mpj": round(pm.get("avg_mpj", 0.0), 2),
                    "avg_ssc": round(pm.get("avg_ssc", 0.0), 2),
                }
            )
            if dp > 0.01 and pm:
                d_vols.append(dp)
                d_sbps.append(avg_sbp)

        daily_price_corr = _pearson(d_vols, d_sbps)
        # Low-price farming score: high when large share happens below SSC and daily r <= 0.25
        corr_component = (
            _clamp((0.55 - (daily_price_corr if daily_price_corr is not None else 0.25)) / 0.75 * 100.0)
        )
        low_price_component = _clamp(pct_below_ssc * 140.0 + pct_below_60 * 120.0)
        low_price_farming_score = _clamp(low_price_component * 0.60 + corr_component * 0.40)

        # --- Signal 5: EV Off-Peak Window Cliff & Continuous Duty Cycle ---
        # SP 1-11 = 00:00-05:30 (Intelligent Octopus Go / Next Drive off-peak window)
        # SP 12-46 = 05:30-23:00 (Daytime + Evening window)
        avg_sp_pos = [v / max(1, total_gran_days) for v in vtp_sp_pos[sec]]
        avg_sp_neg = [v / max(1, total_gran_days) for v in vtp_sp_neg[sec]]
        night_mean = sum(avg_sp_pos[0:11]) / 11.0
        day_eve_mean = sum(avg_sp_pos[11:46]) / 35.0
        day_to_night_ratio = (
            day_eve_mean / max(0.01, night_mean) if day_eve_mean > 0.01 else 0.0
        )
        peak_sp_vol = max(avg_sp_pos) if avg_sp_pos else 0.0
        active_sps_per_day = (
            sum(1 for v in avg_sp_pos if peak_sp_vol > 0 and v >= peak_sp_vol * 0.15)
        )
        active_hours_per_day = active_sps_per_day * 0.5

        # Detect pre-event turn-up signature (negative volume in SPs 31-38 before SP 37-48 peak)
        pre_peak_neg = abs(sum(avg_sp_neg[30:38]))
        eve_pos = sum(avg_sp_pos[36:48])
        pre_event_turnup_flag = bool(pre_peak_neg > 0.5 and eve_pos > pre_peak_neg * 5.0)

        # Duty cycle anomaly: continuous 12-20h/day turn-down + steep overnight EV window cliff
        hours_component = _clamp((active_hours_per_day - 4.0) / 14.0 * 100.0)
        cliff_component = _clamp(min(100.0, math.log1p(day_to_night_ratio) * 32.0))
        duty_cycle_score = _clamp(hours_component * 0.65 + cliff_component * 0.35)

        # --- Signal 6: Multi-Day Persistence & Frozen Baseline (Low CoV) ---
        active_days = sum(1 for d in gran_dates if vtp_day_pos[sec].get(d, 0.0) > 0.1)
        active_day_pct = active_days / max(1, total_gran_days)
        active_daily_vols = [
            vtp_day_pos[sec][d] for d in gran_dates if vtp_day_pos[sec].get(d, 0.0) > 0.1
        ]
        if len(active_daily_vols) >= 3:
            mean_dv = sum(active_daily_vols) / len(active_daily_vols)
            std_dv = math.sqrt(
                sum((v - mean_dv) ** 2 for v in active_daily_vols) / len(active_daily_vols)
            )
            daily_cov = std_dv / mean_dv if mean_dv > 0 else 1.0
        else:
            daily_cov = 1.0

        # Persistence score: active nearly every day + very low CoV = frozen baseline harvesting
        stability_component = _clamp((0.55 - daily_cov) / 0.45 * 100.0)
        persistence_score = _clamp(active_day_pct * 55.0 + stability_component * 45.0)

        # --- Composite Baselining Abuse Risk Score (0-100) ---
        baselining_risk_score = _clamp(
            conservation_score * 0.30
            + low_price_farming_score * 0.30
            + duty_cycle_score * 0.20
            + persistence_score * 0.20
        )

        # Archetype classification & evidence bullets
        if night_mean > day_eve_mean * 1.5 and night_mean > 0.05:
            archetype = (
                "Overnight EV / Off-Peak Specialist"
                if ev_focus_score >= 65
                else "Overnight / Off-Peak Specialist"
            )
        elif ev_focus_score >= 65 and baselining_risk_score >= 65:
            archetype = "Continuous EV Baseline Harvester"
        elif ev_focus_score >= 65 and baselining_risk_score >= 45:
            archetype = "Evening EV Shifter (Elevated Risk)"
        elif ev_focus_score >= 65:
            archetype = "Domestic EV Flexibility"
        elif ev_sup_share < 0.35:
            archetype = "Commercial / Fleet / I&C Flexibility"
        else:
            archetype = "Mixed / Targeted Flexibility"

        evidence: list[str] = []
        if octopus_lift >= 2.0:
            evidence.append(
                f"{octopus_share * 100:.1f}% of volume lands on Octopus Energy "
                f"({octopus_lift:.1f}x its GB demand share); "
                f"{ev_sup_share * 100:.1f}% across major EV-tariff suppliers."
            )
        else:
            evidence.append(
                f"{ev_sup_share * 100:.1f}% lands on domestic EV-tariff suppliers "
                f"(GB demand benchmark: {gb_ev_supplier_share * 100:.1f}%)."
            )
        if one_sided_ratio >= 0.95:
            evidence.append(
                f"{one_sided_ratio * 100:.1f}% one-sided positive turn-down "
                f"({pos_vol:,.1f} MWh vs {neg_vol:,.1f} MWh turn-up) — missing physical rebound."
            )
        if pct_below_ssc >= 0.20:
            evidence.append(
                f"{pct_below_ssc * 100:.1f}% of turn-down occurs when System Buy Price is below "
                f"Supplier Sourcing Cost ({pct_below_60 * 100:.1f}% when SBP < £60/MWh)."
            )
        if active_hours_per_day >= 12.0:
            evidence.append(
                f"Active {active_hours_per_day:.1f} hours/day on average with a "
                f"{day_to_night_ratio:.1f}x drop-off during the 00:00-05:30 EV tariff window."
            )
        if pre_event_turnup_flag:
            evidence.append(
                "Shows measurable demand turn-up (negative QCV) between 15:00-19:00 immediately "
                "preceding its main evening turn-down block."
            )
        if active_day_pct >= 0.85 and daily_cov < 0.25:
            evidence.append(
                f"Active on {active_days}/{total_gran_days} days with near-constant daily volume "
                f"(CoV {daily_cov:.2f}), consistent with a frozen BL01 lookback baseline."
            )

        # Top suppliers for this VTP
        top_suppliers = []
        for pri_id, p_cash in sorted(
            vtp_supplier_cash[sec].items(), key=lambda kv: abs(kv[1]), reverse=True
        )[:8]:
            p_meta = party_meta.get(pri_id, {})
            top_suppliers.append(
                {
                    "party_id": pri_id,
                    "company_name": p_meta.get("company_name") or pri_id,
                    "qcv_mwh": round(vtp_supplier_vol[sec][pri_id], 2),
                    "comp_gbp": round(p_cash, 2),
                    "share_pct": round(
                        abs(vtp_supplier_vol[sec][pri_id]) / tot_sup_abs * 100.0, 1
                    ),
                    "is_ev_supplier": pri_id in EV_TARIFF_SUPPLIERS,
                }
            )

        # 48-SP profile
        sp_profile = []
        for idx in range(48):
            sp_num = idx + 1
            hh = (sp_num - 1) // 2
            mm = "00" if (sp_num - 1) % 2 == 0 else "30"
            sp_profile.append(
                {
                    "sp": sp_num,
                    "time": f"{hh:02d}:{mm}",
                    "avg_pos_mwh": round(avg_sp_pos[idx], 3),
                    "avg_neg_mwh": round(avg_sp_neg[idx], 3),
                    "avg_weekday_mwh": round(
                        vtp_sp_wkday[sec][idx] / max(1, wkday_count), 3
                    ),
                    "avg_weekend_mwh": round(
                        vtp_sp_wkend[sec][idx] / max(1, wkend_count), 3
                    ),
                }
            )

        # GSP breakdown
        gsp_breakdown = [
            {
                "gsp_group": code,
                "gsp_name": GSP_GROUP_NAMES.get(code, code),
                "abs_qcv_mwh": round(gsp_vols.get(code, 0.0), 2),
                "share_pct": round(gsp_vols.get(code, 0.0) / abs_vol * 100.0, 1),
            }
            for code in sorted(GSP_GROUP_NAMES.keys())
            if gsp_vols.get(code, 0.0) > 0.01
        ]

        # Sub-BMU suffix totals (e.g. *001 vs *002)
        sub_bmus = [
            {
                "suffix": suf,
                "total_qcv_mwh": round(sum(dmap.values()), 2),
                "active_days": sum(1 for v in dmap.values() if abs(v) > 0.1),
            }
            for suf, dmap in sorted(
                vtp_suffix_daily[sec].items(),
                key=lambda kv: abs(sum(kv[1].values())),
                reverse=True,
            )[:6]
        ]

        # Tariff-window counterfactual & profitability metrics
        ev_tariff_tot = vtp_ev_peak_qcv[sec] + vtp_ev_offpeak_qcv[sec]
        peak_tariff_share = (
            vtp_ev_peak_qcv[sec] / ev_tariff_tot * 100.0 if ev_tariff_tot > 0.01 else 0.0
        )
        offpeak_tariff_share = (
            vtp_ev_offpeak_qcv[sec] / ev_tariff_tot * 100.0 if ev_tariff_tot > 0.01 else 0.0
        )
        wkday_midday_share = (
            vtp_wkday_midday_qcv[sec] / pos_vol * 100.0 if pos_vol > 0.01 else 0.0
        )

        # Equivalent Full-Load Hours per day: avg(daily_pos_MWh / (daily_peak_sp_MWh * 2))
        eflh_vals = []
        for d in gran_dates:
            sp_vols_d = [
                max(0.0, day_sp_map.get((d, sp), 0.0)) for sp in range(1, 49)
            ]
            peak_sp_d = max(sp_vols_d) if sp_vols_d else 0.0
            if peak_sp_d > 0.05:
                eflh_vals.append(sum(sp_vols_d) / (peak_sp_d * 2.0))
        eflh_hours = sum(eflh_vals) / len(eflh_vals) if eflh_vals else 0.0

        # Supplier-specific tariff clock boundary curves (wrapped 22:00 -> 08:30, SP 45..48 then 1..18)
        sup_peaks = {
            s: max(vtp_sup_sp_pos[sec][s]) for s in BOUNDARY_SUPPLIERS
        }
        wrapped_sps = [45, 46, 47, 48] + list(range(1, 19))
        boundary_curves = []
        for sp_num in wrapped_sps:
            hh = (sp_num - 1) // 2
            mm = "00" if (sp_num - 1) % 2 == 0 else "30"
            pt: dict[str, Any] = {"sp": sp_num, "time": f"{hh:02d}:{mm}"}
            for s in BOUNDARY_SUPPLIERS:
                pk = sup_peaks[s]
                pt[s] = round(vtp_sup_sp_pos[sec][s][sp_num - 1] / pk * 100.0, 1) if pk > 0.05 else 0.0
            boundary_curves.append(pt)

        # Detect supplier-specific tariff clock steps (e.g. BG jumps at 05:00 ahead of Octopus at 05:30;
        # Octopus drops at 23:30 ahead of E.ON Next at 00:00)
        def _norm(sup: str, sp_num: int) -> float:
            pk = sup_peaks[sup]
            return (vtp_sup_sp_pos[sec][sup][sp_num - 1] / pk * 100.0) if pk > 0.05 else 0.0

        bg_0500_lead = _norm("BRITGAS", 11) - _norm("MERCURY", 11)
        oct_0530_lead = _norm("MERCURY", 12) - _norm("NITTWO01", 12)
        oct_2330_drop = _norm("NITTWO01", 48) - _norm("MERCURY", 48)
        edf_2300_drop = _norm("NITTWO01", 47) - _norm("LENCO", 47)
        has_clock_fingerprint = bool(
            sup_peaks["MERCURY"] > 1.0
            and sup_peaks["NITTWO01"] > 0.5
            and (bg_0500_lead >= 12.0 or oct_0530_lead >= 8.0)
            and oct_2330_drop >= 15.0
        )

        vtp_results.append(
            {
                "party_id": sec,
                "company_name": company_name,
                "roles": roles,
                "is_amvlp": is_amvlp,
                "bmu_count": len(vtp_bmus[sec]),
                "pos_qcv_mwh": round(pos_vol, 2),
                "neg_qcv_mwh": round(neg_vol, 2),
                "net_qcv_mwh": round(net_vol, 2),
                "comp_gbp": round(comp_cash, 2),
                "market_share_pct": round(
                    (comp_cash / market_total_comp * 100.0)
                    if abs(market_total_comp) > 1
                    else 0.0,
                    2,
                ),
                "ev_focus_score": round(ev_focus_score, 1),
                "baselining_risk_score": round(baselining_risk_score, 1),
                "archetype": archetype,
                "evidence": evidence,
                "tariff_analysis": {
                    "peak_tariff_share_pct": round(peak_tariff_share, 1),
                    "offpeak_tariff_share_pct": round(offpeak_tariff_share, 1),
                    "weekday_midday_share_pct": round(wkday_midday_share, 1),
                    "eflh_hours_per_day": round(eflh_hours, 1),
                    "estimated_vtp_revenue_gbp": round(vtp_est_rev_mpj[sec], 2),
                    "peak_tariff_revenue_gbp": round(vtp_peak_rev_mpj[sec], 2),
                    "below_ssc_mpj_qcv_mwh": round(vtp_below_ssc_mpj_qcv[sec], 2),
                    "below_ssc_vtp_revenue_gbp": round(vtp_below_ssc_mpj_rev[sec], 2),
                    "deadweight_subsidy_gbp": round(vtp_deadweight_gbp[sec], 2),
                    "has_tariff_clock_fingerprint": has_clock_fingerprint,
                    "clock_steps": {
                        "bg_0500_pct": round(_norm("BRITGAS", 11), 1),
                        "oct_0500_pct": round(_norm("MERCURY", 11), 1),
                        "oct_0530_pct": round(_norm("MERCURY", 12), 1),
                        "eon_0530_pct": round(_norm("NITTWO01", 12), 1),
                        "eon_0600_pct": round(_norm("NITTWO01", 13), 1),
                        "edf_2300_pct": round(_norm("LENCO", 47), 1),
                        "oct_2330_pct": round(_norm("MERCURY", 48), 1),
                        "eon_2330_pct": round(_norm("NITTWO01", 48), 1),
                        "eon_0000_pct": round(_norm("NITTWO01", 1), 1),
                        "edf_2300_drop_gap": round(edf_2300_drop, 1),
                    },
                    "boundary_curves": boundary_curves,
                },
                "signals": {
                    "ev_affinity_score": round(ev_affinity_score, 1),
                    "ev_supplier_share_pct": round(ev_sup_share * 100.0, 1),
                    "octopus_share_pct": round(octopus_share * 100.0, 1),
                    "ev_lift": round(ev_lift, 2),
                    "octopus_lift": round(octopus_lift, 2),
                    "domestic_footprint_score": round(domestic_footprint_score, 1),
                    "gsp_count": gsp_count,
                    "gsp_entropy": round(gsp_entropy, 2),
                    "base_bmu_share_pct": round(base_bmu_share * 100.0, 1),
                    "conservation_score": round(conservation_score, 1),
                    "one_sided_ratio_pct": round(one_sided_ratio * 100.0, 2),
                    "low_price_farming_score": round(low_price_farming_score, 1),
                    "pct_below_ssc": round(pct_below_ssc * 100.0, 1),
                    "pct_below_60": round(pct_below_60 * 100.0, 1),
                    "pct_negative_sbp": round(pct_negative_sbp * 100.0, 2),
                    "sp_price_corr": round(sp_price_corr, 3)
                    if sp_price_corr is not None
                    else None,
                    "daily_price_corr": round(daily_price_corr, 3)
                    if daily_price_corr is not None
                    else None,
                    "duty_cycle_score": round(duty_cycle_score, 1),
                    "active_hours_per_day": round(active_hours_per_day, 1),
                    "day_to_night_ratio": round(day_to_night_ratio, 2),
                    "pre_event_turnup_flag": pre_event_turnup_flag,
                    "persistence_score": round(persistence_score, 1),
                    "active_days": active_days,
                    "total_days": total_gran_days,
                    "daily_cov": round(daily_cov, 3),
                },
                "top_suppliers": top_suppliers,
                "sp_profile": sp_profile,
                "daily_series": daily_series,
                "gsp_breakdown": gsp_breakdown,
                "sub_bmus": sub_bmus,
            }
        )

    # Market-level verdict answering Question 3
    high_ev_cash = sum(
        v["comp_gbp"] for v in vtp_results if v["ev_focus_score"] >= 65
    )
    high_ev_high_risk_cash = sum(
        v["comp_gbp"]
        for v in vtp_results
        if v["ev_focus_score"] >= 65 and v["baselining_risk_score"] >= 65
    )
    high_ev_share = (
        high_ev_cash / market_total_comp * 100.0 if abs(market_total_comp) > 1 else 0.0
    )
    high_ev_high_risk_share = (
        high_ev_high_risk_cash / market_total_comp * 100.0
        if abs(market_total_comp) > 1
        else 0.0
    )
    tot_est_rev = sum(v["tariff_analysis"]["estimated_vtp_revenue_gbp"] for v in vtp_results)
    tot_peak_rev = sum(v["tariff_analysis"]["peak_tariff_revenue_gbp"] for v in vtp_results)
    tot_below_ssc_rev = sum(v["tariff_analysis"]["below_ssc_vtp_revenue_gbp"] for v in vtp_results)
    tot_deadweight = sum(v["tariff_analysis"]["deadweight_subsidy_gbp"] for v in vtp_results)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "granular_days": total_gran_days,
        "benchmarks": {
            "gb_ev_supplier_demand_share_pct": round(gb_ev_supplier_share * 100.0, 1),
            "gb_octopus_demand_share_pct": round(gb_octopus_share * 100.0, 1),
            "ev_tariff_suppliers": sorted(EV_TARIFF_SUPPLIERS),
        },
        "market_verdict": {
            "total_comp_gbp": round(market_total_comp, 2),
            "ev_focused_comp_gbp": round(high_ev_cash, 2),
            "ev_focused_share_pct": round(high_ev_share, 1),
            "ev_baselining_high_risk_gbp": round(high_ev_high_risk_cash, 2),
            "ev_baselining_high_risk_share_pct": round(high_ev_high_risk_share, 1),
            "total_estimated_vtp_revenue_gbp": round(tot_est_rev, 2),
            "total_peak_tariff_revenue_gbp": round(tot_peak_rev, 2),
            "total_below_ssc_vtp_revenue_gbp": round(tot_below_ssc_rev, 2),
            "total_deadweight_subsidy_gbp": round(tot_deadweight, 2),
            "headline": (
                f"{high_ev_share:.1f}% of VTP supplier compensation is driven by EV-focused "
                f"domestic aggregators, and {high_ev_high_risk_share:.1f}% shows strong "
                f"multi-signal signatures of baselining distortion."
                if total_gran_days > 0
                else "Ingest granular BMU×SP data to run EV baselining forensics."
            ),
        },
        "vtps": vtp_results,
    }
