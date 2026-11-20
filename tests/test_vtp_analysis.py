"""Unit and FastAPI integration tests for VTP BMU Analysis."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.db import get_conn, init_db
from backend.elexon import extract_gsp_group, parse_bsc_signatories_html
from backend.forensics import compute_forensics
from backend.main import app


def test_parse_bsc_signatories_html() -> None:
    sample = """
    <table><tbody>
      <tr>
        <td class="title">Axle Energy</td>
        <td>AXLEENER </td>
        <td>128 City Road\nLondon</td>
        <td>BP, VP, AV, VT</td>
      </tr>
      <tr>
        <td class="title">Octopus Energy Limited</td>
        <td>MERCURY</td>
        <td>UK House</td>
        <td>BP, TS, EN, MV</td>
      </tr>
    </tbody></table>
    """
    rows = parse_bsc_signatories_html(sample)
    assert len(rows) == 2
    axle = rows[0]
    assert axle.party_id == "AXLEENER"
    assert axle.company_name == "Axle Energy"
    assert axle.is_vtp is True
    assert axle.is_amvlp is True
    assert axle.is_supplier is False

    octo = rows[1]
    assert octo.party_id == "MERCURY"
    assert octo.is_supplier is True
    assert octo.is_vtp is False


def test_extract_gsp_group() -> None:
    assert extract_gsp_group("V__AAXLE001") == "A"
    assert extract_gsp_group("2__DMRCY000") == "D"
    assert extract_gsp_group("T_DRAXX-1") == ""
    assert extract_gsp_group("") == ""


def _seed_synthetic_db(db_path: Path) -> None:
    init_db(db_path)
    with get_conn(db_path) as conn:
        # Parties
        parties = [
            ("AXLEENER", "Axle Energy", json.dumps(["BP", "VP", "AV", "VT"]), 1, 1, 1, 0),
            ("ZENOBER1", "Zenobe Rental 1 Limited", json.dumps(["BP", "VP", "VT"]), 1, 1, 0, 0),
            ("MERCURY", "Octopus Energy Limited", json.dumps(["BP", "TS"]), 0, 0, 0, 1),
            ("SMARTEST", "SmartestEnergy Ltd", json.dumps(["BP", "TS"]), 0, 0, 0, 1),
        ]
        for pid, name, roles, vtp, vlp, av, sup in parties:
            conn.execute(
                """
                INSERT INTO parties (
                    party_id, company_name, roles_json, is_vtp, is_vlp, is_amvlp, is_supplier, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '2026-10-10T00:00:00Z')
                """,
                (pid, name, roles, vtp, vlp, av, sup),
            )

        dates = ["2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]
        sbps = [180.0, 150.0, 45.0, 50.0]  # 2 expensive, 2 very cheap days
        ssc = 100.0
        gsps = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N", "P"]

        for d, sbp in zip(dates, sbps):
            conn.execute(
                """
                INSERT INTO ingested_days (
                    settlement_date, run_type, has_bmu_sp, has_party_level, has_sp_level, ingested_at
                ) VALUES (?, 'SF', 1, 1, 1, '2026-10-10T00:00:00Z')
                """,
                (d,),
            )
            for sp in range(1, 49):
                conn.execute(
                    """
                    INSERT INTO sp_market_data (
                        settlement_date, sp, run_type, ssc, sbp, ssp, mpj, qcvj, sccj, scvj
                    ) VALUES (?, ?, 'SF', ?, ?, ?, ?, 10.0, 1000.0, 1000.0)
                    """,
                    (d, sp, ssc, sbp, sbp, sbp),
                )

            # AXLEENER: flat volume every day across all 14 GSPs on MERCURY 2__ BMUs, 06:00-23:00, 100% positive
            axle_total_cash = 0.0
            for sp in range(13, 47):
                for g in gsps:
                    qcv = 1.0
                    cash = qcv * ssc
                    axle_total_cash += cash
                    conn.execute(
                        """
                        INSERT INTO bmu_sp_compensation (
                            settlement_date, sp, pri_bmu_id, sec_bmu_id, run_type,
                            pri_party_id, sec_party_id, gsp_group, qsd, qcv, ssc, comp_cashflow
                        ) VALUES (?, ?, ?, ?, 'SF', 'MERCURY', 'AXLEENER', ?, ?, ?, ?, ?)
                        """,
                        (d, sp, f"2__{g}MRCY000", f"V__{g}AXLE001", g, qcv, qcv, ssc, cash),
                    )

            # ZENOBER1: only on high-price days (sbp > 120), 2 GSPs, commercial supplier, balanced rebound
            zeno_cash = 0.0
            if sbp > 120:
                for sp in (37, 38, 39, 40):
                    qcv = 5.0
                    zeno_cash += qcv * ssc
                    conn.execute(
                        """
                        INSERT INTO bmu_sp_compensation (
                            settlement_date, sp, pri_bmu_id, sec_bmu_id, run_type,
                            pri_party_id, sec_party_id, gsp_group, qsd, qcv, ssc, comp_cashflow
                        ) VALUES (?, ?, 'C__ASMAR001', 'V__AZENO001', 'SF', 'SMARTEST', 'ZENOBER1', 'A', ?, ?, ?, ?)
                        """,
                        (d, sp, qcv, qcv, ssc, qcv * ssc),
                    )
                for sp in (3, 4, 5, 6):
                    qcv = -4.0
                    zeno_cash += qcv * ssc
                    conn.execute(
                        """
                        INSERT INTO bmu_sp_compensation (
                            settlement_date, sp, pri_bmu_id, sec_bmu_id, run_type,
                            pri_party_id, sec_party_id, gsp_group, qsd, qcv, ssc, comp_cashflow
                        ) VALUES (?, ?, 'C__ASMAR001', 'V__AZENO001', 'SF', 'SMARTEST', 'ZENOBER1', 'A', ?, ?, ?, ?)
                        """,
                        (d, sp, qcv, qcv, ssc, qcv * ssc),
                    )

            tot_day_comp = axle_total_cash + zeno_cash
            conn.execute(
                """
                INSERT INTO party_daily_settlement (settlement_date, party_id, run_type, sccp, scvp)
                VALUES (?, 'MERCURY', 'SF', ?, ?), (?, 'SMARTEST', 'SF', ?, ?)
                """,
                (d, axle_total_cash, tot_day_comp * 0.15, d, zeno_cash, tot_day_comp * 0.85),
            )


def test_forensics_distinguishes_ev_baselining_from_commercial(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    _seed_synthetic_db(db_path)

    with get_conn(db_path) as conn:
        res = compute_forensics(conn, "2026-10-01", "2026-10-04")

    by_id = {v["party_id"]: v for v in res["vtps"]}
    axle = by_id["AXLEENER"]
    zeno = by_id["ZENOBER1"]

    assert axle["ev_focus_score"] >= 80
    assert axle["baselining_risk_score"] >= 80
    assert axle["signals"]["one_sided_ratio_pct"] == 100.0
    assert axle["signals"]["pct_below_ssc"] == 50.0
    assert axle["signals"]["gsp_count"] == 14

    assert zeno["ev_focus_score"] < 30
    assert zeno["baselining_risk_score"] < axle["baselining_risk_score"] - 35
    assert zeno["signals"]["pct_below_ssc"] == 0.0


def test_api_endpoints_end_to_end(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "api_test.db"
    _seed_synthetic_db(db_path)
    monkeypatch.setenv("VTP_DB_PATH", str(db_path))

    client = TestClient(app)

    st = client.get("/api/status")
    assert st.status_code == 200
    assert st.json()["granular_days"] == 4

    ov = client.get("/api/overview?start_date=2026-10-01&end_date=2026-10-04")
    assert ov.status_code == 200
    assert ov.json()["summary"]["max_reconciliation_diff_gbp"] == 0.0

    tm = client.get("/api/timing?start_date=2026-10-01&end_date=2026-10-04")
    assert tm.status_code == 200
    assert len(tm.json()["intraday"]) == 48
    assert len(tm.json()["heatmap"]) == 4

    cp = client.get("/api/compensation?start_date=2026-10-01&end_date=2026-10-04")
    assert cp.status_code == 200
    assert len(cp.json()["flows"]) >= 2

    fr = client.get("/api/forensics?start_date=2026-10-01&end_date=2026-10-04")
    assert fr.status_code == 200
    assert fr.json()["market_verdict"]["ev_focused_share_pct"] > 90

    ex = client.get("/api/explorer?start_date=2026-10-01&end_date=2026-10-04")
    assert ex.status_code == 200
    assert ex.json()["total"] > 0

    csv_resp = client.get("/api/explorer/export.csv?start_date=2026-10-01&end_date=2026-10-04")
    assert csv_resp.status_code == 200
    assert "sec_bmu_id" in csv_resp.text

    pt = client.get("/api/parties?role=VT")
    assert pt.status_code == 200
    assert pt.json()["total"] == 2
