"""Comprehensive Python 3.14 test suite for the Python-only Dash dashboard.

Covers:
1. `py_dashboard.formatting` helpers and UI component builders
2. `py_dashboard.data_access` SQLite wrappers, zip auto-extraction, and export builders
3. All 6 view renderers (`overview`, `timing`, `compensation`, `baseline_audit`,
   `forensics`, `explorer`) against the real SQLite DB (`data/vtp_analysis.db`)
   and empty-data edge cases (with full `PlotlyJSONEncoder` serialization checks)
4. `py_dashboard.app.create_app()`, Flask test client HTTP routes, and Dash callback
   invocation including CSV & Markdown export downloads.
"""

from __future__ import annotations

import csv
import io
import json
import math
import zipfile
from pathlib import Path
from typing import Any

import pytest
from plotly.utils import PlotlyJSONEncoder

from backend.db import DEFAULT_DB_PATH, init_db
from py_dashboard import data_access as da
from py_dashboard import formatting as fmt
from py_dashboard.app import create_app
from py_dashboard.views.baseline_audit import render_baseline_audit
from py_dashboard.views.compensation import render_compensation
from py_dashboard.views.explorer import render_explorer_results, render_explorer_shell
from py_dashboard.views.forensics import render_forensics
from py_dashboard.views.overview import render_overview
from py_dashboard.views.timing import render_timing

# Compact 3-day slice from the bundled DB so full-DB tests stay fast (<15s total)
TEST_START = "2026-10-01"
TEST_END = "2026-10-03"


def _assert_dash_serializable(component: Any) -> str:
    """Ensure a Dash component tree (including all Plotly figures) JSON-serializes cleanly."""
    assert component is not None
    payload = json.dumps(component, cls=PlotlyJSONEncoder)
    assert len(payload) > 2
    return payload


def _has_real_db() -> bool:
    return DEFAULT_DB_PATH.exists() and DEFAULT_DB_PATH.stat().st_size > 0


# ---------------------------------------------------------------------------
# 1. formatting.py unit tests
# ---------------------------------------------------------------------------


class TestFormatting:
    def test_palette_tokens_present(self) -> None:
        for key in (
            "bg_canvas",
            "bg_surface",
            "ink",
            "teal",
            "vermilion",
            "amber",
            "indigo",
            "chart_series",
        ):
            assert key in fmt.PALETTE
        assert isinstance(fmt.PALETTE["chart_series"], list)
        assert len(fmt.PALETTE["chart_series"]) >= 5

    def test_gbp_formatters(self) -> None:
        assert fmt.fmt_gbp(12345.6) == "£12,346"
        assert fmt.fmt_gbp(-987) == "-£987"
        assert fmt.fmt_gbp(None) == "£0"
        assert fmt.fmt_gbp(math.nan) == "£0"

        assert fmt.fmt_gbp_exact(1234.5) == "£1,234.50"
        assert fmt.fmt_gbp_exact(-0.25) == "-£0.25"

        assert fmt.fmt_gbp_compact(1_240_000) == "£1.24m"
        assert fmt.fmt_gbp_compact(-45_200) == "-£45.2k"
        assert fmt.fmt_gbp_compact(812) == "£812"
        assert fmt.fmt_gbp(2_500_000, compact=True) == "£2.50m"

        assert fmt.fmt_signed_gbp(500) == "+£500"
        assert fmt.fmt_signed_gbp(-500) == "-£500"
        assert fmt.fmt_signed_gbp(0) == "£0"
        assert fmt.fmt_signed_gbp(1_500_000, compact=True) == "+£1.50m"

    def test_unit_and_number_formatters(self) -> None:
        assert fmt.fmt_mwh(1234.56) == "1,234.6 MWh"
        assert fmt.fmt_mwh(10.0, decimals=0) == "10 MWh"
        assert fmt.fmt_mw(42.34) == "42.3 MW"
        assert fmt.fmt_pct(64.25) == "64.2%"
        assert fmt.fmt_num(1234567) == "1,234,567"
        assert fmt.fmt_num(12.345, decimals=2) == "12.35"

    def test_sp_to_time_and_short_date_and_risk_tone(self) -> None:
        assert fmt.sp_to_time(1) == "00:00"
        assert fmt.sp_to_time(2) == "00:30"
        assert fmt.sp_to_time(36) == "17:30"
        assert fmt.sp_to_time(48) == "23:30"
        assert fmt.sp_to_time(49) == "00:00"

        assert fmt.short_date("2026-10-14") == "14 Oct"
        assert fmt.short_date("2026-01-05") == "5 Jan"
        assert fmt.short_date(None) == ""
        assert fmt.short_date("invalid") == "invalid"

        assert fmt.risk_tone(80) == "vermilion"
        assert fmt.risk_tone(65) == "vermilion"
        assert fmt.risk_tone(50) == "amber"
        assert fmt.risk_tone(20) == "teal"

    def test_plotly_base_layout_merges_nested_dicts(self) -> None:
        layout = fmt.plotly_base_layout(
            height=420,
            xaxis={"title": "Settlement Period"},
            yaxis={"range": [0, 100]},
        )
        assert layout["height"] == 420
        assert layout["xaxis"]["title"] == "Settlement Period"
        assert layout["xaxis"]["showgrid"] is False  # preserved default
        assert layout["yaxis"]["range"] == [0, 100]
        assert layout["yaxis"]["showgrid"] is True  # preserved default

    def test_ui_builders_serialize(self) -> None:
        _assert_dash_serializable(fmt.badge("BL01", tone="vermilion", title="Frozen"))
        _assert_dash_serializable(fmt.kpi_card("Total Comp", "£8.36m", sub="30 days", tone="teal"))
        _assert_dash_serializable(
            fmt.section_card("Panel Title", ["Body"], subtitle="Sub", actions=fmt.badge("OK"))
        )
        _assert_dash_serializable(fmt.empty_state("No data", "Sync dates first."))


# ---------------------------------------------------------------------------
# 2. data_access.py unit & integration tests
# ---------------------------------------------------------------------------


class TestDataAccess:
    def test_ensure_db_ready_extracts_zip(self, tmp_path: Path) -> None:
        # Build a valid empty SQLite DB and pack it into vtp_analysis_db.zip
        src_db = tmp_path / "source.db"
        init_db(src_db)
        zip_path = tmp_path / "vtp_analysis_db.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(src_db, arcname="vtp_analysis.db")

        target_db = tmp_path / "vtp_analysis.db"
        assert not target_db.exists()
        resolved = da.ensure_db_ready(target_db)
        assert resolved == target_db
        assert target_db.exists()
        assert target_db.stat().st_size > 0

    def test_start_sync_dates_validation(self) -> None:
        ok, msg = da.start_sync_dates("", "2026-10-05")
        assert ok is False
        assert "required" in msg.lower()

        ok, msg = da.start_sync_dates("2026-10-10", "2026-10-05")
        assert ok is False
        assert "before" in msg.lower()

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_data_access_wrappers_on_real_db(self) -> None:
        status = da.get_status()
        assert status["granular_days"] >= 1
        assert "sync" in status

        s, e = da.resolve_date_window()
        assert s <= e
        bs, be = da.resolve_baseline_window()
        assert bs <= be

        ov = da.get_overview(TEST_START, TEST_END)
        assert "summary" in ov and "top_vtps" in ov

        ti = da.get_timing(TEST_START, TEST_END)
        assert "intraday" in ti and "heatmap" in ti

        co = da.get_compensation(TEST_START, TEST_END)
        assert "suppliers" in co and "flows" in co

        fo = da.compute_forensics(TEST_START, TEST_END)
        assert "vtps" in fo and "market_verdict" in fo

        au = da.compute_baseline_audit(TEST_START, TEST_END)
        assert "market_summary" in au and "vtps" in au

        exp_pair = da.get_explorer(TEST_START, TEST_END, group_by="bmu_pair", limit=10)
        assert exp_pair["group_by"] == "bmu_pair"
        assert isinstance(exp_pair["items"], list)

        exp_raw = da.get_explorer(TEST_START, TEST_END, group_by="raw", limit=10)
        assert exp_raw["group_by"] == "raw"

        parties = da.get_parties(role="VT")
        assert "items" in parties and len(parties["items"]) > 0

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_export_generators_on_real_db(self) -> None:
        csv_name, csv_text = da.export_baseline_audit_csv(TEST_START, TEST_END)
        assert csv_name.endswith(".csv")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        assert len(rows) > 0
        assert "sec_bmu_id" in rows[0]

        md_name, md_text = da.export_baseline_briefing_md(TEST_START, TEST_END)
        assert md_name.endswith(".md")
        assert "#" in md_text
        assert len(md_text) > 200

        exp_name, exp_csv = da.export_explorer_csv(
            TEST_START, TEST_END, group_by="bmu_pair", sec_party_id="AXLEENER"
        )
        assert exp_name.endswith(".csv")
        exp_rows = list(csv.DictReader(io.StringIO(exp_csv)))
        assert len(exp_rows) > 0


# ---------------------------------------------------------------------------
# 3. All 6 view renderers — real SQLite DB + empty-data edge cases
# ---------------------------------------------------------------------------


class TestViewRenderers:
    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_overview_view_real_db(self) -> None:
        data = da.get_overview(TEST_START, TEST_END)
        comp = render_overview(data)
        payload = _assert_dash_serializable(comp)
        assert "Settlement" in payload or "VTP" in payload

    def test_overview_view_empty(self) -> None:
        _assert_dash_serializable(render_overview({}))
        _assert_dash_serializable(
            render_overview(
                {
                    "summary": {},
                    "daily_series": [],
                    "macro_series": [],
                    "vtps": [],
                    "top_winners": [],
                    "top_payers": [],
                }
            )
        )

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_timing_view_real_db(self) -> None:
        data = da.get_timing(TEST_START, TEST_END)
        _assert_dash_serializable(render_timing(data, selected_vtp=""))

        data_vtp = da.get_timing(TEST_START, TEST_END, sec_party_id="AXLEENER")
        _assert_dash_serializable(render_timing(data_vtp, selected_vtp="AXLEENER"))

    def test_timing_view_empty(self) -> None:
        _assert_dash_serializable(render_timing({}, selected_vtp=""))
        _assert_dash_serializable(
            render_timing(
                {
                    "sp_profile": [],
                    "heatmap": [],
                    "vtp_schedules": [],
                    "weekday_vs_weekend": [],
                    "vtp_options": [],
                },
                selected_vtp="UNKNOWN",
            )
        )

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_compensation_view_real_db(self) -> None:
        data = da.get_compensation(TEST_START, TEST_END)
        _assert_dash_serializable(render_compensation(data))

        data_f = da.get_compensation(
            TEST_START, TEST_END, sec_party_id="AXLEENER", pri_party_id="MERCURY"
        )
        _assert_dash_serializable(
            render_compensation(data_f, filter_vtp="AXLEENER", filter_supplier="MERCURY")
        )

    def test_compensation_view_empty(self) -> None:
        _assert_dash_serializable(render_compensation({}))
        _assert_dash_serializable(
            render_compensation(
                {
                    "reconciliation": {},
                    "suppliers": [],
                    "flows": [],
                    "p415_vs_bm": {},
                    "vtp_options": [],
                    "supplier_options": [],
                },
                filter_vtp="AXLEENER",
                filter_supplier="MERCURY",
            )
        )

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_baseline_audit_view_real_db(self) -> None:
        data = da.compute_baseline_audit(TEST_START, TEST_END)
        _assert_dash_serializable(render_baseline_audit(data))

        data_vtp = da.compute_baseline_audit(TEST_START, TEST_END, sec_party_id="AXLEENER")
        _assert_dash_serializable(
            render_baseline_audit(data_vtp, selected_party_id="AXLEENER")
        )

    def test_baseline_audit_view_empty(self) -> None:
        _assert_dash_serializable(render_baseline_audit({}))
        _assert_dash_serializable(
            render_baseline_audit(
                {
                    "has_data": False,
                    "market": {},
                    "vtp_summary": [],
                    "sbmu_audit": [],
                    "sp_profile": [],
                    "daily_series": [],
                }
            )
        )

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_forensics_view_real_db(self) -> None:
        data = da.compute_forensics(TEST_START, TEST_END)
        _assert_dash_serializable(render_forensics(data))
        _assert_dash_serializable(render_forensics(data, selected_vtp_id="AXLEENER"))

    def test_forensics_view_empty(self) -> None:
        _assert_dash_serializable(render_forensics({}))
        _assert_dash_serializable(
            render_forensics({"summary": {}, "vtps": [], "ev_suppliers": []}, selected_vtp_id="NONE")
        )

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_explorer_view_real_db(self) -> None:
        shell = render_explorer_shell(TEST_START, TEST_END)
        _assert_dash_serializable(shell)

        for mode in ("bmu_pair", "raw"):
            data = da.get_explorer(TEST_START, TEST_END, group_by=mode, limit=25)
            parties = da.get_parties(role="VT")
            res = render_explorer_results(
                data,
                parties,
                {"group_by": mode, "page": 0, "limit": 25},
            )
            _assert_dash_serializable(res)

    def test_explorer_view_empty(self) -> None:
        _assert_dash_serializable(render_explorer_shell(TEST_START, TEST_END))
        _assert_dash_serializable(
            render_explorer_results(
                {"items": [], "total": 0, "group_by": "bmu_pair"},
                {"items": [], "total": 0},
                {"group_by": "bmu_pair", "page": 0, "limit": 200},
            )
        )


# ---------------------------------------------------------------------------
# 4. Dash app creation, Flask HTTP routes, and callback execution
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dash_app():
    return create_app()


class TestDashAppAndCallbacks:
    def test_flask_routes_return_200(self, dash_app) -> None:
        client = dash_app.server.test_client()

        resp = client.get("/")
        assert resp.status_code == 200
        assert b"GB VTP" in resp.data or b"_dash-config" in resp.data

        css = client.get("/assets/styles.css")
        assert css.status_code == 200
        assert b"--bg-canvas" in css.data

        layout = client.get("/_dash-layout")
        assert layout.status_code == 200

        deps = client.get("/_dash-dependencies")
        assert deps.status_code == 200
        dep_list = deps.get_json()
        assert isinstance(dep_list, list) and len(dep_list) >= 10

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    @pytest.mark.parametrize(
        "tab",
        ["overview", "timing", "compensation", "baseline_audit", "forensics", "explorer"],
    )
    def test_main_content_callback_all_tabs(self, dash_app, tab: str) -> None:
        client = dash_app.server.test_client()
        payload = {
            "output": "main-content.children",
            "outputs": {"id": "main-content", "property": "children"},
            "inputs": [
                {"id": "active-tab-store", "property": "data", "value": tab},
                {"id": "date-start-input", "property": "value", "value": TEST_START},
                {"id": "date-end-input", "property": "value", "value": TEST_END},
                {"id": "timing-vtp-store", "property": "data", "value": ""},
                {"id": "comp-vtp-store", "property": "data", "value": ""},
                {"id": "comp-supplier-store", "property": "data", "value": ""},
                {"id": "audit-vtp-store", "property": "data", "value": ""},
                {"id": "audit-bmu-store", "property": "data", "value": ""},
                {"id": "forensics-vtp-store", "property": "data", "value": ""},
                {"id": "reload-tick-store", "property": "data", "value": 0},
            ],
            "changedPropIds": ["active-tab-store.data"],
            "state": [],
        }
        resp = client.post("/_dash-update-component", json=payload)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "response" in body
        assert body["response"]["main-content"]["children"] is not None

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_export_download_callbacks(self, dash_app) -> None:
        client = dash_app.server.test_client()

        # 1. Baseline Audit CSV download callback
        resp_csv = client.post(
            "/_dash-update-component",
            json={
                "output": "download-audit-csv.data",
                "outputs": {"id": "download-audit-csv", "property": "data"},
                "inputs": [
                    {"id": "audit-export-csv-btn", "property": "n_clicks", "value": 1},
                ],
                "state": [
                    {"id": "date-start-input", "property": "value", "value": TEST_START},
                    {"id": "date-end-input", "property": "value", "value": TEST_END},
                    {"id": "audit-vtp-store", "property": "data", "value": ""},
                    {"id": "audit-bmu-store", "property": "data", "value": ""},
                ],
                "changedPropIds": ["audit-export-csv-btn.n_clicks"],
            },
        )
        assert resp_csv.status_code == 200
        dl_csv = resp_csv.get_json()["response"]["download-audit-csv"]["data"]
        assert dl_csv["filename"].endswith(".csv")
        assert "sec_bmu_id" in dl_csv["content"]

        # 2. Policy Briefing Markdown download callback
        resp_md = client.post(
            "/_dash-update-component",
            json={
                "output": "download-audit-md.data",
                "outputs": {"id": "download-audit-md", "property": "data"},
                "inputs": [
                    {"id": "audit-export-md-btn", "property": "n_clicks", "value": 1},
                ],
                "state": [
                    {"id": "date-start-input", "property": "value", "value": TEST_START},
                    {"id": "date-end-input", "property": "value", "value": TEST_END},
                    {"id": "audit-vtp-store", "property": "data", "value": ""},
                    {"id": "audit-bmu-store", "property": "data", "value": ""},
                ],
                "changedPropIds": ["audit-export-md-btn.n_clicks"],
            },
        )
        assert resp_md.status_code == 200
        dl_md = resp_md.get_json()["response"]["download-audit-md"]["data"]
        assert dl_md["filename"].endswith(".md")
        assert len(dl_md["content"]) > 200

        # 3. Explorer CSV download callback
        resp_exp = client.post(
            "/_dash-update-component",
            json={
                "output": "download-explorer-csv.data",
                "outputs": {"id": "download-explorer-csv", "property": "data"},
                "inputs": [
                    {"id": "explorer-export-csv-btn", "property": "n_clicks", "value": 1},
                ],
                "state": [
                    {"id": "date-start-input", "property": "value", "value": TEST_START},
                    {"id": "date-end-input", "property": "value", "value": TEST_END},
                    {"id": "explorer-group-by", "property": "value", "value": "bmu_pair"},
                    {"id": "explorer-vtp-input", "property": "value", "value": "AXLEENER"},
                    {"id": "explorer-supplier-input", "property": "value", "value": ""},
                    {"id": "explorer-gsp-select", "property": "value", "value": ""},
                    {"id": "explorer-sp-select", "property": "value", "value": ""},
                    {"id": "explorer-search-input", "property": "value", "value": ""},
                ],
                "changedPropIds": ["explorer-export-csv-btn.n_clicks"],
            },
        )
        assert resp_exp.status_code == 200
        dl_exp = resp_exp.get_json()["response"]["download-explorer-csv"]["data"]
        assert dl_exp["filename"].endswith(".csv")
        assert len(dl_exp["content"]) > 50

    @pytest.mark.skipif(not _has_real_db(), reason="Bundled SQLite DB not present")
    def test_explorer_results_callback(self, dash_app) -> None:
        client = dash_app.server.test_client()
        resp = client.post(
            "/_dash-update-component",
            json={
                "output": "explorer-results-container.children",
                "outputs": {"id": "explorer-results-container", "property": "children"},
                "inputs": [
                    {"id": "explorer-page-store", "property": "data", "value": 0},
                    {"id": "explorer-group-by", "property": "value", "value": "bmu_pair"},
                    {"id": "explorer-vtp-input", "property": "value", "value": "AXLEENER"},
                    {"id": "explorer-supplier-input", "property": "value", "value": ""},
                    {"id": "explorer-gsp-select", "property": "value", "value": ""},
                    {"id": "explorer-sp-select", "property": "value", "value": ""},
                    {"id": "explorer-search-input", "property": "value", "value": ""},
                    {"id": "explorer-party-role-select", "property": "value", "value": "VT"},
                    {"id": "explorer-party-search-input", "property": "value", "value": ""},
                    {"id": "date-start-input", "property": "value", "value": TEST_START},
                    {"id": "date-end-input", "property": "value", "value": TEST_END},
                    {"id": "reload-tick-store", "property": "data", "value": 0},
                ],
                "state": [],
                "changedPropIds": ["explorer-vtp-input.value"],
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["response"]["explorer-results-container"]["children"] is not None
