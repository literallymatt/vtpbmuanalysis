"""BL01 (P376) & Self-Nominated Baseline Audit Engine for Elexon SAA-I014 Secondary BMUs.

Provides an objective, evidence-led assessment of Secondary BMU Settlement Expected
Volumes (SEV) against Actual Metered Volumes (QM) for Ofgem / Elexon Issue 127 & P510
policy evaluation. Focuses on structural rule distortions:
  1. Non-active baseline forecast error (MAE, RMSE, WAPE/MAPE, bias)
  2. Un-notified rebound leakage during inactive Settlement Periods (wmi == 0)
  3. Asymmetric activation selection ("free option" distribution shift)
  4. P376 BL01 (10-working-day / middle-2-of-4-weekend) reconstruction & frozen lookback drift
  5. Quantised / sparse self-nominated SEV detection & sign-inverted baseline flagging
  6. BL01 In-Day Adjustment (IDA) pre-event ramp diagnostics
  7. Counter-economic dispatch across System Buy Price regimes relative to SSC

Sign convention in SAA-I014:
  Demand is NEGATIVE (e.g., qm = -6.72 MWh, sev = -7.88 MWh).
  implied_dev = qm - sev:
    > 0 : actual demand was LESS than baseline (turn-down / reduced import)
    < 0 : actual demand was HIGHER than baseline (rebound / load surge)
  wmi > 0 (or abs(wmi) > 0): VTP notified a wholesale activation in that SP.
  wmi == 0: no wholesale activation notified in that SP.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Any

EPS = 1e-6
WMI_EPS = 1e-9
EVENT_DAY_MIN_ACTIVE_SPS = 4
_CACHE_MAX_ENTRIES = 8

PRICE_REGIME_ORDER = (
    "< £0",
    "£0–£50",
    "£50–£106 (Below SSC)",
    "£106–£180",
    "> £180/MWh",
)


@dataclass(slots=True)
class _RowRec:
    date: str
    sp: int
    sec_bmu_id: str
    sec_party_id: str
    gsp_group: str
    sev: float
    qm: float
    wmi: float
    wmi_flag: int
    qcv: float
    qsd: float
    qdei: float
    is_active: bool
    has_sev: bool
    implied_dev: float
    bl01_raw: float | None = None
    bl01_excl: float | None = None


@dataclass
class _BaseAuditCache:
    baseline_dates: list[str]
    sp_market: dict[tuple[str, int], dict[str, float]]
    slot_index: dict[tuple[str, int], int]
    by_bmu: dict[str, list[_RowRec]]
    by_party: dict[str, list[_RowRec]]
    active_bmu_days: set[tuple[str, str]]
    sign_inverted_bmus: set[str]
    market_summary: dict[str, Any]
    vtps_list: list[dict[str, Any]]
    vtp_by_id: dict[str, dict[str, Any]]
    vtp_ida_cache: dict[str, dict[str, Any]]
    sbmu_metrics_cache: dict[str, tuple[dict[str, Any], str, list[str]]]


_BASE_CACHE: OrderedDict[tuple[Any, ...], _BaseAuditCache] = OrderedDict()


def clear_audit_cache() -> None:
    """Clear the in-memory baseline audit base cache (useful in tests)."""
    _BASE_CACHE.clear()


def _sp_to_time(sp: int) -> str:
    hh = ((sp - 1) // 2) % 24
    mm = "00" if (sp - 1) % 2 == 0 else "30"
    return f"{hh:02d}:{mm}"


def _is_quantised_2dp(val: float) -> bool:
    """Return True if val is exact to 2 decimal places (0.01 MWh / 0.02 MW grid)."""
    scaled = val * 100.0
    return abs(scaled - round(scaled)) < 1e-4


def _middle_2_of_4(vals: list[float]) -> float:
    """BSC P376 BL01 weekend rule: drop highest and lowest of 4, average middle 2."""
    n = len(vals)
    if n == 1:
        return vals[0]
    if n == 2:
        return (vals[0] + vals[1]) * 0.5
    s = sorted(vals)
    if n == 3:
        return s[1]
    return (s[1] + s[2]) * 0.5


def _pearson_r2(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 5:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = 0.0
    dx = 0.0
    dy = 0.0
    for x, y in zip(xs, ys):
        ax = x - mx
        ay = y - my
        num += ax * ay
        dx += ax * ax
        dy += ay * ay
    if dx < 1e-12 or dy < 1e-12:
        return None
    r = num / math.sqrt(dx * dy)
    if r <= 0.0:
        return 0.0
    return max(0.0, min(1.0, r * r))


def _cod_r2(actual: list[float], pred: list[float]) -> float | None:
    """Coefficient of determination R^2 clamped to [0.0, 1.0]."""
    n = len(actual)
    if n < 5:
        return None
    mean_y = sum(actual) / n
    ss_tot = sum((y - mean_y) ** 2 for y in actual)
    if ss_tot < 1e-12:
        return 0.0
    ss_res = sum((y - yh) ** 2 for y, yh in zip(actual, pred))
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def _db_cache_key(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> tuple[Any, ...] | None:
    """Build a fast O(log N) collision-free cache key invalidated when DB contents change."""
    cur = conn.cursor()
    cur.row_factory = None
    has_row = cur.execute(
        "SELECT 1 FROM sbmu_baseline_sp WHERE settlement_date BETWEEN ? AND ? LIMIT 1",
        (start_date, end_date),
    ).fetchone()
    if has_row is None:
        return None
    db_list = cur.execute("PRAGMA database_list").fetchall()
    db_file = db_list[0][2] if db_list else ""
    db_ident = db_file if db_file else f":mem:{id(conn)}"
    base_max_rowid = cur.execute(
        "SELECT COALESCE(MAX(rowid), 0) FROM sbmu_baseline_sp"
    ).fetchone()[0]
    ing_cnt, ing_max_at = cur.execute(
        "SELECT COUNT(*), COALESCE(MAX(ingested_at), '') FROM ingested_days WHERE has_sbmu_baselines = 1"
    ).fetchone()
    sp_max_rowid = cur.execute(
        "SELECT COALESCE(MAX(rowid), 0) FROM sp_market_data"
    ).fetchone()[0]
    party_cnt = cur.execute("SELECT COUNT(*) FROM parties").fetchone()[0]
    return (
        db_ident,
        start_date,
        end_date,
        base_max_rowid,
        ing_cnt,
        ing_max_at,
        sp_max_rowid,
        party_cnt,
    )


def _load_party_map(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    cur = conn.cursor()
    cur.row_factory = None
    out: dict[str, dict[str, Any]] = {}
    for pid, cname, rjson in cur.execute(
        "SELECT party_id, company_name, roles_json FROM parties"
    ):
        out[pid] = {
            "company_name": cname,
            "roles": json.loads(rjson or "[]"),
        }
    return out


def _reconstruct_bl01_for_bmu(bmu_rows: list[_RowRec]) -> None:
    """Attach bl01_raw and bl01_excl to each _RowRec for a single Secondary BMU."""
    by_date: dict[str, dict[int, _RowRec]] = defaultdict(dict)
    active_sps_per_day: dict[str, int] = defaultdict(int)
    for rec in bmu_rows:
        by_date[rec.date][rec.sp] = rec
        if rec.is_active:
            active_sps_per_day[rec.date] += 1

    sorted_dates = sorted(by_date.keys())
    prior_wd_all: list[dict[int, float]] = []
    prior_we_all: list[dict[int, float]] = []
    prior_wd_clean: list[dict[int, float]] = []
    prior_we_clean: list[dict[int, float]] = []

    for d in sorted_dates:
        is_we = dt.date.fromisoformat(d).weekday() >= 5
        sp_map = by_date[d]

        if not is_we:
            wd_raw_slice = prior_wd_all[-10:]
            wd_excl_slice = prior_wd_clean[-10:]
            has_raw_wd = len(wd_raw_slice) >= 2
            has_excl_wd = len(wd_excl_slice) >= 2
            if has_raw_wd or has_excl_wd:
                for sp, rec in sp_map.items():
                    if has_raw_wd:
                        vals_raw = [dm[sp] for dm in wd_raw_slice if sp in dm]
                        if len(vals_raw) >= 2:
                            rec.bl01_raw = sum(vals_raw) / len(vals_raw)
                    if has_excl_wd:
                        vals_excl = [dm[sp] for dm in wd_excl_slice if sp in dm]
                        if len(vals_excl) >= 2:
                            rec.bl01_excl = sum(vals_excl) / len(vals_excl)
        else:
            we_raw_slice = prior_we_all[-4:]
            we_excl_slice = prior_we_clean[-4:]
            has_raw_we = len(we_raw_slice) >= 1
            has_excl_we = len(we_excl_slice) >= 1
            if has_raw_we or has_excl_we:
                for sp, rec in sp_map.items():
                    if has_raw_we:
                        vals_raw = [dm[sp] for dm in we_raw_slice if sp in dm]
                        if vals_raw:
                            rec.bl01_raw = _middle_2_of_4(vals_raw)
                    if has_excl_we:
                        vals_excl = [dm[sp] for dm in we_excl_slice if sp in dm]
                        if vals_excl:
                            rec.bl01_excl = _middle_2_of_4(vals_excl)

        qm_today = {sp: rec.qm for sp, rec in sp_map.items()}
        is_event_day = active_sps_per_day[d] >= EVENT_DAY_MIN_ACTIVE_SPS
        if not is_we:
            prior_wd_all.append(qm_today)
            if not is_event_day:
                prior_wd_clean.append(qm_today)
        else:
            prior_we_all.append(qm_today)
            if not is_event_day:
                prior_we_clean.append(qm_today)


def _compute_ida_pre_ramp(
    rows: list[_RowRec],
    slot_index: dict[tuple[str, int], int],
) -> dict[str, Any]:
    """Measure pre-event actual vs baseline demand (offsets -6..-1 SPs) before wmi: 0 -> >0."""
    by_bmu: dict[str, dict[int, _RowRec]] = defaultdict(dict)
    for rec in rows:
        t = slot_index.get((rec.date, rec.sp))
        if t is not None:
            by_bmu[rec.sec_bmu_id][t] = rec

    event_offsets: dict[int, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0])
    )
    event_has_valid: set[int] = set()

    for _bmu_id, slot_map in by_bmu.items():
        for t, rec in slot_map.items():
            if not rec.is_active:
                continue
            prev_rec = slot_map.get(t - 1)
            if prev_rec is None or prev_rec.is_active:
                continue
            found_any = False
            for k in (-6, -5, -4, -3, -2, -1):
                pre = slot_map.get(t + k)
                if pre is None or pre.is_active or not pre.has_sev:
                    continue
                acc = event_offsets[t][k]
                acc[0] += -pre.qm * 2.0
                acc[1] += -pre.sev * 2.0
                found_any = True
            if found_any:
                event_has_valid.add(t)

    offsets_out = []
    excess_vals = []
    for k in (-6, -5, -4, -3, -2, -1):
        actuals = []
        baselines = []
        for t in event_has_valid:
            if k in event_offsets[t]:
                actuals.append(event_offsets[t][k][0])
                baselines.append(event_offsets[t][k][1])
        if actuals:
            avg_act = sum(actuals) / len(actuals)
            avg_base = sum(baselines) / len(baselines)
            exc = avg_act - avg_base
            excess_vals.append(exc)
        else:
            avg_act = 0.0
            avg_base = 0.0
            exc = 0.0
        hours = k * 0.5
        offsets_out.append(
            {
                "offset_sp": k,
                "label": f"{k} SP ({hours:+.1f}h)",
                "avg_actual_mw": round(avg_act, 3),
                "avg_baseline_mw": round(avg_base, 3),
                "excess_load_mw": round(exc, 3),
            }
        )

    pre_ramp_excess_mw = (
        sum(excess_vals) / len(excess_vals) if excess_vals else 0.0
    )
    return {
        "pre_event_window_sp_offsets": offsets_out,
        "transitions_count": len(event_has_valid),
        "pre_ramp_excess_mw": round(pre_ramp_excess_mw, 3),
    }


def _classify_methodology(
    sev_obs_count: int,
    is_sign_inverted: bool,
    sev_coverage_pct: float,
    quantised_2dp_pct: float,
    bl01_r2: float | None,
    bl01_shape_r2: float | None,
    inact_bl01_r2: float | None,
    inact_shape_r2: float | None,
    bl01_mae_mwh: float | None,
    bl01_drift_mwh: float | None,
    mean_abs_sev: float,
    active_day_pct: float,
    rebound_leakage_pct: float,
    non_active_mae_mwh: float,
    non_active_mape_pct: float | None,
) -> tuple[str, list[str]]:
    """Classify baseline methodology with transparent, objective evidence statements."""
    reasons: list[str] = []

    if sev_obs_count < 10:
        return (
            "Insufficient Baseline Data",
            [
                f"Only {sev_obs_count} settlement periods carry a non-zero SEV baseline in this window."
            ],
        )

    if is_sign_inverted:
        return (
            "Sign-Inverted / Test SEV",
            [
                "Submitted SEV values carry a positive sign (mean SEV > 0) against negative metered demand "
                "(mean QM < 0), indicating a sign-convention inversion or test baseline feed rather than a "
                "valid demand counterfactual.",
                "Excluded from market-wide demand rebound totals to avoid inflating unsettled rebound leakage.",
            ],
        )

    drift_ratio = (
        (bl01_drift_mwh / mean_abs_sev)
        if (bl01_drift_mwh is not None and mean_abs_sev > EPS)
        else 0.0
    )

    best_shape_r2 = max(
        (v for v in (bl01_shape_r2, inact_shape_r2) if v is not None),
        default=None,
    )
    best_cod_r2 = max(
        (v for v in (bl01_r2, inact_bl01_r2) if v is not None),
        default=None,
    )

    # Strong direct P376 BL01 fit overrides sparse-portfolio dilution (e.g., dormant GSP BMUs)
    strong_direct_bl01 = (
        best_cod_r2 is not None and best_cod_r2 >= 0.85 and quantised_2dp_pct < 40.0
    )

    if sev_coverage_pct < 45.0 and not strong_direct_bl01:
        cls = "Self-Nominated (Sparse / Event-Only)"
        reasons.append(
            f"SEV is populated on only {sev_coverage_pct:.1f}% of load/active settlement periods, "
            f"leaving non-active periods largely without a settlement baseline for forecast auditing."
        )
        if quantised_2dp_pct >= 60.0:
            reasons.append(
                f"{quantised_2dp_pct:.1f}% of populated SEV values sit on exact 0.01 MWh (2dp) increments, "
                f"consistent with party-submitted nominations."
            )
    elif quantised_2dp_pct >= 75.0 and (best_cod_r2 is None or best_cod_r2 < 0.85):
        cls = "Self-Nominated (Quantised SEV)"
        reasons.append(
            f"{quantised_2dp_pct:.1f}% of non-zero SEV values are exact to 2 decimal places (0.01 MWh grid), "
            f"far above the ~10% expected from metered 10-day historical averaging."
        )
        if bl01_r2 is not None:
            reasons.append(
                f"Reconstructed P376 BL01 explains R² = {bl01_r2:.2f} of settled SEV variance "
                f"(MAE {bl01_mae_mwh:.3f} MWh/SP), confirming divergence from standard historic averaging."
            )
    elif (
        strong_direct_bl01
        or (best_cod_r2 is not None and best_cod_r2 >= 0.60)
        or (
            best_shape_r2 is not None
            and best_shape_r2 >= 0.65
            and quantised_2dp_pct < 60.0
        )
    ):
        is_frozen = (drift_ratio >= 0.12 and active_day_pct >= 50.0) or (
            active_day_pct >= 75.0 and drift_ratio >= 0.08
        )
        r2_disp = (
            bl01_r2
            if bl01_r2 is not None
            else (best_shape_r2 if best_shape_r2 is not None else 0.0)
        )
        if is_frozen:
            cls = "BL01 (P376 — Frozen Lookback)"
            if inact_shape_r2 is not None and (bl01_r2 is None or inact_shape_r2 > bl01_r2 + 0.1):
                fit_note = f"non-active SP BL01 shape R² = {inact_shape_r2:.2f} (overall R² = {r2_disp:.2f})"
            else:
                fit_note = f"R² = {r2_disp:.2f}"
            reasons.append(
                f"Continuous SEV coverage ({sev_coverage_pct:.1f}%) with 3dp+ metered precision "
                f"({quantised_2dp_pct:.1f}% at 2dp) and strong P376 BL01 alignment ({fit_note})."
            )
            reasons.append(
                f"Active on {active_day_pct:.0f}% of days with settled SEV sitting "
                f"+{bl01_drift_mwh:.3f} MWh/SP ({drift_ratio * 100:.1f}%) above rolling 10-working-day "
                f"actual demand during active SPs — indicative of P376 Event-Day exclusion lookback freeze."
            )
        else:
            cls = "BL01 (P376 Historic Average)"
            reasons.append(
                f"SEV with 3dp+ precision ({quantised_2dp_pct:.1f}% at 2dp; {sev_coverage_pct:.1f}% coverage) "
                f"closely matches reconstructed P376 BL01 "
                f"(R² = {r2_disp:.2f}, MAE {(bl01_mae_mwh or 0.0):.3f} MWh/SP)."
            )
            if bl01_drift_mwh is not None and abs(drift_ratio) >= 0.05:
                reasons.append(
                    f"Mean settled SEV drift vs rolling 10-working-day actuals is "
                    f"{bl01_drift_mwh:+.3f} MWh/SP ({drift_ratio * 100:+.1f}% of mean baseline demand)."
                )
    elif quantised_2dp_pct >= 75.0:
        cls = "Self-Nominated (Quantised SEV)"
        reasons.append(
            f"{quantised_2dp_pct:.1f}% of populated SEV values sit on exact 0.01 MWh (2dp) increments "
            f"across {sev_coverage_pct:.1f}% SEV coverage."
        )
    else:
        cls = "Hybrid / Custom Baseline"
        r2_txt = f"R² = {bl01_r2:.2f}" if bl01_r2 is not None else "insufficient lookback"
        inact_txt = (
            f"; non-active shape R² = {inact_shape_r2:.2f}"
            if inact_shape_r2 is not None
            else ""
        )
        reasons.append(
            f"Continuous SEV coverage ({sev_coverage_pct:.1f}%) with low 2dp quantisation "
            f"({quantised_2dp_pct:.1f}%), but weak fit to standard P376 BL01 ({r2_txt}{inact_txt}), "
            f"consistent with a bespoke, ML, or custom baseline methodology."
        )

    if non_active_mae_mwh > 0.001:
        mape_part = (
            f" ({non_active_mape_pct:.1f}% WAPE)"
            if non_active_mape_pct is not None
            else ""
        )
        reasons.append(
            f"During non-active SPs (wmi = 0), baseline forecast MAE is {non_active_mae_mwh:.3f} MWh/SP{mape_part}."
        )
    if rebound_leakage_pct >= 15.0:
        reasons.append(
            f"Un-notified demand exceeding baseline on active days equals {rebound_leakage_pct:.1f}% "
            f"of settled wholesale turn-down volume."
        )

    return cls, reasons


def _aggregate_metrics(
    rows: list[_RowRec],
    sp_market: dict[tuple[str, int], dict[str, float]],
    slot_index: dict[tuple[str, int], int],
    total_baseline_days: int,
    active_bmu_days: set[tuple[str, str]],
    sign_inverted_bmus: set[str],
    compute_ida: bool = True,
) -> tuple[dict[str, Any], str, list[str], dict[str, Any] | None]:
    """Compute full audit KPIs, methodology classification, and optional IDA pre-ramp."""
    sbmu_ids = {r.sec_bmu_id for r in rows}
    active_dates: set[str] = set()

    settled_turndown_mwh = 0.0
    unsettled_rebound_mwh = 0.0
    implied_unsettled_comp_gbp = 0.0

    non_active_devs: list[float] = []
    non_active_abs_qm_sum = 0.0
    active_devs: list[float] = []

    sev_obs = 0
    quantised_2dp_obs = 0
    load_or_active_obs = 0
    sum_abs_sev = 0.0
    sum_signed_sev = 0.0
    sum_signed_qm = 0.0

    # BL01 comparison arrays
    bl01_raw_sev: list[float] = []
    bl01_raw_pred: list[float] = []
    bl01_raw_act_sev: list[float] = []
    bl01_raw_act_pred: list[float] = []
    bl01_raw_inact_sev: list[float] = []
    bl01_raw_inact_pred: list[float] = []
    bl01_excl_sev: list[float] = []
    bl01_excl_pred: list[float] = []

    for r in rows:
        mkt = sp_market.get((r.date, r.sp))
        ssc = mkt["ssc"] if mkt else 0.0
        bmu_inverted = r.sec_bmu_id in sign_inverted_bmus

        if r.has_sev or abs(r.qm) > EPS or r.is_active:
            load_or_active_obs += 1
        if r.has_sev:
            sev_obs += 1
            sum_abs_sev += abs(r.sev)
            sum_signed_sev += r.sev
            sum_signed_qm += r.qm
            if _is_quantised_2dp(r.sev):
                quantised_2dp_obs += 1

        if r.is_active:
            active_dates.add(r.date)
            if r.has_sev or abs(r.qm) > EPS:
                active_devs.append(r.implied_dev)
            if r.implied_dev > 0 and not bmu_inverted:
                settled_turndown_mwh += r.implied_dev
        else:
            if r.has_sev and not bmu_inverted:
                non_active_devs.append(r.implied_dev)
                non_active_abs_qm_sum += abs(r.qm)
                if r.implied_dev < 0 and (r.sec_bmu_id, r.date) in active_bmu_days:
                    reb = -r.implied_dev
                    unsettled_rebound_mwh += reb
                    implied_unsettled_comp_gbp += reb * ssc

        if r.has_sev and not bmu_inverted:
            if r.bl01_raw is not None:
                bl01_raw_sev.append(r.sev)
                bl01_raw_pred.append(r.bl01_raw)
                if r.is_active:
                    bl01_raw_act_sev.append(r.sev)
                    bl01_raw_act_pred.append(r.bl01_raw)
                else:
                    bl01_raw_inact_sev.append(r.sev)
                    bl01_raw_inact_pred.append(r.bl01_raw)
            if r.bl01_excl is not None:
                bl01_excl_sev.append(r.sev)
                bl01_excl_pred.append(r.bl01_excl)

    # Portfolio/SBMU is sign-inverted if all its SEV-bearing SBMUs are sign-inverted
    # (or aggregate mean SEV > 0.05 while mean QM < -0.05)
    is_sign_inverted = bool(
        sev_obs >= 10
        and (
            (sbmu_ids and sbmu_ids.issubset(sign_inverted_bmus))
            or (
                (sum_signed_sev / sev_obs) > 0.05
                and (sum_signed_qm / sev_obs) < -0.05
                and settled_turndown_mwh < 1.0
            )
        )
    )

    n_inact = len(non_active_devs)
    if n_inact > 0:
        non_active_abs_err = sum(abs(d) for d in non_active_devs)
        non_active_mae = non_active_abs_err / n_inact
        non_active_rmse = math.sqrt(sum(d * d for d in non_active_devs) / n_inact)
        non_active_bias = sum(non_active_devs) / n_inact
        over_forecast_rate = (
            sum(1 for d in non_active_devs if d > 0) / n_inact * 100.0
        )
        non_active_mape = (
            (non_active_abs_err / non_active_abs_qm_sum * 100.0)
            if non_active_abs_qm_sum > EPS
            else None
        )
        inactive_mean_dev = non_active_bias
        inactive_pos_pct = over_forecast_rate
    else:
        non_active_mae = 0.0
        non_active_rmse = 0.0
        non_active_bias = 0.0
        over_forecast_rate = 0.0
        non_active_mape = None
        inactive_mean_dev = 0.0
        inactive_pos_pct = 0.0

    n_act = len(active_devs)
    if n_act > 0:
        active_mean_dev = sum(active_devs) / n_act
        active_pos_pct = sum(1 for d in active_devs if d > 0) / n_act * 100.0
    else:
        active_mean_dev = 0.0
        active_pos_pct = 0.0

    # Guard rebound_leakage_pct when settled turn-down is negligible (< 5 MWh) to avoid
    # division-by-tiny-number distortions while keeping float type for frontend contract.
    if settled_turndown_mwh >= 5.0:
        rebound_leakage_pct = unsettled_rebound_mwh / settled_turndown_mwh * 100.0
    elif settled_turndown_mwh >= 1.0:
        rebound_leakage_pct = min(
            500.0, unsettled_rebound_mwh / settled_turndown_mwh * 100.0
        )
    else:
        rebound_leakage_pct = 0.0

    quantised_2dp_pct = (
        (quantised_2dp_obs / sev_obs * 100.0) if sev_obs > 0 else 0.0
    )
    sev_coverage_pct = (
        (sev_obs / load_or_active_obs * 100.0) if load_or_active_obs > 0 else 0.0
    )
    mean_abs_sev = (sum_abs_sev / sev_obs) if sev_obs > 0 else 0.0

    # BL01 fit: evaluate event-excluded, non-active raw, and all-SP raw
    r2_raw = _cod_r2(bl01_raw_sev, bl01_raw_pred) if len(bl01_raw_sev) >= 10 else None
    r2_excl = (
        _cod_r2(bl01_excl_sev, bl01_excl_pred) if len(bl01_excl_sev) >= 10 else None
    )
    inact_r2_raw = (
        _cod_r2(bl01_raw_inact_sev, bl01_raw_inact_pred)
        if len(bl01_raw_inact_sev) >= 10
        else None
    )
    shape_r2 = (
        _pearson_r2(bl01_raw_sev, bl01_raw_pred)
        if len(bl01_raw_sev) >= 10
        else None
    )
    inact_shape_r2 = (
        _pearson_r2(bl01_raw_inact_sev, bl01_raw_inact_pred)
        if len(bl01_raw_inact_sev) >= 10
        else None
    )

    # Choose best representative BL01 R^2 & MAE:
    # 1. Event-excluded BL01 when available and at least as accurate as raw
    # 2. Non-active-SP BL01 when continuous daily activations depress active-SP bl01_raw
    # 3. All-SP raw BL01
    candidates: list[tuple[float, list[float], list[float]]] = []
    if r2_excl is not None:
        candidates.append((r2_excl, bl01_excl_sev, bl01_excl_pred))
    if inact_r2_raw is not None:
        candidates.append((inact_r2_raw, bl01_raw_inact_sev, bl01_raw_inact_pred))
    if r2_raw is not None:
        candidates.append((r2_raw, bl01_raw_sev, bl01_raw_pred))

    if candidates:
        bl01_r2, best_y, best_yh = max(candidates, key=lambda item: item[0])
        bl01_mae: float | None = sum(
            abs(y - yh) for y, yh in zip(best_y, best_yh)
        ) / len(best_y)
    else:
        bl01_r2 = None
        bl01_mae = None

    # Drift: evaluate over active SPs where available so daytime turn-down drift is not
    # masked by overnight rebound; positive means settled baseline demand (-sev) sits
    # ABOVE rolling 10-working-day recent actuals (-bl01_raw).
    if bl01_raw_act_sev:
        bl01_drift: float | None = sum(
            yh - y for y, yh in zip(bl01_raw_act_sev, bl01_raw_act_pred)
        ) / len(bl01_raw_act_sev)
        drift_denom_abs_sev = sum(abs(y) for y in bl01_raw_act_sev) / len(
            bl01_raw_act_sev
        )
    elif bl01_raw_sev:
        bl01_drift = sum(
            yh - y for y, yh in zip(bl01_raw_sev, bl01_raw_pred)
        ) / len(bl01_raw_sev)
        drift_denom_abs_sev = mean_abs_sev
    else:
        bl01_drift = None
        drift_denom_abs_sev = mean_abs_sev

    ida: dict[str, Any] | None = None
    ida_pre_ramp_mw: float | None = None
    if compute_ida:
        ida = _compute_ida_pre_ramp(rows, slot_index)
        ida_pre_ramp_mw = (
            ida["pre_ramp_excess_mw"] if ida["transitions_count"] > 0 else None
        )

    active_day_pct = (
        (len(active_dates) / max(1, total_baseline_days) * 100.0)
        if total_baseline_days > 0
        else 0.0
    )

    cls, reasons = _classify_methodology(
        sev_obs_count=sev_obs,
        is_sign_inverted=is_sign_inverted,
        sev_coverage_pct=sev_coverage_pct,
        quantised_2dp_pct=quantised_2dp_pct,
        bl01_r2=bl01_r2,
        bl01_shape_r2=shape_r2,
        inact_bl01_r2=inact_r2_raw,
        inact_shape_r2=inact_shape_r2,
        bl01_mae_mwh=bl01_mae,
        bl01_drift_mwh=bl01_drift,
        mean_abs_sev=drift_denom_abs_sev,
        active_day_pct=active_day_pct,
        rebound_leakage_pct=rebound_leakage_pct,
        non_active_mae_mwh=non_active_mae,
        non_active_mape_pct=non_active_mape,
    )

    metrics = {
        "sbmu_count": len(sbmu_ids),
        "active_days": len(active_dates),
        "settled_turndown_mwh": round(settled_turndown_mwh, 2),
        "unsettled_rebound_mwh": round(unsettled_rebound_mwh, 2),
        "rebound_leakage_pct": round(rebound_leakage_pct, 1),
        "implied_unsettled_comp_gbp": round(implied_unsettled_comp_gbp, 2),
        "non_active_mae_mwh": round(non_active_mae, 4),
        "non_active_rmse_mwh": round(non_active_rmse, 4),
        "non_active_mape_pct": round(non_active_mape, 1)
        if non_active_mape is not None
        else None,
        "non_active_bias_mwh": round(non_active_bias, 4),
        "over_forecast_rate_pct": round(over_forecast_rate, 1),
        "active_mean_dev_mwh": round(active_mean_dev, 4),
        "inactive_mean_dev_mwh": round(inactive_mean_dev, 4),
        "active_positive_pct": round(active_pos_pct, 1),
        "inactive_positive_pct": round(inactive_pos_pct, 1),
        "bl01_r2": round(bl01_r2, 3) if bl01_r2 is not None else None,
        "bl01_mae_mwh": round(bl01_mae, 4) if bl01_mae is not None else None,
        "bl01_drift_mwh": round(bl01_drift, 4) if bl01_drift is not None else None,
        "quantised_2dp_pct": round(quantised_2dp_pct, 1),
        "sev_coverage_pct": round(sev_coverage_pct, 1),
        "ida_pre_ramp_mw": round(ida_pre_ramp_mw, 3)
        if ida_pre_ramp_mw is not None
        else None,
    }
    return metrics, cls, reasons, ida


def _build_sp_overlay(
    rows: list[_RowRec],
    baseline_dates: list[str],
    sp_market: dict[tuple[str, int], dict[str, float]],
    active_bmu_days: set[tuple[str, str]],
    sign_inverted_bmus: set[str],
) -> list[dict[str, Any]]:
    """Build 48-SP demand overlay in positive MW magnitudes (-sev*2 and -qm*2)."""
    n_days = max(1, len(baseline_dates))
    base_mw_sum = [0.0] * 48
    act_mw_sum = [0.0] * 48
    td_mw_sum = [0.0] * 48
    reb_mw_sum = [0.0] * 48
    sp_total_rows = [0] * 48
    sp_active_rows = [0] * 48

    for r in rows:
        if not (1 <= r.sp <= 48):
            continue
        idx = r.sp - 1
        sp_total_rows[idx] += 1
        bmu_inverted = r.sec_bmu_id in sign_inverted_bmus
        if r.has_sev:
            base_mw_sum[idx] += -r.sev * 2.0
        act_mw_sum[idx] += -r.qm * 2.0
        if r.is_active:
            sp_active_rows[idx] += 1
            if r.implied_dev > 0 and not bmu_inverted:
                td_mw_sum[idx] += r.implied_dev * 2.0
        else:
            if (
                r.has_sev
                and not bmu_inverted
                and r.implied_dev < 0
                and (r.sec_bmu_id, r.date) in active_bmu_days
            ):
                reb_mw_sum[idx] += (-r.implied_dev) * 2.0

    out = []
    for sp in range(1, 49):
        idx = sp - 1
        sbps = [
            sp_market[(d, sp)]["sbp"]
            for d in baseline_dates
            if (d, sp) in sp_market
        ]
        sscs = [
            sp_market[(d, sp)]["ssc"]
            for d in baseline_dates
            if (d, sp) in sp_market
        ]
        avg_sbp = sum(sbps) / len(sbps) if sbps else 0.0
        avg_ssc = sum(sscs) / len(sscs) if sscs else 0.0
        act_rate = (
            (sp_active_rows[idx] / sp_total_rows[idx] * 100.0)
            if sp_total_rows[idx] > 0
            else 0.0
        )
        out.append(
            {
                "sp": sp,
                "time": _sp_to_time(sp),
                "baseline_demand_mw": round(base_mw_sum[idx] / n_days, 3),
                "actual_demand_mw": round(act_mw_sum[idx] / n_days, 3),
                "settled_turndown_mw": round(td_mw_sum[idx] / n_days, 3),
                "unsettled_rebound_mw": round(reb_mw_sum[idx] / n_days, 3),
                "avg_sbp": round(avg_sbp, 2),
                "avg_ssc": round(avg_ssc, 2),
                "activation_rate_pct": round(act_rate, 1),
            }
        )
    return out


def _build_cherry_pick_hist(
    rows: list[_RowRec],
    sign_inverted_bmus: set[str],
) -> list[dict[str, Any]]:
    """Build symmetric-around-zero histogram of implied_dev = qm - sev for active vs inactive SPs."""
    active_devs = [
        r.implied_dev
        for r in rows
        if r.is_active
        and r.sec_bmu_id not in sign_inverted_bmus
        and (r.has_sev or abs(r.qm) > EPS)
    ]
    inactive_devs = [
        r.implied_dev
        for r in rows
        if not r.is_active
        and r.has_sev
        and r.sec_bmu_id not in sign_inverted_bmus
    ]
    combined = active_devs + inactive_devs
    if not combined:
        return []

    abs_sorted = sorted(abs(v) for v in combined)
    p98_idx = min(len(abs_sorted) - 1, int(len(abs_sorted) * 0.98))
    max_abs = max(0.1, abs_sorted[p98_idx])
    half_bins = 8
    raw_step = max_abs / half_bins
    mag = 10 ** math.floor(math.log10(max(raw_step, 1e-4)))
    norm = raw_step / mag
    if norm <= 1.0:
        step = 1.0 * mag
    elif norm <= 2.0:
        step = 2.0 * mag
    elif norm <= 2.5:
        step = 2.5 * mag
    elif norm <= 5.0:
        step = 5.0 * mag
    else:
        step = 10.0 * mag

    total_bins = half_bins * 2
    lo_bound = -half_bins * step
    act_counts = [0] * total_bins
    inact_counts = [0] * total_bins

    def _bin_idx(v: float) -> int:
        idx = int(math.floor((v - lo_bound) / step))
        return max(0, min(total_bins - 1, idx))

    for v in active_devs:
        act_counts[_bin_idx(v)] += 1
    for v in inactive_devs:
        inact_counts[_bin_idx(v)] += 1

    n_act = len(active_devs)
    n_inact = len(inactive_devs)
    decimals = 2 if step < 0.25 else (1 if step < 2.0 else 0)

    out = []
    for i in range(total_bins):
        b_lo = lo_bound + i * step
        b_hi = b_lo + step
        center = (b_lo + b_hi) * 0.5
        out.append(
            {
                "bin_label": f"{center:+.{decimals}f}",
                "bin_center": round(center, 4),
                "active_pct": round(act_counts[i] / n_act * 100.0, 2) if n_act > 0 else 0.0,
                "inactive_pct": round(inact_counts[i] / n_inact * 100.0, 2)
                if n_inact > 0
                else 0.0,
                "active_count": act_counts[i],
                "inactive_count": inact_counts[i],
            }
        )
    return out


def _build_bl01_daily_series(
    rows: list[_RowRec],
    baseline_dates: list[str],
    active_bmu_days: set[tuple[str, str]],
    sign_inverted_bmus: set[str],
) -> list[dict[str, Any]]:
    """Build daily demand series comparing actual, settled SEV, BL01 raw, and BL01 event-excluded."""
    by_day: dict[str, list[_RowRec]] = defaultdict(list)
    for r in rows:
        by_day[r.date].append(r)

    out = []
    for d in baseline_dates:
        day_rows = by_day.get(d, [])
        dow = dt.date.fromisoformat(d).strftime("%a")
        actual_dem = sum(-r.qm for r in day_rows)
        sev_dem = sum(-r.sev for r in day_rows if r.has_sev)
        raw_vals = [-r.bl01_raw for r in day_rows if r.bl01_raw is not None]
        excl_vals = [-r.bl01_excl for r in day_rows if r.bl01_excl is not None]
        active_sps = len({r.sp for r in day_rows if r.is_active})
        settled_td = sum(
            r.implied_dev
            for r in day_rows
            if r.is_active and r.implied_dev > 0 and r.sec_bmu_id not in sign_inverted_bmus
        )
        unsettled_reb = sum(
            -r.implied_dev
            for r in day_rows
            if not r.is_active
            and r.has_sev
            and r.implied_dev < 0
            and r.sec_bmu_id not in sign_inverted_bmus
            and (r.sec_bmu_id, r.date) in active_bmu_days
        )
        out.append(
            {
                "date": d,
                "dow": dow,
                "actual_demand_mwh": round(actual_dem, 2),
                "settled_sev_mwh": round(sev_dem, 2),
                "bl01_raw_mwh": round(sum(raw_vals), 2) if raw_vals else None,
                "bl01_excl_mwh": round(sum(excl_vals), 2) if excl_vals else None,
                "active_sps": active_sps,
                "settled_turndown_mwh": round(settled_td, 2),
                "unsettled_rebound_mwh": round(unsettled_reb, 2),
            }
        )
    return out


def _regime_for_sp(sbp: float, ssc: float) -> str:
    ssc_thresh = ssc if ssc > 50.0 else 106.0
    if sbp < 0.0:
        return "< £0"
    if sbp < 50.0:
        return "£0–£50"
    if sbp < ssc_thresh:
        return "£50–£106 (Below SSC)"
    if sbp < 180.0:
        return "£106–£180"
    return "> £180/MWh"


def _build_price_regimes(
    rows: list[_RowRec],
    sp_market: dict[tuple[str, int], dict[str, float]],
    active_bmu_days: set[tuple[str, str]],
    sign_inverted_bmus: set[str],
) -> list[dict[str, Any]]:
    """Aggregate settled turn-down, turn-up, and unsettled rebound across 5 SBP regimes."""
    buckets: dict[str, dict[str, Any]] = {
        name: {
            "sps": set(),
            "sbp_by_sp": {},
            "row_count": 0,
            "active_row_count": 0,
            "turndown": 0.0,
            "turnup": 0.0,
            "rebound": 0.0,
        }
        for name in PRICE_REGIME_ORDER
    }

    for r in rows:
        mkt = sp_market.get((r.date, r.sp))
        if not mkt:
            continue
        sbp = mkt["sbp"]
        ssc = mkt["ssc"]
        reg = _regime_for_sp(sbp, ssc)
        b = buckets[reg]
        key = (r.date, r.sp)
        b["sps"].add(key)
        b["sbp_by_sp"][key] = sbp
        b["row_count"] += 1
        bmu_inverted = r.sec_bmu_id in sign_inverted_bmus
        if r.is_active:
            b["active_row_count"] += 1
            if not bmu_inverted:
                if r.implied_dev > 0:
                    b["turndown"] += r.implied_dev
                elif r.implied_dev < 0:
                    b["turnup"] += -r.implied_dev
        else:
            if (
                r.has_sev
                and not bmu_inverted
                and r.implied_dev < 0
                and (r.sec_bmu_id, r.date) in active_bmu_days
            ):
                b["rebound"] += -r.implied_dev

    out = []
    for name in PRICE_REGIME_ORDER:
        b = buckets[name]
        sbp_vals = list(b["sbp_by_sp"].values())
        avg_sbp = sum(sbp_vals) / len(sbp_vals) if sbp_vals else 0.0
        act_rate = (
            (b["active_row_count"] / b["row_count"] * 100.0)
            if b["row_count"] > 0
            else 0.0
        )
        out.append(
            {
                "regime": name,
                "sps_count": len(b["sps"]),
                "settled_turndown_mwh": round(b["turndown"], 2),
                "settled_turnup_mwh": round(b["turnup"], 2),
                "unsettled_rebound_mwh": round(b["rebound"], 2),
                "avg_sbp": round(avg_sbp, 2),
                "activation_rate_pct": round(act_rate, 1),
            }
        )
    return out


def _get_or_build_base(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
) -> _BaseAuditCache | None:
    """Load, reconstruct BL01, and cache base market & VTP summaries for a date window."""
    cache_key = _db_cache_key(conn, start_date, end_date)
    if cache_key is None:
        return None

    cached = _BASE_CACHE.get(cache_key)
    if cached is not None:
        _BASE_CACHE.move_to_end(cache_key)
        return cached

    party_map = _load_party_map(conn)

    cur = conn.cursor()
    cur.row_factory = None

    baseline_dates = [
        r[0]
        for r in cur.execute(
            """
            SELECT DISTINCT settlement_date
            FROM sbmu_baseline_sp
            WHERE settlement_date BETWEEN ? AND ?
            ORDER BY settlement_date
            """,
            (start_date, end_date),
        )
    ]
    baseline_days = len(baseline_dates)
    if baseline_days == 0:
        return None

    sp_market: dict[tuple[str, int], dict[str, float]] = {}
    for d, sp, ssc, sbp, mpj in cur.execute(
        """
        SELECT settlement_date, sp, ssc, sbp, mpj
        FROM sp_market_data
        WHERE settlement_date BETWEEN ? AND ?
        """,
        (start_date, end_date),
    ):
        sp_market[(d, int(sp))] = {
            "ssc": float(ssc or 0.0),
            "sbp": float(sbp or 0.0),
            "mpj": float(mpj or 0.0),
        }

    # Fetch plain tuples (4-5x faster than sqlite3.Row on 650k+ rows)
    all_rows: list[_RowRec] = []
    by_bmu: dict[str, list[_RowRec]] = defaultdict(list)
    by_party: dict[str, list[_RowRec]] = defaultdict(list)
    max_sp_per_day: dict[str, int] = defaultdict(lambda: 48)

    for (
        d,
        sp_raw,
        sec_bmu_id,
        sec_party_id,
        gsp_group,
        sev_raw,
        qm_raw,
        wmi_raw,
        wmi_flag_raw,
        qcv_raw,
        qsd_raw,
        qdei_raw,
    ) in cur.execute(
        """
        SELECT settlement_date, sp, sec_bmu_id, sec_party_id, gsp_group,
               sev, qm, wmi, wmi_flag, qcv, qsd, qdei
        FROM sbmu_baseline_sp
        WHERE settlement_date BETWEEN ? AND ?
        ORDER BY sec_bmu_id, settlement_date, sp
        """,
        (start_date, end_date),
    ):
        sp = int(sp_raw)
        sev = float(sev_raw or 0.0)
        qm = float(qm_raw or 0.0)
        wmi = float(wmi_raw or 0.0)
        wmi_flag = int(wmi_flag_raw or 0)
        is_act = abs(wmi) > WMI_EPS
        has_sev = abs(sev) > EPS
        rec = _RowRec(
            date=d,
            sp=sp,
            sec_bmu_id=sec_bmu_id,
            sec_party_id=sec_party_id,
            gsp_group=gsp_group or "",
            sev=sev,
            qm=qm,
            wmi=wmi,
            wmi_flag=wmi_flag,
            qcv=float(qcv_raw or 0.0),
            qsd=float(qsd_raw or 0.0),
            qdei=float(qdei_raw or 0.0),
            is_active=is_act,
            has_sev=has_sev,
            implied_dev=qm - sev,
        )
        all_rows.append(rec)
        by_bmu[sec_bmu_id].append(rec)
        by_party[sec_party_id].append(rec)
        if sp > max_sp_per_day[d]:
            max_sp_per_day[d] = sp

    slot_index: dict[tuple[str, int], int] = {}
    slot_cursor = 0
    for d in baseline_dates:
        for sp in range(1, max_sp_per_day[d] + 1):
            slot_index[(d, sp)] = slot_cursor
            slot_cursor += 1

    # Reconstruct P376 BL01 per SBMU, detect sign-inverted SEV SBMUs, and track active SBMU-days
    active_bmu_days: set[tuple[str, str]] = set()
    sign_inverted_bmus: set[str] = set()

    for bmu_id, bmu_rows in by_bmu.items():
        _reconstruct_bl01_for_bmu(bmu_rows)
        sev_n = 0
        s_sev = 0.0
        s_qm = 0.0
        for r in bmu_rows:
            if r.has_sev:
                sev_n += 1
                s_sev += r.sev
                s_qm += r.qm
            if r.is_active and r.implied_dev > EPS:
                active_bmu_days.add((bmu_id, r.date))
        if sev_n >= 10 and (s_sev / sev_n) > 0.05 and (s_qm / sev_n) < -0.05:
            sign_inverted_bmus.add(bmu_id)

    # Market-level counters (excluding sign-inverted test baselines and non-active SBMU-days from rebound)
    total_settled_td = 0.0
    total_unsettled_reb = 0.0
    total_implied_comp = 0.0
    counter_econ_td = 0.0
    mkt_non_active_devs: list[float] = []

    for r in all_rows:
        if r.sec_bmu_id in sign_inverted_bmus:
            continue
        mkt = sp_market.get((r.date, r.sp))
        ssc = mkt["ssc"] if mkt else 0.0
        sbp = mkt["sbp"] if mkt else 0.0
        ssc_thresh = ssc if ssc > 0.0 else 106.0
        if r.is_active:
            if r.implied_dev > 0:
                total_settled_td += r.implied_dev
                if mkt and sbp < ssc_thresh:
                    counter_econ_td += r.implied_dev
        else:
            if r.has_sev:
                mkt_non_active_devs.append(r.implied_dev)
                if r.implied_dev < 0 and (r.sec_bmu_id, r.date) in active_bmu_days:
                    reb = -r.implied_dev
                    total_unsettled_reb += reb
                    total_implied_comp += reb * ssc

    mkt_mae = (
        sum(abs(d) for d in mkt_non_active_devs) / len(mkt_non_active_devs)
        if mkt_non_active_devs
        else 0.0
    )
    mkt_bias = (
        sum(mkt_non_active_devs) / len(mkt_non_active_devs)
        if mkt_non_active_devs
        else 0.0
    )
    mkt_leakage = (
        (total_unsettled_reb / total_settled_td * 100.0)
        if total_settled_td >= 1.0
        else 0.0
    )

    vtps_list: list[dict[str, Any]] = []
    vtp_ida_cache: dict[str, dict[str, Any]] = {}
    sbmu_metrics_cache: dict[str, tuple[dict[str, Any], str, list[str]]] = {}

    for pid, p_rows in by_party.items():
        if not any(r.has_sev or abs(r.qm) > EPS or r.is_active for r in p_rows):
            continue

        metrics, cls, reasons, ida = _aggregate_metrics(
            p_rows,
            sp_market,
            slot_index,
            baseline_days,
            active_bmu_days,
            sign_inverted_bmus,
            compute_ida=True,
        )
        assert ida is not None
        vtp_ida_cache[pid] = ida

        bmu_groups: dict[str, list[_RowRec]] = defaultdict(list)
        for r in p_rows:
            bmu_groups[r.sec_bmu_id].append(r)

        sbmus_summary: list[dict[str, Any]] = []
        for bmu_id, b_rows in bmu_groups.items():
            if not any(r.has_sev or abs(r.qm) > EPS or r.is_active for r in b_rows):
                continue
            # Skip IDA scan for the 399-SBMU summary list (computed on demand when SBMU selected)
            b_met, b_cls, b_reasons, _ = _aggregate_metrics(
                b_rows,
                sp_market,
                slot_index,
                baseline_days,
                active_bmu_days,
                sign_inverted_bmus,
                compute_ida=False,
            )
            sbmu_metrics_cache[bmu_id] = (b_met, b_cls, b_reasons)
            gsp = b_rows[0].gsp_group if b_rows else ""
            sbmus_summary.append(
                {
                    "sec_bmu_id": bmu_id,
                    "gsp_group": gsp,
                    "settled_turndown_mwh": b_met["settled_turndown_mwh"],
                    "unsettled_rebound_mwh": b_met["unsettled_rebound_mwh"],
                    "non_active_mae_mwh": b_met["non_active_mae_mwh"],
                    "bl01_r2": b_met["bl01_r2"],
                    "quantised_2dp_pct": b_met["quantised_2dp_pct"],
                    "sev_coverage_pct": b_met["sev_coverage_pct"],
                    "methodology_class": b_cls,
                }
            )

        sbmus_summary.sort(
            key=lambda x: (x["settled_turndown_mwh"], x["unsettled_rebound_mwh"]),
            reverse=True,
        )

        meta = party_map.get(pid, {})
        vtps_list.append(
            {
                "party_id": pid,
                "company_name": meta.get("company_name") or pid,
                "roles": meta.get("roles") or [],
                **metrics,
                "methodology_class": cls,
                "methodology_reasons": reasons,
                "sbmus": sbmus_summary,
            }
        )

    vtps_list.sort(
        key=lambda x: (
            x["settled_turndown_mwh"],
            x["unsettled_rebound_mwh"],
            x["non_active_mae_mwh"],
        ),
        reverse=True,
    )

    bl01_vtps_count = sum(
        1 for v in vtps_list if v["methodology_class"].startswith("BL01")
    )
    self_nom_vtps_count = sum(
        1 for v in vtps_list if v["methodology_class"].startswith("Self-Nominated")
    )

    headline = (
        f"Across {baseline_days} settlement days ({bl01_vtps_count} BL01, "
        f"{self_nom_vtps_count} self-nominated VTPs), settled wholesale turn-down of "
        f"{total_settled_td:,.1f} MWh is accompanied by {total_unsettled_reb:,.1f} MWh "
        f"of un-notified rebound ({mkt_leakage:.1f}% leakage; "
        f"£{total_implied_comp:,.0f} implied unsettled compensation) and "
        f"{mkt_mae:.3f} MWh/SP non-active baseline MAE."
    )

    market_summary = {
        "total_settled_turndown_mwh": round(total_settled_td, 2),
        "total_unsettled_rebound_mwh": round(total_unsettled_reb, 2),
        "rebound_leakage_pct": round(mkt_leakage, 1),
        "implied_unsettled_comp_gbp": round(total_implied_comp, 2),
        "non_active_mae_mwh": round(mkt_mae, 4),
        "non_active_bias_mwh": round(mkt_bias, 4),
        "counter_economic_turndown_mwh": round(counter_econ_td, 2),
        "bl01_vtps_count": bl01_vtps_count,
        "self_nom_vtps_count": self_nom_vtps_count,
        "headline": headline,
    }

    base = _BaseAuditCache(
        baseline_dates=baseline_dates,
        sp_market=sp_market,
        slot_index=slot_index,
        by_bmu=by_bmu,
        by_party=by_party,
        active_bmu_days=active_bmu_days,
        sign_inverted_bmus=sign_inverted_bmus,
        market_summary=market_summary,
        vtps_list=vtps_list,
        vtp_by_id={v["party_id"]: v for v in vtps_list},
        vtp_ida_cache=vtp_ida_cache,
        sbmu_metrics_cache=sbmu_metrics_cache,
    )
    _BASE_CACHE[cache_key] = base
    while len(_BASE_CACHE) > _CACHE_MAX_ENTRIES:
        _BASE_CACHE.popitem(last=False)
    return base


def compute_baseline_audit(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    sec_party_id: str | None = None,
    sec_bmu_id: str | None = None,
) -> dict[str, Any]:
    """Compute policy-grade BL01 & Self-Nominated Baseline Audit across sbmu_baseline_sp."""
    base = _get_or_build_base(conn, start_date, end_date)
    if base is None:
        return {
            "start_date": start_date,
            "end_date": end_date,
            "baseline_days": 0,
            "selected_party_id": None,
            "selected_bmu_id": None,
            "market_summary": {
                "total_settled_turndown_mwh": 0.0,
                "total_unsettled_rebound_mwh": 0.0,
                "rebound_leakage_pct": 0.0,
                "implied_unsettled_comp_gbp": 0.0,
                "non_active_mae_mwh": 0.0,
                "non_active_bias_mwh": 0.0,
                "counter_economic_turndown_mwh": 0.0,
                "bl01_vtps_count": 0,
                "self_nom_vtps_count": 0,
                "headline": (
                    "No Secondary BMU baseline records ingested in the selected date window. "
                    "Sync baselines from Elexon SAA-I014 to run the BL01 & SEV audit."
                ),
            },
            "vtps": [],
            "selected_detail": None,
        }

    baseline_days = len(base.baseline_dates)
    vtp_by_id = base.vtp_by_id
    resolved_bmu: str | None = None
    resolved_party: str | None = None

    if sec_bmu_id and sec_bmu_id in base.by_bmu:
        bmu_owner = base.by_bmu[sec_bmu_id][0].sec_party_id
        if sec_party_id is None or sec_party_id == bmu_owner:
            resolved_party = bmu_owner
            resolved_bmu = sec_bmu_id
        elif sec_party_id in vtp_by_id:
            resolved_party = sec_party_id
            resolved_bmu = None
    if resolved_party is None:
        if sec_party_id and sec_party_id in vtp_by_id:
            resolved_party = sec_party_id
        elif base.vtps_list:
            resolved_party = base.vtps_list[0]["party_id"]

    selected_detail: dict[str, Any] | None = None
    if resolved_party is not None and resolved_party in vtp_by_id:
        vtp_entry = vtp_by_id[resolved_party]
        if resolved_bmu is not None and resolved_bmu in base.sbmu_metrics_cache:
            sel_rows = base.by_bmu[resolved_bmu]
            b_met, sel_cls, sel_reasons = base.sbmu_metrics_cache[resolved_bmu]
            sel_ida = _compute_ida_pre_ramp(sel_rows, base.slot_index)
            sel_metrics = {
                **b_met,
                "ida_pre_ramp_mw": round(sel_ida["pre_ramp_excess_mw"], 3)
                if sel_ida["transitions_count"] > 0
                else None,
            }
        else:
            resolved_bmu = None
            sel_rows = base.by_party[resolved_party]
            sel_cls = vtp_entry["methodology_class"]
            sel_reasons = vtp_entry["methodology_reasons"]
            sel_ida = base.vtp_ida_cache[resolved_party]
            sel_metrics = {
                k: vtp_entry[k]
                for k in (
                    "sbmu_count",
                    "active_days",
                    "settled_turndown_mwh",
                    "unsettled_rebound_mwh",
                    "rebound_leakage_pct",
                    "implied_unsettled_comp_gbp",
                    "non_active_mae_mwh",
                    "non_active_rmse_mwh",
                    "non_active_mape_pct",
                    "non_active_bias_mwh",
                    "over_forecast_rate_pct",
                    "active_mean_dev_mwh",
                    "inactive_mean_dev_mwh",
                    "active_positive_pct",
                    "inactive_positive_pct",
                    "bl01_r2",
                    "bl01_mae_mwh",
                    "bl01_drift_mwh",
                    "quantised_2dp_pct",
                    "sev_coverage_pct",
                    "ida_pre_ramp_mw",
                )
            }

        selected_detail = {
            "party_id": resolved_party,
            "company_name": vtp_entry["company_name"],
            "sec_bmu_id": resolved_bmu,
            "methodology_class": sel_cls,
            "methodology_reasons": sel_reasons,
            "metrics": sel_metrics,
            "sp_overlay": _build_sp_overlay(
                sel_rows,
                base.baseline_dates,
                base.sp_market,
                base.active_bmu_days,
                base.sign_inverted_bmus,
            ),
            "cherry_pick_hist": _build_cherry_pick_hist(
                sel_rows, base.sign_inverted_bmus
            ),
            "bl01_daily_series": _build_bl01_daily_series(
                sel_rows,
                base.baseline_dates,
                base.active_bmu_days,
                base.sign_inverted_bmus,
            ),
            "ida_pre_ramp": sel_ida,
            "price_regimes": _build_price_regimes(
                sel_rows,
                base.sp_market,
                base.active_bmu_days,
                base.sign_inverted_bmus,
            ),
        }

    return {
        "start_date": start_date,
        "end_date": end_date,
        "baseline_days": baseline_days,
        "selected_party_id": resolved_party,
        "selected_bmu_id": resolved_bmu,
        "market_summary": base.market_summary,
        "vtps": base.vtps_list,
        "selected_detail": selected_detail,
    }


def build_sbmu_audit_csv_rows(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    sec_party_id: str | None = None,
    sec_bmu_id: str | None = None,
) -> list[dict[str, Any]]:
    """Build flat SBMU-level audit rows for CSV export reconciled to compute_baseline_audit."""
    audit = compute_baseline_audit(
        conn,
        start_date,
        end_date,
        sec_party_id=sec_party_id,
        sec_bmu_id=sec_bmu_id,
    )
    rows: list[dict[str, Any]] = []
    for v in audit["vtps"]:
        if sec_party_id and v["party_id"] != sec_party_id:
            continue
        for b in v["sbmus"]:
            if sec_bmu_id and b["sec_bmu_id"] != sec_bmu_id:
                continue
            rows.append(
                {
                    "start_date": audit["start_date"],
                    "end_date": audit["end_date"],
                    "party_id": v["party_id"],
                    "company_name": v["company_name"],
                    "sec_bmu_id": b["sec_bmu_id"],
                    "gsp_group": b["gsp_group"],
                    "methodology_class": b["methodology_class"],
                    "settled_turndown_mwh": b["settled_turndown_mwh"],
                    "unsettled_rebound_mwh": b["unsettled_rebound_mwh"],
                    "non_active_mae_mwh": b["non_active_mae_mwh"],
                    "bl01_r2": "" if b["bl01_r2"] is None else b["bl01_r2"],
                    "quantised_2dp_pct": b["quantised_2dp_pct"],
                    "sev_coverage_pct": b["sev_coverage_pct"],
                    "vtp_rebound_leakage_pct": v["rebound_leakage_pct"],
                    "vtp_implied_unsettled_comp_gbp": v["implied_unsettled_comp_gbp"],
                    "vtp_non_active_bias_mwh": v["non_active_bias_mwh"],
                    "vtp_ida_pre_ramp_mw": ""
                    if v["ida_pre_ramp_mw"] is None
                    else v["ida_pre_ramp_mw"],
                }
            )
    return rows


def render_policy_briefing_md(audit_data: dict[str, Any]) -> str:
    """Render an objective Ofgem / Elexon Issue 127 & P510 Markdown policy evidence briefing."""
    ms = audit_data.get("market_summary", {})
    vtps = audit_data.get("vtps", [])
    detail = audit_data.get("selected_detail")
    start_date = audit_data.get("start_date", "")
    end_date = audit_data.get("end_date", "")
    days = audit_data.get("baseline_days", 0)

    def _fmt_opt(val: float | None, fmt: str = ".2f", suffix: str = "") -> str:
        if val is None:
            return "n/a"
        return f"{val:{fmt}}{suffix}"

    lines: list[str] = [
        "# Secondary BMU Baseline & BL01 (P376) Structural Audit",
        "",
        "**Policy Context:** Ofgem / Elexon BSC Issue 127, P376 (BL01 Baselining), P415 (VTP Wholesale Access), and P510 Review  ",
        f"**Settlement Window:** `{start_date}` to `{end_date}` ({days} settlement days with Secondary BMU baseline records)  ",
        "**Data Source:** Elexon SAA-I014 `bm-unit-level` (`sevij`, `qmij`, `wmi2j`, `qdei2j`) joined with `settlement-period-level` (`sbp`, `ssc`, `mpj`).  ",
        "**Sign Convention:** In SAA-I014, demand is negative (`qm`, `sev < 0`). Implied deviation `qm - sev > 0` denotes demand turn-down below baseline; `qm - sev < 0` denotes demand rebound / load surge above baseline.",
        "",
        "---",
        "",
        "## 1. Executive Summary",
        "",
        f"> {ms.get('headline', 'No baseline data available.')}",
        "",
        "This evidence brief evaluates how accurately Secondary BMU Settlement Expected Volumes (`SEV`) forecast metered demand (`QM`) during non-active periods, and quantifies structural incentive distortions arising from the interaction between P376 BL01 lookback rules, self-nominated baselines, and P415 wholesale activation settlement.",
        "",
        "### Market-Wide Baseline Integrity Ledger",
        "",
        "| Metric | Value | Structural Interpretation |",
        "| --- | ---: | --- |",
        f"| Settled Wholesale Turn-Down (`wmi > 0`, `qm > sev`) | {ms.get('total_settled_turndown_mwh', 0.0):,.2f} MWh | Volume credited as reduced demand in active wholesale SPs |",
        f"| Un-Notified Rebound (`wmi = 0`, `qm < sev`, active days) | {ms.get('total_unsettled_rebound_mwh', 0.0):,.2f} MWh | Excess load above baseline in non-active SPs excluded from compensation |",
        f"| Rebound Leakage Ratio | {ms.get('rebound_leakage_pct', 0.0):.1f}% | Un-notified rebound as % of settled turn-down |",
        f"| Implied Unsettled Compensation (`rebound × SSC`) | £{ms.get('implied_unsettled_comp_gbp', 0.0):,.2f} | Counterfactual supplier compensation offset if rebound were settled |",
        f"| Non-Active Baseline Forecast MAE (`wmi = 0`) | {ms.get('non_active_mae_mwh', 0.0):.4f} MWh/SP | Mean absolute forecast error when no wholesale action is notified |",
        f"| Non-Active Baseline Forecast Bias (`mean(qm - sev)`) | {ms.get('non_active_bias_mwh', 0.0):+.4f} MWh/SP | Positive = baseline over-forecasts demand; Negative = un-notified load surge |",
        f"| Counter-Economic Turn-Down (`SBP < SSC`) | {ms.get('counter_economic_turndown_mwh', 0.0):,.2f} MWh | Settled turn-down in periods where System Buy Price is below SSC |",
        f"| Methodology Split (BL01 vs Self-Nominated VTPs) | {ms.get('bl01_vtps_count', 0)} BL01 / {ms.get('self_nom_vtps_count', 0)} Self-Nom | Count of active VTPs by inferred settlement baselining regime |",
        "",
        "---",
        "",
        "## 2. VTP Methodology Classification & Reconciled Audit Table",
        "",
    ]

    if vtps:
        lines.extend(
            [
                "| VTP (Party ID) | Methodology Class | SBMUs | Settled Turn-Down (MWh) | Unsettled Rebound (MWh) | Leakage (%) | Implied Unsettled Comp (£) | Non-Active MAE (MWh/SP) | Non-Active Bias (MWh/SP) | BL01 R² | 2dp Quantised (%) | SEV Coverage (%) | IDA Pre-Ramp (MW) |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for v in vtps:
            lines.append(
                f"| {v['company_name']} (`{v['party_id']}`) | {v['methodology_class']} | {v['sbmu_count']} | "
                f"{v['settled_turndown_mwh']:,.2f} | {v['unsettled_rebound_mwh']:,.2f} | {v['rebound_leakage_pct']:.1f}% | "
                f"£{v['implied_unsettled_comp_gbp']:,.0f} | {v['non_active_mae_mwh']:.4f} | {v['non_active_bias_mwh']:+.4f} | "
                f"{_fmt_opt(v.get('bl01_r2'), '.2f')} | {v['quantised_2dp_pct']:.1f}% | {v['sev_coverage_pct']:.1f}% | "
                f"{_fmt_opt(v.get('ida_pre_ramp_mw'), '+.3f')} |"
            )
    else:
        lines.append("_No active VTP baseline records in the selected window._")

    if detail:
        m = detail["metrics"]
        scope_label = (
            f"{detail['company_name']} (`{detail['party_id']}`) — SBMU `{detail['sec_bmu_id']}`"
            if detail.get("sec_bmu_id")
            else f"{detail['company_name']} (`{detail['party_id']}`) — Portfolio Aggregate ({m.get('sbmu_count', 0)} SBMUs)"
        )
        lines.extend(
            [
                "",
                "---",
                "",
                f"## 3. Focused Diagnostic: {scope_label}",
                "",
                f"**Inferred Methodology:** `{detail['methodology_class']}`",
                "",
                "**Empirical Evidence:**",
            ]
        )
        for reason in detail.get("methodology_reasons", []):
            lines.append(f"- {reason}")

        ida = detail.get("ida_pre_ramp", {})
        lines.extend(
            [
                "",
                "### Asymmetric Activation Selection & Pre-Event Ramp Summary",
                "",
                f"- **Active SPs (`wmi > 0`):** Mean deviation `{m['active_mean_dev_mwh']:+.4f} MWh/SP`, positive (turn-down) in **{m['active_positive_pct']:.1f}%** of periods.",
                f"- **Non-Active SPs (`wmi = 0`, `SEV != 0`):** Mean deviation `{m['inactive_mean_dev_mwh']:+.4f} MWh/SP`, positive in **{m['inactive_positive_pct']:.1f}%** of periods (MAE `{m['non_active_mae_mwh']:.4f} MWh/SP`, RMSE `{m['non_active_rmse_mwh']:.4f} MWh/SP`, WAPE `{_fmt_opt(m.get('non_active_mape_pct'), '.1f', '%')}`).",
                f"- **BL01 Reconstruction:** `R² = {_fmt_opt(m.get('bl01_r2'), '.3f')}`, MAE `{_fmt_opt(m.get('bl01_mae_mwh'), '.4f', ' MWh/SP')}`, drift vs rolling 10-working-day actuals `{_fmt_opt(m.get('bl01_drift_mwh'), '+.4f', ' MWh/SP')}`.",
                f"- **IDA Pre-Event Window (`-6..-1` SPs before activation start):** {ida.get('transitions_count', 0)} observed transitions with mean pre-event excess load of `{ida.get('pre_ramp_excess_mw', 0.0):+.3f} MW` relative to baseline.",
                "",
                "### Dispatch Across System Buy Price Regimes",
                "",
                "| SBP Regime | SPs | Avg SBP (£/MWh) | Activation Rate (%) | Settled Turn-Down (MWh) | Settled Turn-Up (MWh) | Unsettled Rebound (MWh) |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for reg in detail.get("price_regimes", []):
            lines.append(
                f"| {reg['regime']} | {reg['sps_count']} | £{reg['avg_sbp']:.2f} | "
                f"{reg['activation_rate_pct']:.1f}% | {reg['settled_turndown_mwh']:,.2f} | "
                f"{reg['settled_turnup_mwh']:,.2f} | {reg['unsettled_rebound_mwh']:,.2f} |"
            )

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Structural Policy Implications (P376 / Issue 127 / P510)",
            "",
            "1. **Asymmetric Settlement Option & Un-Notified Rebound (Issue 127 / P415):** Because wholesale settlement only captures deviations in SPs where `wmi > 0`, energy-shifting loads (such as domestic EV chargers) can settle daytime turn-down while leaving overnight catch-up demand (`qm < sev`, `wmi = 0`) outside Supplier Compensation. Introducing symmetric multi-period energy conservation checks or mandatory rebound accounting closes this structural transfer.",
            "2. **P376 BL01 Event-Day Exclusion & Lookback Freeze:** Excluding activated days from the 10-working-day / middle-2-of-4-weekend historic average preserves a pre-event baseline even when portfolio consumption patterns change permanently (e.g., seasonal tariff switching or continuous daily activation). Capping lookback staleness or adopting control-group / weather-normalised baselines mitigates baseline drift.",
            "3. **In-Day Adjustment (IDA) Pre-Event Sensitivity:** Where BL01 applies an additive or multiplicative In-Day Adjustment using the 2–3 hours prior to activation, elevated pre-event load (`actual > baseline` at offsets `-6..-1`) mechanically lifts the event-period baseline. Monitoring pre-ramp excess load provides an objective diagnostic for IDA distortion.",
            "4. **Self-Nominated SEV Auditability & Counter-Economic Dispatch (P510):** Sparse event-only or coarsely quantised self-nominated baselines prevent independent verification of non-active forecast accuracy (`SEV` absent when `wmi = 0`). Meanwhile, fixed SSC compensation above prevailing System Buy Price creates an economic incentive to settle turn-down during surplus/low-price periods (`SBP < SSC`).",
            "",
        ]
    )

    return "\n".join(lines)
