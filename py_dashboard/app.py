"""Dash application shell, layout, and callback wiring for GB VTP Settlement Forensics."""

from __future__ import annotations

import datetime as dt
from typing import Any

import dash
from dash import ALL, Input, Output, State, ctx, dcc, html
from dash.exceptions import PreventUpdate

from . import data_access as da
from .formatting import badge, empty_state

ANALYSIS_NAV: list[tuple[str, str, str]] = [
    ("overview", "Settlement overview", "◉"),
    ("timing", "When VTPs trade", "◷"),
    ("compensation", "Supplier compensation", "⇄"),
    ("baseline_audit", "Baseline & BL01 audit", "⚖"),
    ("forensics", "EV baselining lab", "⚑"),
]

DATA_NAV: list[tuple[str, str, str]] = [
    ("explorer", "BMU & party explorer", "▤"),
]

EXPLORER_PAGE_SIZE = 200


def _add_days(iso_date: str, delta: int) -> str:
    d = dt.date.fromisoformat(iso_date)
    return (d + dt.timedelta(days=delta)).isoformat()


def _render_sidebar_stats(status: dict[str, Any] | None) -> list[Any]:
    s = status or {}

    def _row(label: str, val: Any) -> html.Div:
        return html.Div(
            [
                html.Span(label),
                html.Span(val if val is not None else "—", className="sidebar-stat-val"),
            ],
            className="sidebar-stat-row",
        )

    bmu_rows = s.get("bmu_sp_rows")
    bmu_rows_fmt = f"{int(bmu_rows):,}" if isinstance(bmu_rows, (int, float)) else "—"
    return [
        _row("Granular BMU days", s.get("granular_days")),
        _row("Baseline days", s.get("baseline_days")),
        _row("Macro history days", s.get("macro_days")),
        _row("BSC signatories", s.get("parties_count")),
        _row("Registered VTPs", s.get("registered_vtps_count")),
        _row("BMU × SP rows", bmu_rows_fmt),
    ]


def _render_topbar_badges(status: dict[str, Any] | None) -> list[Any]:
    s = status or {}
    items: list[Any] = []
    breakdown = s.get("run_breakdown") or []
    if breakdown:
        summary = ", ".join(f"{r['run_type']} {r['days']}d" for r in breakdown)
        items.append(
            badge(
                summary,
                tone="neutral",
                title="Settlement runs loaded in local SQLite store",
            )
        )
    sync = s.get("sync") or {}
    if sync.get("status") == "running":
        cur = sync.get("current_date") or "..."
        items.append(
            badge(
                f"Syncing {sync.get('completed_days', 0)}/{sync.get('total_days', 0)} ({cur})",
                tone="amber",
            )
        )
    return items


def _render_sync_progress(sync: dict[str, Any] | None) -> Any:
    if not sync or sync.get("status") in (None, "idle"):
        return None
    children: list[Any] = [
        html.Div(
            [
                html.Strong("Last job: "),
                f"{sync.get('status')} ({sync.get('completed_days', 0)}/{sync.get('total_days', 0)} days)",
            ]
        )
    ]
    if sync.get("message"):
        children.append(
            html.Div(
                sync["message"],
                style={"color": "var(--ink-secondary)", "marginTop": "2px"},
            )
        )
    return html.Div(children, className="sync-progress-box")


def _build_sidebar(status: dict[str, Any] | None) -> html.Aside:
    def _nav_btn(tab_id: str, label: str, icon: str) -> html.Button:
        cls = "nav-item active" if tab_id == "overview" else "nav-item"
        return html.Button(
            [
                html.Span(icon, className="nav-icon", **{"aria-hidden": "true"}),
                html.Span(label),
            ],
            id={"type": "sidebar-nav-btn", "tab": tab_id},
            type="button",
            className=cls,
            n_clicks=0,
        )

    return html.Aside(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(className="brand-dot", **{"aria-hidden": "true"}),
                            html.H1("GB VTP Forensics", className="sidebar-brand-title"),
                        ],
                        className="sidebar-brand-mark",
                    ),
                    html.P(
                        "Elexon SAA-I014 settlement ledger and P415 market analytics",
                        className="sidebar-brand-sub",
                    ),
                ],
                className="sidebar-brand",
            ),
            html.Nav(
                [
                    html.Div("Analysis", className="nav-section-label"),
                    *[_nav_btn(tid, lbl, ico) for tid, lbl, ico in ANALYSIS_NAV],
                    html.Div("Data & Registry", className="nav-section-label"),
                    *[_nav_btn(tid, lbl, ico) for tid, lbl, ico in DATA_NAV],
                ],
                className="sidebar-nav",
                **{"aria-label": "Primary navigation"},
            ),
            html.Div(
                _render_sidebar_stats(status),
                id="sidebar-stats-footer",
                className="sidebar-footer",
            ),
        ],
        className="sidebar",
    )


def _build_topbar(
    init_start: str,
    init_end: str,
    status: dict[str, Any] | None,
) -> html.Header:
    s = status or {}
    granular_days = s.get("granular_days")
    all_label = f"All {granular_days}d" if granular_days else "All days"

    return html.Header(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("From"),
                            dcc.Input(
                                id="date-start-input",
                                type="date",
                                value=init_start,
                                debounce=True,
                            ),
                            html.Span("to"),
                            dcc.Input(
                                id="date-end-input",
                                type="date",
                                value=init_end,
                                debounce=True,
                            ),
                        ],
                        className="date-control",
                    ),
                    html.Div(
                        [
                            html.Button(
                                all_label,
                                id="preset-all-btn",
                                type="button",
                                className="preset-btn",
                                n_clicks=0,
                            ),
                            html.Button(
                                "Last 14d",
                                id="preset-14d-btn",
                                type="button",
                                className="preset-btn",
                                n_clicks=0,
                            ),
                            html.Button(
                                "Last 7d",
                                id="preset-7d-btn",
                                type="button",
                                className="preset-btn",
                                n_clicks=0,
                            ),
                        ],
                        className="preset-group",
                        role="group",
                    ),
                    html.Div(
                        _render_topbar_badges(status),
                        id="topbar-status-badges",
                        style={"display": "inline-flex", "gap": "8px", "alignItems": "center"},
                    ),
                ],
                className="topbar-left",
            ),
            html.Div(
                [
                    html.Button(
                        "↻ Reload",
                        id="reload-btn",
                        type="button",
                        className="btn btn-sm",
                        n_clicks=0,
                    ),
                    html.Button(
                        "↓ Fetch Elexon dates",
                        id="open-sync-modal-btn",
                        type="button",
                        className="btn btn-sm btn-primary",
                        n_clicks=0,
                    ),
                ],
                className="topbar-left",
            ),
        ],
        className="topbar",
    )


def _build_sync_modal(init_start: str, init_end: str) -> html.Div:
    return html.Div(
        html.Div(
            [
                html.Div(
                    [
                        html.H3(
                            "Fetch live Elexon SAA-I014 data",
                            className="panel-title",
                        ),
                        html.Button(
                            "✕",
                            id="sync-modal-close-btn",
                            type="button",
                            className="btn btn-sm",
                            n_clicks=0,
                        ),
                    ],
                    className="modal-head",
                ),
                html.Div(
                    [
                        html.P(
                            [
                                "Pulls public settlement reports directly from ",
                                html.Span(
                                    "data.elexon.co.uk/saa/api/v1/i014",
                                    className="mono",
                                ),
                                " using the most reconciled available run type (RF, R3, R2, R1, SF, or II).",
                            ],
                            className="panel-subtitle",
                            style={"marginBottom": "14px"},
                        ),
                        html.Div(
                            [
                                html.Div(
                                    [
                                        html.Label("Start settlement date", htmlFor="sync-start-input"),
                                        dcc.Input(
                                            id="sync-start-input",
                                            type="date",
                                            value=init_start,
                                            className="input",
                                            style={"width": "100%"},
                                        ),
                                    ],
                                    className="field-group",
                                ),
                                html.Div(
                                    [
                                        html.Label("End settlement date", htmlFor="sync-end-input"),
                                        dcc.Input(
                                            id="sync-end-input",
                                            type="date",
                                            value=init_end,
                                            className="input",
                                            style={"width": "100%"},
                                        ),
                                    ],
                                    className="field-group",
                                ),
                            ],
                            className="grid-2",
                            style={"gap": "12px"},
                        ),
                        html.Div(
                            dcc.Checklist(
                                id="sync-options-checklist",
                                options=[
                                    {
                                        "label": " Include granular Primary/Secondary BMU × SP records (~5 MB/day)",
                                        "value": "bmu_sp",
                                    },
                                    {
                                        "label": " Include Secondary BMU baselines & metered demand (sev / qm / wmi)",
                                        "value": "baselines",
                                    },
                                ],
                                value=["bmu_sp"],
                                className="dash-checklist-stack",
                            ),
                            className="field-group",
                        ),
                        html.Div(id="sync-progress-panel"),
                        html.Div(id="sync-feedback-msg"),
                    ],
                    className="modal-body",
                ),
                html.Div(
                    [
                        html.Button(
                            "Refresh BSC parties & BMUs",
                            id="sync-ref-btn",
                            type="button",
                            className="btn",
                            n_clicks=0,
                        ),
                        html.Button(
                            "Fetch date range",
                            id="sync-dates-btn",
                            type="button",
                            className="btn btn-teal",
                            n_clicks=0,
                        ),
                    ],
                    className="modal-foot",
                ),
            ],
            className="modal",
        ),
        id="sync-modal-backdrop",
        className="modal-backdrop hidden",
        role="dialog",
    )


def _render_view_safe(
    tab: str,
    start_date: str | None,
    end_date: str | None,
    timing_vtp: str,
    comp_vtp: str,
    comp_supplier: str,
    audit_vtp: str,
    audit_bmu: str,
    forensics_vtp: str,
) -> Any:
    try:
        if tab == "overview":
            from .views.overview import render_overview

            data = da.get_overview(start_date, end_date)
            return render_overview(data)

        if tab == "timing":
            from .views.timing import render_timing

            data = da.get_timing(start_date, end_date, sec_party_id=timing_vtp or None)
            return render_timing(data, selected_vtp=timing_vtp or "")

        if tab == "compensation":
            from .views.compensation import render_compensation

            data = da.get_compensation(
                start_date,
                end_date,
                sec_party_id=comp_vtp or None,
                pri_party_id=comp_supplier or None,
            )
            return render_compensation(
                data,
                filter_vtp=comp_vtp or "",
                filter_supplier=comp_supplier or "",
            )

        if tab == "baseline_audit":
            from .views.baseline_audit import render_baseline_audit

            data = da.compute_baseline_audit(
                start_date,
                end_date,
                sec_party_id=audit_vtp or None,
                sec_bmu_id=audit_bmu or None,
            )
            return render_baseline_audit(
                data,
                selected_party_id=audit_vtp or "",
                selected_bmu_id=audit_bmu or "",
            )

        if tab == "forensics":
            from .views.forensics import render_forensics

            data = da.compute_forensics(start_date, end_date)
            return render_forensics(data, selected_vtp_id=forensics_vtp or "")

        if tab == "explorer":
            from .views.explorer import render_explorer_shell

            s, e = da.resolve_date_window(start_date, end_date)
            return render_explorer_shell(s, e)

        return empty_state("Unknown view", f"No view registered for tab '{tab}'.")
    except Exception as exc:
        return html.Div(
            [
                html.Strong("Failed to render view: "),
                html.Span(str(exc), className="mono"),
            ],
            className="error-state",
        )


def create_app() -> dash.Dash:
    """Create and configure the Dash application with all layouts and callbacks."""
    da.ensure_db_ready()
    try:
        init_status = da.get_status()
    except Exception:
        init_status = None

    init_start, init_end = da.resolve_date_window()

    app = dash.Dash(
        __name__,
        title="GB VTP Settlement Forensics",
        suppress_callback_exceptions=True,
        update_title="Loading...",
    )

    app.layout = html.Div(
        [
            # State stores
            dcc.Store(id="active-tab-store", data="overview"),
            dcc.Store(id="timing-vtp-store", data=""),
            dcc.Store(id="comp-vtp-store", data=""),
            dcc.Store(id="comp-supplier-store", data=""),
            dcc.Store(id="audit-vtp-store", data=""),
            dcc.Store(id="audit-bmu-store", data=""),
            dcc.Store(id="forensics-vtp-store", data=""),
            dcc.Store(id="explorer-page-store", data=0),
            dcc.Store(id="reload-tick-store", data=0),
            # Download targets
            dcc.Download(id="download-audit-csv"),
            dcc.Download(id="download-audit-md"),
            dcc.Download(id="download-explorer-csv"),
            # Background sync polling interval
            dcc.Interval(id="sync-poll-interval", interval=2500, n_intervals=0, disabled=True),
            # App shell
            html.Div(
                [
                    _build_sidebar(init_status),
                    html.Div(
                        [
                            _build_topbar(init_start, init_end, init_status),
                            dcc.Loading(
                                html.Main(
                                    id="main-content",
                                    className="content-wrap",
                                ),
                                type="dot",
                                color="#0b7a75",
                            ),
                        ],
                        className="main-col",
                    ),
                ],
                className="app-shell",
            ),
            _build_sync_modal(init_start, init_end),
        ]
    )

    _register_callbacks(app)
    return app


def _register_callbacks(app: dash.Dash) -> None:
    # ------------------------------------------------------------------
    # 1. Sidebar navigation & cross-view VTP drill-down
    # ------------------------------------------------------------------
    @app.callback(
        Output("active-tab-store", "data"),
        Output("timing-vtp-store", "data"),
        Output("comp-vtp-store", "data"),
        Output("audit-vtp-store", "data"),
        Output("audit-bmu-store", "data"),
        Output("forensics-vtp-store", "data"),
        Input({"type": "sidebar-nav-btn", "tab": ALL}, "n_clicks"),
        Input({"type": "nav-vtp-btn", "target": ALL, "vtp": ALL, "idx": ALL}, "n_clicks"),
        State("active-tab-store", "data"),
        State("timing-vtp-store", "data"),
        State("comp-vtp-store", "data"),
        State("audit-vtp-store", "data"),
        State("audit-bmu-store", "data"),
        State("forensics-vtp-store", "data"),
        prevent_initial_call=True,
    )
    def _handle_navigation(
        _sidebar_clicks: list[int | None],
        _drill_clicks: list[int | None],
        cur_tab: str,
        timing_vtp: str,
        comp_vtp: str,
        audit_vtp: str,
        audit_bmu: str,
        forensics_vtp: str,
    ) -> tuple[str, str, str, str, str, str]:
        trig = ctx.triggered_id
        if not isinstance(trig, dict):
            raise PreventUpdate

        # Guard against newly mounted buttons with n_clicks == 0 or None
        triggered_prop = ctx.triggered[0] if ctx.triggered else {}
        if not triggered_prop.get("value"):
            raise PreventUpdate

        if trig.get("type") == "sidebar-nav-btn":
            new_tab = trig["tab"]
            if new_tab == cur_tab:
                raise PreventUpdate
            return new_tab, timing_vtp, comp_vtp, audit_vtp, audit_bmu, forensics_vtp

        if trig.get("type") == "nav-vtp-btn":
            target = trig.get("target", "forensics")
            vtp = trig.get("vtp", "") or ""
            if target == "forensics" and vtp:
                forensics_vtp = vtp
            elif target == "timing" and vtp:
                timing_vtp = vtp
            elif target == "compensation" and vtp:
                comp_vtp = vtp
            elif target == "baseline_audit" and vtp:
                audit_vtp = vtp
                audit_bmu = ""
            return target, timing_vtp, comp_vtp, audit_vtp, audit_bmu, forensics_vtp

        raise PreventUpdate

    @app.callback(
        Output({"type": "sidebar-nav-btn", "tab": ALL}, "className"),
        Input("active-tab-store", "data"),
        State({"type": "sidebar-nav-btn", "tab": ALL}, "id"),
    )
    def _sync_sidebar_active(active_tab: str, ids: list[dict[str, str]]) -> list[str]:
        return [
            "nav-item active" if item.get("tab") == active_tab else "nav-item"
            for item in ids
        ]

    # ------------------------------------------------------------------
    # 2. TopBar quick date presets & reload button
    # ------------------------------------------------------------------
    @app.callback(
        Output("date-start-input", "value"),
        Output("date-end-input", "value"),
        Input("preset-all-btn", "n_clicks"),
        Input("preset-14d-btn", "n_clicks"),
        Input("preset-7d-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _apply_date_preset(
        _all_clicks: int,
        _14_clicks: int,
        _7_clicks: int,
    ) -> tuple[str, str]:
        trig = ctx.triggered_id
        min_d, max_d = da.resolve_date_window()
        if trig == "preset-all-btn":
            return min_d, max_d
        if trig == "preset-14d-btn":
            start = max(min_d, _add_days(max_d, -13))
            return start, max_d
        if trig == "preset-7d-btn":
            start = max(min_d, _add_days(max_d, -6))
            return start, max_d
        raise PreventUpdate

    @app.callback(
        Output("reload-tick-store", "data"),
        Input("reload-btn", "n_clicks"),
        State("reload-tick-store", "data"),
        prevent_initial_call=True,
    )
    def _bump_reload(_n: int, tick: int) -> int:
        return (tick or 0) + 1

    # ------------------------------------------------------------------
    # 3. Sync modal open/close, sync actions & live polling
    # ------------------------------------------------------------------
    @app.callback(
        Output("sync-modal-backdrop", "className"),
        Input("open-sync-modal-btn", "n_clicks"),
        Input({"type": "open-sync-btn", "idx": ALL}, "n_clicks"),
        Input("sync-modal-close-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def _toggle_sync_modal(
        _open_top: int,
        _open_inline: list[int | None],
        _close: int,
    ) -> str:
        triggered = ctx.triggered[0] if ctx.triggered else {}
        if not triggered.get("value"):
            raise PreventUpdate
        trig = ctx.triggered_id
        if trig == "sync-modal-close-btn":
            return "modal-backdrop hidden"
        return "modal-backdrop"

    @app.callback(
        Output("sync-feedback-msg", "children"),
        Output("sync-poll-interval", "disabled"),
        Output("reload-tick-store", "data", allow_duplicate=True),
        Input("sync-dates-btn", "n_clicks"),
        Input("sync-ref-btn", "n_clicks"),
        State("sync-start-input", "value"),
        State("sync-end-input", "value"),
        State("sync-options-checklist", "value"),
        State("reload-tick-store", "data"),
        prevent_initial_call=True,
    )
    def _trigger_sync_action(
        _dates_clicks: int,
        _ref_clicks: int,
        start_val: str | None,
        end_val: str | None,
        options: list[str] | None,
        tick: int,
    ) -> tuple[Any, bool, int]:
        trig = ctx.triggered_id
        opts = set(options or [])
        if trig == "sync-dates-btn":
            ok, msg = da.start_sync_dates(
                start_val or "",
                end_val or "",
                include_bmu_sp="bmu_sp" in opts,
                include_baselines="baselines" in opts,
            )
            color = "var(--teal)" if ok else "var(--vermilion)"
            return (
                html.Div(msg, style={"color": color, "fontSize": "12.5px", "marginTop": "8px"}),
                not ok,  # enable polling if started
                (tick or 0) + 1,
            )
        if trig == "sync-ref-btn":
            try:
                res = da.run_sync_reference()
                msg = (
                    f"Refreshed {res.get('signatories', 0)} BSC signatories and "
                    f"{res.get('bmus', 0)} BM units from Elexon."
                )
                return (
                    html.Div(
                        msg,
                        style={"color": "var(--teal)", "fontSize": "12.5px", "marginTop": "8px"},
                    ),
                    True,
                    (tick or 0) + 1,
                )
            except Exception as exc:
                return (
                    html.Div(
                        f"Reference sync failed: {exc}",
                        style={
                            "color": "var(--vermilion)",
                            "fontSize": "12.5px",
                            "marginTop": "8px",
                        },
                    ),
                    True,
                    tick or 0,
                )
        raise PreventUpdate

    @app.callback(
        Output("sidebar-stats-footer", "children"),
        Output("topbar-status-badges", "children"),
        Output("sync-progress-panel", "children"),
        Output("sync-poll-interval", "disabled", allow_duplicate=True),
        Input("reload-tick-store", "data"),
        Input("sync-poll-interval", "n_intervals"),
        prevent_initial_call=True,
    )
    def _refresh_status(_tick: int, _n_intervals: int) -> tuple[Any, Any, Any, bool]:
        status = da.get_status()
        sync = status.get("sync") or {}
        is_running = sync.get("status") == "running"
        return (
            _render_sidebar_stats(status),
            _render_topbar_badges(status),
            _render_sync_progress(sync),
            not is_running,
        )

    # ------------------------------------------------------------------
    # 4. Per-view filter & selection callbacks
    # ------------------------------------------------------------------
    @app.callback(
        Output("timing-vtp-store", "data", allow_duplicate=True),
        Input("timing-vtp-select", "value"),
        State("timing-vtp-store", "data"),
        prevent_initial_call=True,
    )
    def _on_timing_vtp(val: str | None, cur: str) -> str:
        nxt = val or ""
        if nxt == (cur or ""):
            raise PreventUpdate
        return nxt

    @app.callback(
        Output("comp-vtp-store", "data", allow_duplicate=True),
        Output("comp-supplier-store", "data", allow_duplicate=True),
        Input("comp-vtp-select", "value"),
        Input("comp-supplier-select", "value"),
        State("comp-vtp-store", "data"),
        State("comp-supplier-store", "data"),
        prevent_initial_call=True,
    )
    def _on_comp_filters(
        vtp: str | None,
        supplier: str | None,
        cur_vtp: str,
        cur_sup: str,
    ) -> tuple[str, str]:
        nv, ns = vtp or "", supplier or ""
        if nv == (cur_vtp or "") and ns == (cur_sup or ""):
            raise PreventUpdate
        return nv, ns

    @app.callback(
        Output("audit-vtp-store", "data", allow_duplicate=True),
        Output("audit-bmu-store", "data", allow_duplicate=True),
        Input("audit-vtp-select", "value"),
        Input("audit-bmu-select", "value"),
        State("audit-vtp-store", "data"),
        State("audit-bmu-store", "data"),
        prevent_initial_call=True,
    )
    def _on_audit_dropdowns(
        vtp: str | None,
        bmu: str | None,
        cur_vtp: str,
        cur_bmu: str,
    ) -> tuple[str, str]:
        trig = ctx.triggered_id
        nv = vtp or ""
        nb = bmu or ""
        if trig == "audit-vtp-select":
            nb = ""
        if nv == (cur_vtp or "") and nb == (cur_bmu or ""):
            raise PreventUpdate
        return nv, nb

    @app.callback(
        Output("audit-vtp-store", "data", allow_duplicate=True),
        Output("audit-bmu-store", "data", allow_duplicate=True),
        Input({"type": "audit-pick-vtp", "vtp": ALL, "idx": ALL}, "n_clicks"),
        Input({"type": "audit-pick-bmu", "vtp": ALL, "bmu": ALL, "idx": ALL}, "n_clicks"),
        State("audit-vtp-store", "data"),
        State("audit-bmu-store", "data"),
        prevent_initial_call=True,
    )
    def _on_audit_pickers(
        _vtp_clicks: list[int | None],
        _bmu_clicks: list[int | None],
        cur_vtp: str,
        cur_bmu: str,
    ) -> tuple[str, str]:
        triggered = ctx.triggered[0] if ctx.triggered else {}
        if not triggered.get("value"):
            raise PreventUpdate
        trig = ctx.triggered_id
        if not isinstance(trig, dict):
            raise PreventUpdate
        if trig.get("type") == "audit-pick-vtp":
            nv = trig.get("vtp", "") or ""
            if nv == (cur_vtp or "") and not cur_bmu:
                raise PreventUpdate
            return nv, ""
        if trig.get("type") == "audit-pick-bmu":
            nv = trig.get("vtp", "") or ""
            nb = trig.get("bmu", "") or ""
            if nv == (cur_vtp or "") and nb == (cur_bmu or ""):
                raise PreventUpdate
            return nv, nb
        raise PreventUpdate

    @app.callback(
        Output("forensics-vtp-store", "data", allow_duplicate=True),
        Input("forensics-vtp-select", "value"),
        State("forensics-vtp-store", "data"),
        prevent_initial_call=True,
    )
    def _on_forensics_select(val: str | None, cur: str) -> str:
        nxt = val or ""
        if nxt == (cur or ""):
            raise PreventUpdate
        return nxt

    @app.callback(
        Output("forensics-vtp-store", "data", allow_duplicate=True),
        Input({"type": "forensics-pick-vtp", "vtp": ALL, "idx": ALL}, "n_clicks"),
        State("forensics-vtp-store", "data"),
        prevent_initial_call=True,
    )
    def _on_forensics_pill(_clicks: list[int | None], cur: str) -> str:
        triggered = ctx.triggered[0] if ctx.triggered else {}
        if not triggered.get("value"):
            raise PreventUpdate
        trig = ctx.triggered_id
        if isinstance(trig, dict) and trig.get("type") == "forensics-pick-vtp":
            nxt = trig.get("vtp", "") or ""
            if nxt == (cur or ""):
                raise PreventUpdate
            return nxt
        raise PreventUpdate

    @app.callback(
        Output("forensics-vtp-store", "data", allow_duplicate=True),
        Input("forensics-quadrant-chart", "clickData"),
        State("forensics-vtp-store", "data"),
        prevent_initial_call=True,
    )
    def _on_forensics_scatter_click(click_data: dict[str, Any] | None, cur: str) -> str:
        if not click_data or not click_data.get("points"):
            raise PreventUpdate
        pt = click_data["points"][0]
        cd = pt.get("customdata")
        vtp_id = cd[0] if isinstance(cd, list) and cd else (cd if isinstance(cd, str) else "")
        if not vtp_id or vtp_id == (cur or ""):
            raise PreventUpdate
        return str(vtp_id)

    # ------------------------------------------------------------------
    # 5. Main view router
    # ------------------------------------------------------------------
    @app.callback(
        Output("main-content", "children"),
        Input("active-tab-store", "data"),
        Input("date-start-input", "value"),
        Input("date-end-input", "value"),
        Input("timing-vtp-store", "data"),
        Input("comp-vtp-store", "data"),
        Input("comp-supplier-store", "data"),
        Input("audit-vtp-store", "data"),
        Input("audit-bmu-store", "data"),
        Input("forensics-vtp-store", "data"),
        Input("reload-tick-store", "data"),
    )
    def _render_main_content(
        active_tab: str,
        start_date: str | None,
        end_date: str | None,
        timing_vtp: str,
        comp_vtp: str,
        comp_supplier: str,
        audit_vtp: str,
        audit_bmu: str,
        forensics_vtp: str,
        _reload_tick: int,
    ) -> Any:
        trig = ctx.triggered_id
        # Avoid re-rendering an unrelated tab when a different tab's filter store updates
        tab_scoped_stores = {
            "timing-vtp-store": "timing",
            "comp-vtp-store": "compensation",
            "comp-supplier-store": "compensation",
            "audit-vtp-store": "baseline_audit",
            "audit-bmu-store": "baseline_audit",
            "forensics-vtp-store": "forensics",
        }
        if trig in tab_scoped_stores and tab_scoped_stores[trig] != active_tab:
            raise PreventUpdate

        return _render_view_safe(
            tab=active_tab or "overview",
            start_date=start_date,
            end_date=end_date,
            timing_vtp=timing_vtp or "",
            comp_vtp=comp_vtp or "",
            comp_supplier=comp_supplier or "",
            audit_vtp=audit_vtp or "",
            audit_bmu=audit_bmu or "",
            forensics_vtp=forensics_vtp or "",
        )

    # ------------------------------------------------------------------
    # 6. Explorer pagination & live results callbacks
    # ------------------------------------------------------------------
    @app.callback(
        Output("explorer-page-store", "data"),
        Input({"type": "explorer-page-btn", "dir": ALL}, "n_clicks"),
        Input("explorer-group-by", "value"),
        Input("explorer-vtp-input", "value"),
        Input("explorer-supplier-input", "value"),
        Input("explorer-gsp-select", "value"),
        Input("explorer-sp-select", "value"),
        Input("explorer-search-input", "value"),
        State("explorer-page-store", "data"),
        prevent_initial_call=True,
    )
    def _update_explorer_page(
        _page_clicks: list[int | None],
        _group_by: str | None,
        _vtp: str | None,
        _sup: str | None,
        _gsp: str | None,
        _sp: Any,
        _search: str | None,
        cur_page: int,
    ) -> int:
        trig = ctx.triggered_id
        if isinstance(trig, dict) and trig.get("type") == "explorer-page-btn":
            triggered = ctx.triggered[0] if ctx.triggered else {}
            if not triggered.get("value"):
                raise PreventUpdate
            direction = trig.get("dir")
            page = int(cur_page or 0)
            return max(0, page - 1) if direction == "prev" else page + 1
        return 0

    @app.callback(
        Output("explorer-results-container", "children"),
        Input("explorer-page-store", "data"),
        Input("explorer-group-by", "value"),
        Input("explorer-vtp-input", "value"),
        Input("explorer-supplier-input", "value"),
        Input("explorer-gsp-select", "value"),
        Input("explorer-sp-select", "value"),
        Input("explorer-search-input", "value"),
        Input("explorer-party-role-select", "value"),
        Input("explorer-party-search-input", "value"),
        Input("date-start-input", "value"),
        Input("date-end-input", "value"),
        Input("reload-tick-store", "data"),
    )
    def _render_explorer_results_cb(
        page: int,
        group_by: str | None,
        vtp: str | None,
        supplier: str | None,
        gsp: str | None,
        sp_val: Any,
        search: str | None,
        party_role: str | None,
        party_search: str | None,
        start_date: str | None,
        end_date: str | None,
        _reload_tick: int,
    ) -> Any:
        from .views.explorer import render_explorer_results

        gb = group_by if group_by in ("bmu_pair", "raw") else "bmu_pair"
        sp_int: int | None = None
        if sp_val not in (None, ""):
            try:
                sp_int = int(sp_val)
            except (TypeError, ValueError):
                sp_int = None

        page_num = max(0, int(page or 0))
        offset = page_num * EXPLORER_PAGE_SIZE
        data = da.get_explorer(
            start_date=start_date,
            end_date=end_date,
            group_by=gb,
            sec_party_id=(vtp or "").strip() or None,
            pri_party_id=(supplier or "").strip() or None,
            gsp_group=(gsp or "").strip() or None,
            sp=sp_int,
            search=(search or "").strip() or None,
            limit=EXPLORER_PAGE_SIZE,
            offset=offset,
        )
        parties_data = da.get_parties(
            role=(party_role or "").strip() or None,
            search=(party_search or "").strip() or None,
        )
        state = {
            "group_by": gb,
            "sec_party_id": (vtp or "").strip(),
            "pri_party_id": (supplier or "").strip(),
            "gsp_group": (gsp or "").strip(),
            "sp": sp_int,
            "search": (search or "").strip(),
            "page": page_num,
            "limit": EXPLORER_PAGE_SIZE,
            "party_role": (party_role or "").strip(),
            "party_search": (party_search or "").strip(),
        }
        return render_explorer_results(data, parties_data, state)

    # ------------------------------------------------------------------
    # 7. Download callbacks (Baseline Audit CSV, Policy Briefing MD, Explorer CSV)
    # ------------------------------------------------------------------
    @app.callback(
        Output("download-audit-csv", "data"),
        Input("audit-export-csv-btn", "n_clicks"),
        State("date-start-input", "value"),
        State("date-end-input", "value"),
        State("audit-vtp-store", "data"),
        State("audit-bmu-store", "data"),
        prevent_initial_call=True,
    )
    def _download_audit_csv(
        n_clicks: int | None,
        start_date: str | None,
        end_date: str | None,
        vtp: str | None,
        bmu: str | None,
    ) -> dict[str, Any]:
        if not n_clicks:
            raise PreventUpdate
        filename, content = da.export_baseline_audit_csv(
            start_date=start_date,
            end_date=end_date,
            sec_party_id=vtp or None,
            sec_bmu_id=bmu or None,
        )
        return dcc.send_string(content, filename)

    @app.callback(
        Output("download-audit-md", "data"),
        Input("audit-export-md-btn", "n_clicks"),
        State("date-start-input", "value"),
        State("date-end-input", "value"),
        State("audit-vtp-store", "data"),
        State("audit-bmu-store", "data"),
        prevent_initial_call=True,
    )
    def _download_audit_md(
        n_clicks: int | None,
        start_date: str | None,
        end_date: str | None,
        vtp: str | None,
        bmu: str | None,
    ) -> dict[str, Any]:
        if not n_clicks:
            raise PreventUpdate
        filename, content = da.export_baseline_briefing_md(
            start_date=start_date,
            end_date=end_date,
            sec_party_id=vtp or None,
            sec_bmu_id=bmu or None,
        )
        return dcc.send_string(content, filename)

    @app.callback(
        Output("download-explorer-csv", "data"),
        Input("explorer-export-csv-btn", "n_clicks"),
        State("date-start-input", "value"),
        State("date-end-input", "value"),
        State("explorer-group-by", "value"),
        State("explorer-vtp-input", "value"),
        State("explorer-supplier-input", "value"),
        State("explorer-gsp-select", "value"),
        State("explorer-sp-select", "value"),
        State("explorer-search-input", "value"),
        prevent_initial_call=True,
    )
    def _download_explorer_csv(
        n_clicks: int | None,
        start_date: str | None,
        end_date: str | None,
        group_by: str | None,
        vtp: str | None,
        supplier: str | None,
        gsp: str | None,
        sp_val: Any,
        search: str | None,
    ) -> dict[str, Any]:
        if not n_clicks:
            raise PreventUpdate
        sp_int: int | None = None
        if sp_val not in (None, ""):
            try:
                sp_int = int(sp_val)
            except (TypeError, ValueError):
                sp_int = None
        filename, content = da.export_explorer_csv(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by if group_by in ("bmu_pair", "raw") else "bmu_pair",
            sec_party_id=(vtp or "").strip() or None,
            pri_party_id=(supplier or "").strip() or None,
            gsp_group=(gsp or "").strip() or None,
            sp=sp_int,
            search=(search or "").strip() or None,
        )
        return dcc.send_string(content, filename)
