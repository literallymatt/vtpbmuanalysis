"""Unit and FastAPI integration tests for the BL01 (P376) & Self-Nominated Baseline Audit Engine."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import math
from pathlib import Path

from fastapi.testclient import TestClient

from backend.analytics import get_status
from backend.baseline_audit import (
    PRICE_REGIME_ORDER,
    _middle_2_of_4,
    compute_baseline_audit,
    render_policy_briefing_md,
)
from backend.db import get_conn, init_db
from backend.main import SyncDatesRequest, app


def _seed_baseline_audit_db(db_path: Path) -> None:
    """Seed a 21-day synthetic dataset exercising all baseline regimes and policy distortions.

    Parties seeded:
      1. AXLEENER (BL01 — Frozen Lookback + overnight rebound + IDA pre-ramp + cherry-picking)
         - Days 1-7 (Oct 1-7): Clean baseline establishment (no activations).
           Diurnal 3dp+ metered profile varying cleanly by SP and weekday/weekend.
         - Days 8-21 (Oct 8-21): Heavy daily activations SP 15..42 (wmi=1.0),
           settled SEV stays frozen at clean days' BL01 average (event-day exclusion!),
           actual demand drops during SP 15..42 (settled turn-down),
           pre-event load ramps UP during SP 9..14 (offsets -6..-1 -> IDA pre-ramp!),
           and overnight SP 1..8 experiences un-notified rebound (qm < sev while wmi=0)!
      2. REFLEXI (Clean BL01 Historic Average — no freeze, mild occasional activations)
         - Continuous 3dp+ SEV closely tracking rolling 10-working-day / middle-2-of-4 weekend qm.
         - Occasional evening peak activations on 4 high-price days only.
      3. CAPTURE (Self-Nominated — Quantised 2dp SEV)
         - Continuous SEV on 100% of SPs, all exact 2dp increments (-4.50 / -2.25 MWh),
           diverging from actual rolling load.
      4. POWONTEC (Self-Nominated — Sparse / Event-Only SEV)
         - Only submits non-zero SEV during 4 active evening SPs on 6 days; SEV = 0.0 on all
           inactive load SPs (low sev_coverage_pct, zero false rebound from missing SEV).
    """
    init_db(db_path)
    start = dt.date(2026, 10, 1)
    dates = [(start + dt.timedelta(days=i)).isoformat() for i in range(21)]
    ssc = 106.0

    # Vary SBP across all 5 price regimes across the 21 days & SPs
    with get_conn(db_path) as conn:
        parties = [
            ("AXLEENER", "Axle Energy", json.dumps(["BP", "VP", "AV", "VT"]), 1, 1, 1, 0),
            ("REFLEXI", "Reflexi Energy Ltd", json.dumps(["BP", "VP", "VT"]), 1, 1, 0, 0),
            ("CAPTURE", "Capture Flexibility Ltd", json.dumps(["BP", "VP", "VT"]), 1, 1, 0, 0),
            ("POWONTEC", "Joulen (Power On Technologies)", json.dumps(["BP", "VP", "VT"]), 1, 1, 0, 0),
        ]
        for pid, name, roles, vtp, vlp, av, sup in parties:
            conn.execute(
                """
                INSERT INTO parties (
                    party_id, company_name, roles_json, is_vtp, is_vlp, is_amvlp, is_supplier, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '2026-10-22T00:00:00Z')
                """,
                (pid, name, roles, vtp, vlp, av, sup),
            )

        for day_idx, d in enumerate(dates):
            conn.execute(
                """
                INSERT INTO ingested_days (
                    settlement_date, run_type, has_bmu_sp, has_party_level,
                    has_sp_level, has_sbmu_baselines, ingested_at
                ) VALUES (?, 'SF', 1, 1, 1, 1, '2026-10-22T00:00:00Z')
                """,
                (d,),
            )
            for sp in range(1, 49):
                # Cover all 5 SBP regimes cleanly:
                # SP 1-6: negative or very cheap (-15 or 30), SP 7-20: 75 (below SSC),
                # SP 21-36: 130 (above SSC), SP 37-44: 210 (>180), SP 45-48: 40
                if sp <= 6:
                    sbp = -15.0 if day_idx % 2 == 0 else 30.0
                elif sp <= 20:
                    sbp = 75.0
                elif sp <= 36:
                    sbp = 130.0
                elif sp <= 44:
                    sbp = 210.0
                else:
                    sbp = 40.0
                conn.execute(
                    """
                    INSERT INTO sp_market_data (
                        settlement_date, sp, run_type, ssc, sbp, ssp, mpj
                    ) VALUES (?, ?, 'SF', ?, ?, ?, ?)
                    """,
                    (d, sp, ssc, sbp, sbp, sbp),
                )

        def _base_curve(sp: int, is_we: bool, scale: float) -> float:
            # Smooth realistic negative demand (MWh/SP) with 3dp+ non-quantised precision
            phase = math.sin((sp - 10) / 48.0 * 2.0 * math.pi)
            wk_mult = 0.88 if is_we else 1.0
            val = -(scale * wk_mult * (1.0 + 0.35 * phase + 0.0137 * (sp % 7)))
            return round(val, 4)

        baseline_rows: list[tuple] = []

        # --- 1. AXLEENER (2 SBMUs: V__AAXLE001, V__BAXLE001) ---
        for bmu_id, gsp, scale in [("V__AAXLE001", "A", 4.123), ("V__BAXLE001", "B", 2.877)]:
            for day_idx, d in enumerate(dates):
                is_we = dt.date.fromisoformat(d).weekday() >= 5
                is_event_phase = day_idx >= 7  # Days 8..21
                for sp in range(1, 49):
                    clean_base = _base_curve(sp, is_we, scale)
                    sev = clean_base  # Frozen at pre-event BL01 level!
                    if not is_event_phase:
                        # Clean days: tiny symmetric noise around baseline, no activations
                        noise = 0.015 if (sp + day_idx) % 2 == 0 else -0.015
                        qm = round(clean_base + noise, 4)
                        wmi = 0.0
                    else:
                        if 15 <= sp <= 42:
                            # Active turn-down: actual demand much smaller (less negative) than baseline
                            qm = round(clean_base * 0.55, 4)
                            wmi = 1.0
                        elif 9 <= sp <= 14:
                            # Pre-event IDA ramp window (offsets -6..-1 before SP 15):
                            # actual demand is HIGHER (more negative) than baseline by 0.6 MWh (1.2 MW)!
                            qm = round(clean_base - 0.60, 4)
                            wmi = 0.0
                        elif 1 <= sp <= 8:
                            # Overnight un-notified EV rebound (wmi=0, qm < sev)
                            qm = round(clean_base - 1.25, 4)
                            wmi = 0.0
                        else:
                            qm = round(clean_base - 0.10, 4)
                            wmi = 0.0
                    qcv = max(0.0, qm - sev) if wmi > 0 else 0.0
                    baseline_rows.append(
                        (d, sp, bmu_id, "SF", "AXLEENER", gsp, "C", 0.0, qm, sev, qm, qcv, qcv, qcv, wmi, int(wmi > 0))
                    )

        # --- 2. REFLEXI (Clean BL01 Historic Average, 1 SBMU: V__AREFL001) ---
        # Build chronological history so SEV matches exact P376 BL01 formula
        ref_wd_hist: list[dict[int, float]] = []
        ref_we_hist: list[dict[int, float]] = []
        ref_event_days = {14, 15, 18, 19}  # Only 4 event days out of 21
        for day_idx, d in enumerate(dates):
            is_we = dt.date.fromisoformat(d).weekday() >= 5
            is_ev = day_idx in ref_event_days
            qm_day: dict[int, float] = {}
            for sp in range(1, 49):
                true_dem = _base_curve(sp, is_we, 3.219)
                if not is_we and len(ref_wd_hist) >= 2:
                    vals = [h[sp] for h in ref_wd_hist[-10:]]
                    sev = round(sum(vals) / len(vals), 4)
                elif is_we and len(ref_we_hist) >= 1:
                    vals = [h[sp] for h in ref_we_hist[-4:]]
                    sev = round(_middle_2_of_4(vals), 4)
                else:
                    sev = true_dem

                if is_ev and 37 <= sp <= 40:
                    # Targeted evening peak turn-down (SBP = 210 > SSC)
                    qm = round(sev + 1.10, 4)
                    wmi = 1.0
                elif is_ev and 41 <= sp <= 42:
                    # Settled turn-up in active SP to test settled_turnup_mwh
                    qm = round(sev - 0.30, 4)
                    wmi = 1.0
                else:
                    drift = 0.04 if (day_idx + sp) % 2 == 0 else -0.04
                    qm = round(true_dem + drift, 4)
                    wmi = 0.0
                qm_day[sp] = qm
                qcv = (qm - sev) if wmi > 0 else 0.0
                baseline_rows.append(
                    (d, sp, "V__AREFL001", "SF", "REFLEXI", "A", "C", 0.0, qm, sev, qm, qcv, qcv, qcv, wmi, int(wmi > 0))
                )
            if not is_ev:
                if is_we:
                    ref_we_hist.append(qm_day)
                else:
                    ref_wd_hist.append(qm_day)

        # --- 3. CAPTURE (Self-Nominated Quantised 2dp SEV, 1 SBMU: V__ACAPT001) ---
        for day_idx, d in enumerate(dates):
            for sp in range(1, 49):
                # Flat/step exact 2dp nominated SEV completely decoupled from rolling actual load
                sev = -5.00 if 15 <= sp <= 40 else -2.50
                # Actual load varies by day and SP (non-matching)
                qm = round(-3.123 - 0.45 * math.sin((sp + day_idx * 3) / 6.0), 4)
                wmi = 1.0 if (day_idx % 2 == 0 and 35 <= sp <= 40) else 0.0
                if wmi > 0:
                    qm = -3.40  # Turn-down of +1.60 MWh vs -5.00 SEV
                qcv = (qm - sev) if wmi > 0 else 0.0
                baseline_rows.append(
                    (d, sp, "V__ACAPT001", "SF", "CAPTURE", "A", "C", 0.0, qm, sev, qm, qcv, qcv, qcv, wmi, int(wmi > 0))
                )

        # --- 4. POWONTEC (Self-Nominated Sparse / Event-Only SEV, 1 SBMU: V__APOWO001) ---
        for day_idx, d in enumerate(dates):
            for sp in range(1, 49):
                if day_idx >= 15 and 37 <= sp <= 40:
                    sev = -3.50
                    qm = -1.50
                    wmi = 1.0
                else:
                    # Normal metered load present, but NO SEV submitted!
                    sev = 0.0
                    qm = -2.85
                    wmi = 0.0
                qcv = (qm - sev) if wmi > 0 else 0.0
                baseline_rows.append(
                    (d, sp, "V__APOWO001", "SF", "POWONTEC", "A", "C", 0.0, qm, sev, qm, qcv, qcv, qcv, wmi, int(wmi > 0))
                )

        conn.executemany(
            """
            INSERT INTO sbmu_baseline_sp (
                settlement_date, sp, sec_bmu_id, run_type, sec_party_id, gsp_group,
                pc_flag, fpn, qme, sev, qm, qdei, qsd, qcv, wmi, wmi_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            baseline_rows,
        )


def test_middle_2_of_4_weekend_rule() -> None:
    assert _middle_2_of_4([-10.0, -2.0, -5.0, -7.0]) == -6.0
    assert _middle_2_of_4([-10.0, -2.0, -5.0]) == -5.0
    assert _middle_2_of_4([-8.0, -4.0]) == -6.0
    assert _middle_2_of_4([-3.5]) == -3.5


def test_empty_database_graceful_response(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    init_db(db_path)
    with get_conn(db_path) as conn:
        res = compute_baseline_audit(conn, "2026-10-01", "2026-10-21")
        st = get_status(conn)

    assert res["baseline_days"] == 0
    assert res["vtps"] == []
    assert res["selected_detail"] is None
    assert res["market_summary"]["total_settled_turndown_mwh"] == 0.0
    assert "No Secondary BMU baseline records" in res["market_summary"]["headline"]
    assert st["baseline_days"] == 0
    assert st["sbmu_baseline_rows"] == 0

    md = render_policy_briefing_md(res)
    assert "# Secondary BMU Baseline & BL01 (P376) Structural Audit" in md


def test_bl01_reconstruction_and_methodology_classification(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.db"
    _seed_baseline_audit_db(db_path)

    with get_conn(db_path) as conn:
        res = compute_baseline_audit(conn, "2026-10-01", "2026-10-21")

    assert res["baseline_days"] == 21
    by_id = {v["party_id"]: v for v in res["vtps"]}
    assert set(by_id.keys()) == {"AXLEENER", "REFLEXI", "CAPTURE", "POWONTEC"}

    # 1. AXLEENER: Frozen BL01 Lookback
    axle = by_id["AXLEENER"]
    assert axle["methodology_class"] == "BL01 (P376 — Frozen Lookback)"
    assert axle["bl01_r2"] is not None and axle["bl01_r2"] >= 0.90
    assert axle["bl01_drift_mwh"] is not None and axle["bl01_drift_mwh"] > 0.3
    assert axle["quantised_2dp_pct"] < 30.0
    assert axle["sev_coverage_pct"] == 100.0
    assert axle["sbmu_count"] == 2

    # 2. REFLEXI: Clean BL01 Historic Average
    reflexi = by_id["REFLEXI"]
    assert reflexi["methodology_class"] == "BL01 (P376 Historic Average)"
    assert reflexi["bl01_r2"] is not None and reflexi["bl01_r2"] >= 0.95
    assert reflexi["bl01_mae_mwh"] is not None and reflexi["bl01_mae_mwh"] < 0.1
    assert abs(reflexi["bl01_drift_mwh"] or 0.0) < 0.15

    # 3. CAPTURE: Quantised 2dp Self-Nominated SEV
    capture = by_id["CAPTURE"]
    assert capture["methodology_class"] == "Self-Nominated (Quantised SEV)"
    assert capture["quantised_2dp_pct"] == 100.0
    assert capture["sev_coverage_pct"] == 100.0

    # 4. POWONTEC: Sparse / Event-Only Self-Nominated SEV
    powo = by_id["POWONTEC"]
    assert powo["methodology_class"] == "Self-Nominated (Sparse / Event-Only)"
    assert powo["sev_coverage_pct"] < 10.0
    # Crucial: missing SEV (sev == 0) on inactive SPs must NOT produce fake rebound!
    assert powo["unsettled_rebound_mwh"] == 0.0
    assert powo["non_active_mae_mwh"] == 0.0

    # Market summary counts
    ms = res["market_summary"]
    assert ms["bl01_vtps_count"] == 2
    assert ms["self_nom_vtps_count"] == 2
    assert ms["total_settled_turndown_mwh"] > 0
    assert ms["total_unsettled_rebound_mwh"] > 0
    assert ms["implied_unsettled_comp_gbp"] > 0
    assert ms["counter_economic_turndown_mwh"] > 0


def test_cherry_picking_rebound_leakage_and_ida_pre_ramp(tmp_path: Path) -> None:
    db_path = tmp_path / "audit_detail.db"
    _seed_baseline_audit_db(db_path)

    with get_conn(db_path) as conn:
        res = compute_baseline_audit(
            conn, "2026-10-01", "2026-10-21", sec_party_id="AXLEENER"
        )

    assert res["selected_party_id"] == "AXLEENER"
    assert res["selected_bmu_id"] is None
    detail = res["selected_detail"]
    assert detail is not None

    m = detail["metrics"]
    # Active SPs are 100% positive turn-down; inactive SPs show negative bias (rebound + pre-ramp)
    assert m["active_positive_pct"] == 100.0
    assert m["active_mean_dev_mwh"] > 1.0
    assert m["inactive_mean_dev_mwh"] < -0.2
    assert m["inactive_positive_pct"] < 50.0
    assert m["rebound_leakage_pct"] > 20.0
    # Implied unsettled comp = rebound * 106.0 exactly
    assert abs(m["implied_unsettled_comp_gbp"] - m["unsettled_rebound_mwh"] * 106.0) < 1.5

    # SP overlay has 48 periods with positive MW magnitudes
    overlay = detail["sp_overlay"]
    assert len(overlay) == 48
    assert all(pt["baseline_demand_mw"] > 0 and pt["actual_demand_mw"] > 0 for pt in overlay)
    # Overnight SP 1..8 has unsettled rebound; daytime SP 15..42 has settled turn-down
    assert overlay[2]["unsettled_rebound_mw"] > 0
    assert overlay[20]["settled_turndown_mw"] > 0

    # Cherry-pick histogram separates active (right / positive) from inactive (left / negative)
    hist = detail["cherry_pick_hist"]
    assert len(hist) == 16
    act_pos_mass = sum(b["active_pct"] for b in hist if b["bin_center"] > 0)
    inact_neg_mass = sum(b["inactive_pct"] for b in hist if b["bin_center"] < 0)
    assert act_pos_mass >= 99.0
    assert inact_neg_mass >= 55.0

    # BL01 daily series shows bl01_excl staying frozen at settled_sev while bl01_raw drops!
    daily = detail["bl01_daily_series"]
    assert len(daily) == 21
    last_day = daily[-1]
    assert last_day["bl01_excl_mwh"] is not None
    assert last_day["bl01_raw_mwh"] is not None
    assert abs(last_day["settled_sev_mwh"] - last_day["bl01_excl_mwh"]) < 1.0
    assert last_day["bl01_excl_mwh"] > last_day["bl01_raw_mwh"] + 20.0

    # IDA Pre-Event Ramp: 14 event days × 2 SBMUs grouped into 14 portfolio transitions
    # Each SBMU ramped +0.60 MWh = +1.20 MW -> portfolio excess = +2.40 MW across offsets -6..-1
    ida = detail["ida_pre_ramp"]
    assert ida["transitions_count"] == 14
    assert len(ida["pre_event_window_sp_offsets"]) == 6
    assert abs(ida["pre_ramp_excess_mw"] - 2.40) < 0.05
    assert [o["offset_sp"] for o in ida["pre_event_window_sp_offsets"]] == [-6, -5, -4, -3, -2, -1]
    for o in ida["pre_event_window_sp_offsets"]:
        assert abs(o["excess_load_mw"] - 2.40) < 0.05

    # Price regimes: exact 5 buckets
    regimes = detail["price_regimes"]
    assert tuple(r["regime"] for r in regimes) == PRICE_REGIME_ORDER
    reg_by_name = {r["regime"]: r for r in regimes}
    assert reg_by_name["£50–£106 (Below SSC)"]["settled_turndown_mwh"] > 0
    assert reg_by_name["< £0"]["unsettled_rebound_mwh"] > 0

    # Check Reflexi settled_turnup_mwh in > £180/MWh bucket
    with get_conn(db_path) as conn:
        ref_res = compute_baseline_audit(
            conn, "2026-10-01", "2026-10-21", sec_party_id="REFLEXI"
        )
    ref_reg = {r["regime"]: r for r in ref_res["selected_detail"]["price_regimes"]}
    assert ref_reg["> £180/MWh"]["settled_turndown_mwh"] > 0
    assert ref_reg["> £180/MWh"]["settled_turnup_mwh"] > 0


def test_sbmu_drilldown_and_api_exports(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "api_audit.db"
    _seed_baseline_audit_db(db_path)
    monkeypatch.setenv("VTP_DB_PATH", str(db_path))

    client = TestClient(app)

    # 1. /api/status baseline fields
    st = client.get("/api/status")
    assert st.status_code == 200
    st_json = st.json()
    assert st_json["baseline_days"] == 21
    assert st_json["baseline_min_date"] == "2026-10-01"
    assert st_json["baseline_max_date"] == "2026-10-21"
    assert st_json["sbmu_baseline_rows"] == 21 * 48 * 5

    # 2. /api/baseline-audit default + SBMU drill-down
    r_def = client.get("/api/baseline-audit")
    assert r_def.status_code == 200
    d_def = r_def.json()
    assert d_def["baseline_days"] == 21
    assert d_def["selected_party_id"] == "AXLEENER"
    assert d_def["selected_bmu_id"] is None

    r_bmu = client.get(
        "/api/baseline-audit?sec_party_id=AXLEENER&sec_bmu_id=V__BAXLE001"
    )
    assert r_bmu.status_code == 200
    d_bmu = r_bmu.json()
    assert d_bmu["selected_party_id"] == "AXLEENER"
    assert d_bmu["selected_bmu_id"] == "V__BAXLE001"
    assert d_bmu["selected_detail"]["sec_bmu_id"] == "V__BAXLE001"
    assert d_bmu["selected_detail"]["metrics"]["sbmu_count"] == 1
    # Single SBMU IDA pre-ramp should be half of the 2-SBMU portfolio (+1.20 MW)
    assert abs(d_bmu["selected_detail"]["ida_pre_ramp"]["pre_ramp_excess_mw"] - 1.20) < 0.05

    # Stale sec_bmu_id belonging to AXLEENER resets cleanly when switching to REFLEXI
    r_switch = client.get(
        "/api/baseline-audit?sec_party_id=REFLEXI&sec_bmu_id=V__BAXLE001"
    )
    assert r_switch.status_code == 200
    assert r_switch.json()["selected_party_id"] == "REFLEXI"
    assert r_switch.json()["selected_bmu_id"] is None

    # 3. /api/baseline-audit/export.csv
    r_csv = client.get("/api/baseline-audit/export.csv")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers["content-type"]
    rows = list(csv.DictReader(io.StringIO(r_csv.text)))
    assert len(rows) == 5
    bmu_ids = {row["sec_bmu_id"] for row in rows}
    assert bmu_ids == {
        "V__AAXLE001",
        "V__BAXLE001",
        "V__AREFL001",
        "V__ACAPT001",
        "V__APOWO001",
    }

    # 4. /api/baseline-audit/briefing.md
    r_md = client.get("/api/baseline-audit/briefing.md?sec_party_id=AXLEENER")
    assert r_md.status_code == 200
    assert "text/markdown" in r_md.headers["content-type"]
    assert "attachment;" in r_md.headers["content-disposition"]
    md = r_md.text
    assert "Issue 127" in md
    assert "P510" in md
    assert "BL01 (P376 — Frozen Lookback)" in md
    assert "Axle Energy" in md
    assert "Self-Nominated (Quantised SEV)" in md
    assert "Self-Nominated (Sparse / Event-Only)" in md

    # 5. SyncDatesRequest supports include_baselines
    req = SyncDatesRequest(
        start_date="2026-10-01",
        end_date="2026-10-05",
        include_bmu_sp=True,
        include_baselines=True,
    )
    assert req.include_baselines is True


def test_pre_window_frozen_bl01_sign_inverted_and_bm_only_exclusion(tmp_path: Path) -> None:
    """Verify non-active BL01 frozen detection, sign-inverted SEV flagging, and BM-only exclusion."""
    db_path = tmp_path / "frozen_bm.db"
    init_db(db_path)
    start = dt.date(2026, 10, 1)
    dates = [(start + dt.timedelta(days=i)).isoformat() for i in range(14)]

    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO parties (party_id, company_name, roles_json, is_vtp, updated_at)
            VALUES ('FROZEN1', 'Frozen EV VTP', '["VT"]', 1, '2026-10-15T00:00:00Z'),
                   ('CUSTOM1', 'Custom Baseline VTP', '["VT"]', 1, '2026-10-15T00:00:00Z'),
                   ('SIGNINV', 'Sign Inverted Test VTP', '["VT"]', 1, '2026-10-15T00:00:00Z'),
                   ('BMVLP1', 'BM Only VLP', '["VP"]', 0, '2026-10-15T00:00:00Z')
            """
        )
        rows: list[tuple] = []
        for idx, d in enumerate(dates):
            conn.execute(
                """
                INSERT INTO ingested_days (
                    settlement_date, run_type, has_bmu_sp, has_party_level,
                    has_sp_level, has_sbmu_baselines, ingested_at
                ) VALUES (?, 'SF', 1, 1, 1, 1, '2026-10-15T00:00:00Z')
                """,
                (d,),
            )
            for sp in range(1, 49):
                conn.execute(
                    """
                    INSERT INTO sp_market_data (settlement_date, sp, run_type, ssc, sbp, ssp, mpj)
                    VALUES (?, ?, 'SF', 106.0, 120.0, 120.0, 120.0)
                    """,
                    (d, sp),
                )
                # FROZEN1: active EVERY day (14/14). Non-active SPs (1..14, 41..48) follow a smooth
                # diurnal BL01 curve matching settled SEV (high inact BL01 R^2), while active SPs
                # (15..40) have frozen high SEV vs depressed actual QM!
                inact_curve = round(-(3.1234 + 2.5 * math.sin(sp / 14.0 * math.pi)), 4)
                if 15 <= sp <= 40:
                    sev = round(-(7.6543 + 1.2 * math.sin((sp - 15) / 25.0 * math.pi)), 4)
                    qm = round(-1.5432, 4)
                    wmi = 1.0
                else:
                    sev = inact_curve
                    qm = round(inact_curve - 0.35, 4)
                    wmi = 0.0
                rows.append((d, sp, "V__AFROZ001", "SF", "FROZEN1", "A", "C", 0.0, qm, sev, qm, 0.0, 0.0, 0.0, wmi, int(wmi > 0)))

                # CUSTOM1: continuous 4dp SEV whose non-active SPs do NOT match BL01 at all
                c_sev = round(-(2.137 + 0.8 * math.cos(sp / 5.0)), 4)
                c_qm = round(-(6.421 + 2.2 * math.sin((sp + idx * 7) / 4.0)), 4)
                c_wmi = 1.0 if 35 <= sp <= 40 else 0.0
                if c_wmi > 0:
                    c_sev = round(-12.345, 4)
                    c_qm = round(-2.345, 4)
                rows.append((d, sp, "V__ACUST001", "SF", "CUSTOM1", "A", "C", 0.0, c_qm, c_sev, c_qm, 0.0, 0.0, 0.0, c_wmi, int(c_wmi > 0)))

                # SIGNINV: positive SEV (+10.5) against negative QM (-10.9), 0 active SPs
                rows.append((d, sp, "V__ASIGN001", "SF", "SIGNINV", "A", "C", 0.0, -10.94, 10.58, -10.94, 0.0, 0.0, 0.0, 0.0, 0))

                # BMVLP1: never activates in wholesale (wmi == 0 everywhere), large negative qm - sev
                rows.append((d, sp, "V__ABMVL001", "SF", "BMVLP1", "A", "C", 0.0, -5.0, -2.0, -5.0, 0.0, 0.0, 0.0, 0.0, 0))

        conn.executemany(
            """
            INSERT INTO sbmu_baseline_sp (
                settlement_date, sp, sec_bmu_id, run_type, sec_party_id, gsp_group,
                pc_flag, fpn, qme, sev, qm, qdei, qsd, qcv, wmi, wmi_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    with get_conn(db_path) as conn:
        res1 = compute_baseline_audit(conn, "2026-10-01", "2026-10-14", sec_party_id="FROZEN1")
        # Second call hits base cache and switches selected party cleanly
        res2 = compute_baseline_audit(conn, "2026-10-01", "2026-10-14", sec_party_id="SIGNINV")

    by_id = {v["party_id"]: v for v in res1["vtps"]}
    assert by_id["FROZEN1"]["methodology_class"] == "BL01 (P376 — Frozen Lookback)"
    assert by_id["FROZEN1"]["bl01_r2"] is not None and by_id["FROZEN1"]["bl01_r2"] >= 0.70
    assert by_id["FROZEN1"]["bl01_drift_mwh"] is not None and by_id["FROZEN1"]["bl01_drift_mwh"] > 4.0

    assert by_id["CUSTOM1"]["methodology_class"] == "Hybrid / Custom Baseline"

    assert by_id["SIGNINV"]["methodology_class"] == "Sign-Inverted / Test SEV"
    assert by_id["SIGNINV"]["unsettled_rebound_mwh"] == 0.0
    assert by_id["SIGNINV"]["non_active_mae_mwh"] == 0.0
    assert res2["selected_party_id"] == "SIGNINV"

    # BM-only VLP with zero wholesale activations must have 0 unsettled rebound
    assert by_id["BMVLP1"]["unsettled_rebound_mwh"] == 0.0
    assert by_id["BMVLP1"]["non_active_mae_mwh"] == 3.0


