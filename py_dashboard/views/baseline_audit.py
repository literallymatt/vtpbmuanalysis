"""Baseline & BL01 (P376) Audit view for the Python Dash dashboard."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from dash import dcc, html

from py_dashboard.formatting import (
    PALETTE,
    PLOTLY_CONFIG,
    badge,
    empty_state,
    fmt_gbp,
    fmt_mwh,
    kpi_card,
    plotly_base_layout,
    section_card,
    short_date,
)


def _fmt_signed(val: Any, decimals: int = 2, suffix: str = "") -> str:
    if val is None:
        return "—"
    try:
        num = float(val)
        if num != num:
            return "—"
    except (TypeError, ValueError):
        return "—"
    sign = "+" if num > 0 else ""
    tail = f" {suffix}" if suffix else ""
    return f"{sign}{num:,.{decimals}f}{tail}"


def _fmt_opt_num(val: Any, decimals: int = 2, suffix: str = "") -> str:
    if val is None:
        return "—"
    try:
        num = float(val)
        if num != num:
            return "—"
    except (TypeError, ValueError):
        return "—"
    return f"{num:,.{decimals}f}{suffix}"


def _methodology_tone(cls: str) -> str:
    s = (cls or "").lower()
    if any(k in s for k in ("frozen", "sparse", "inflated", "sign-invert")):
        return "vermilion"
    if any(k in s for k in ("quantis", "self", "hybrid")):
        return "amber"
    if any(k in s for k in ("bl01", "p376")):
        return "indigo"
    if any(k in s for k in ("clean", "balanced", "standard")):
        return "teal"
    return "neutral"


def _hero_badge_cls(cls: str) -> str:
    tone = _methodology_tone(cls)
    return "hero-badge" if tone == "neutral" else f"hero-badge {tone}"


def _short_method_tag(cls: str) -> str:
    s = (cls or "").lower()
    if "bl01" in s and "frozen" in s:
        return "BL01 Frozen"
    if "bl01" in s:
        return "BL01"
    if "quantis" in s:
        return "Self-Nom 2dp"
    if "sparse" in s:
        return "Sparse SEV"
    if "self" in s:
        return "Self-Nom"
    if "hybrid" in s:
        return "Hybrid"
    if "sign-invert" in s:
        return "Sign-Inv"
    if "insufficient" in s:
        return "No SEV"
    return (cls or "")[:14]


def _build_sp_overlay_fig(detail: dict[str, Any]) -> go.Figure:
    rows = detail.get("sp_overlay") or []
    times = [r.get("time", "") for r in rows]
    sps = [r.get("sp", 0) for r in rows]
    baseline = [float(r.get("baseline_demand_mw", 0.0) or 0.0) for r in rows]
    actual = [float(r.get("actual_demand_mw", 0.0) or 0.0) for r in rows]
    turndown = [float(r.get("settled_turndown_mw", 0.0) or 0.0) for r in rows]
    rebound = [float(r.get("unsettled_rebound_mw", 0.0) or 0.0) for r in rows]
    act_rate = [float(r.get("activation_rate_pct", 0.0) or 0.0) for r in rows]
    sbp = [float(r.get("avg_sbp", 0.0) or 0.0) for r in rows]
    ssc = [float(r.get("avg_ssc", 0.0) or 0.0) for r in rows]

    custom = list(zip(sps, act_rate, sbp, ssc))

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=times,
            y=turndown,
            name="Settled turn-down (wmi > 0)",
            marker_color="rgba(11, 122, 117, 0.38)",
            customdata=custom,
            hovertemplate=(
                "<b>Settled turn-down:</b> %{y:.2f} MW"
                "<br>SP %{customdata[0]} · Active %{customdata[1]:.1f}%"
                " · SBP £%{customdata[2]:.1f} (SSC £%{customdata[3]:.1f})<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Bar(
            x=times,
            y=rebound,
            name="Unsettled rebound (wmi = 0)",
            marker_color="rgba(209, 67, 42, 0.42)",
            hovertemplate="<b>Unsettled rebound:</b> %{y:.2f} MW<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=baseline,
            mode="lines",
            name="Settlement baseline (sev)",
            line={"color": PALETTE["ink"], "width": 2.2, "dash": "dash"},
            hovertemplate="<b>Baseline (sev):</b> %{y:.2f} MW<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=actual,
            mode="lines",
            name="Actual metered demand (qm)",
            line={"color": PALETTE["indigo"], "width": 2.4},
            hovertemplate="<b>Actual demand (qm):</b> %{y:.2f} MW<extra></extra>",
        )
    )

    if "00:00" in times and "05:30" in times:
        fig.add_vrect(
            x0="00:00",
            x1="05:30",
            fillcolor="rgba(44, 92, 197, 0.075)",
            line_width=0,
            annotation_text="00:00–05:30 off-peak window",
            annotation_position="top left",
            annotation_font={"size": 10.5, "color": PALETTE["indigo"]},
        )

    fig.update_layout(
        **plotly_base_layout(
            height=355,
            barmode="group",
            xaxis={"tickangle": 0, "nticks": 13},
            yaxis={"title": "Average MW"},
        )
    )
    return fig


def _build_cherry_pick_fig(detail: dict[str, Any]) -> go.Figure:
    bins = detail.get("cherry_pick_hist") or []
    labels = [b.get("bin_label", "") for b in bins]
    active_pct = [float(b.get("active_pct", 0.0) or 0.0) for b in bins]
    inactive_pct = [float(b.get("inactive_pct", 0.0) or 0.0) for b in bins]
    active_cnt = [int(b.get("active_count", 0) or 0) for b in bins]
    inactive_cnt = [int(b.get("inactive_count", 0) or 0) for b in bins]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=active_pct,
            name="Active (wmi > 0)",
            marker_color=PALETTE["teal"],
            customdata=active_cnt,
            hovertemplate=(
                "<b>Active (wmi > 0):</b> %{y:.1f}% (%{customdata:,} SPs)<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Bar(
            x=labels,
            y=inactive_pct,
            name="Inactive (wmi = 0)",
            marker_color="rgba(209, 67, 42, 0.82)",
            customdata=inactive_cnt,
            hovertemplate=(
                "<b>Inactive (wmi = 0):</b> %{y:.1f}% (%{customdata:,} SPs)<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=290,
            barmode="group",
            margin={"l": 48, "r": 16, "t": 32, "b": 60},
            xaxis={"tickangle": -25, "tickfont": {"size": 10.5}},
            yaxis={"title": "Share of SPs (%)", "ticksuffix": "%"},
        )
    )
    return fig


def _build_ida_ramp_fig(detail: dict[str, Any]) -> go.Figure:
    ida = detail.get("ida_pre_ramp") or {}
    offsets = ida.get("pre_event_window_sp_offsets") or []
    labels = [pt.get("label", "") for pt in offsets]
    actual = [float(pt.get("avg_actual_mw", 0.0) or 0.0) for pt in offsets]
    baseline = [float(pt.get("avg_baseline_mw", 0.0) or 0.0) for pt in offsets]
    excess = [float(pt.get("excess_load_mw", 0.0) or 0.0) for pt in offsets]
    bar_colors = [
        "rgba(201, 122, 18, 0.58)" if e >= 0 else "rgba(11, 122, 117, 0.55)"
        for e in excess
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=excess,
            name="Excess load (actual − sev)",
            marker_color=bar_colors,
            hovertemplate="<b>Excess load:</b> %{y:+.2f} MW<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=actual,
            mode="lines+markers",
            name="Avg actual load (MW)",
            line={"color": PALETTE["indigo"], "width": 2.3},
            marker={"size": 6},
            hovertemplate="<b>Actual load:</b> %{y:.2f} MW<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=baseline,
            mode="lines+markers",
            name="Avg baseline sev (MW)",
            line={"color": PALETTE["ink"], "width": 2.0, "dash": "dash"},
            marker={"size": 5},
            hovertemplate="<b>Baseline sev:</b> %{y:.2f} MW<extra></extra>",
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=290,
            margin={"l": 48, "r": 16, "t": 32, "b": 44},
            yaxis={"title": "MW"},
        )
    )
    return fig


def _build_bl01_daily_fig(detail: dict[str, Any]) -> go.Figure:
    series = detail.get("bl01_daily_series") or []
    dates = [d.get("date", "") for d in series]
    short_labels = [short_date(d) for d in dates]
    actual = [float(d.get("actual_demand_mwh", 0.0) or 0.0) for d in series]
    sev = [float(d.get("settled_sev_mwh", 0.0) or 0.0) for d in series]
    bl01_raw = [d.get("bl01_raw_mwh") for d in series]
    bl01_excl = [d.get("bl01_excl_mwh") for d in series]
    custom = [
        (
            d.get("date", ""),
            d.get("dow", ""),
            int(d.get("active_sps", 0) or 0),
            float(d.get("settled_turndown_mwh", 0.0) or 0.0),
            float(d.get("unsettled_rebound_mwh", 0.0) or 0.0),
        )
        for d in series
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=short_labels,
            y=actual,
            mode="lines+markers",
            name="Actual demand (qm)",
            line={"color": PALETTE["indigo"], "width": 2.2},
            marker={"size": 4},
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[0]} (%{customdata[1]})</b> · %{customdata[2]}/48 active SPs"
                "<br>Actual demand (qm): %{y:.1f} MWh"
                "<br>Turn-down: %{customdata[3]:.1f} MWh · Rebound: %{customdata[4]:.1f} MWh"
                "<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=short_labels,
            y=sev,
            mode="lines+markers",
            name="Settled baseline (sev)",
            line={"color": PALETTE["ink"], "width": 2.4},
            marker={"size": 4},
            hovertemplate="<b>Settled sev:</b> %{y:.1f} MWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=short_labels,
            y=bl01_raw,
            mode="lines",
            name="BL01 raw (rolling 10WD/2of4WE)",
            line={"color": PALETTE["teal"], "width": 2.0, "dash": "dash"},
            connectgaps=True,
            hovertemplate="<b>BL01 raw:</b> %{y:.1f} MWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=short_labels,
            y=bl01_excl,
            mode="lines",
            name="BL01 excl. event days (P376)",
            line={"color": PALETTE["amber"], "width": 2.0, "dash": "dot"},
            connectgaps=True,
            hovertemplate="<b>BL01 excl. event days:</b> %{y:.1f} MWh<extra></extra>",
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=315,
            yaxis={"title": "Daily MWh"},
        )
    )
    return fig


def _build_price_regime_fig(detail: dict[str, Any]) -> go.Figure:
    regimes = detail.get("price_regimes") or []
    x = [r.get("regime", "") for r in regimes]
    td = [float(r.get("settled_turndown_mwh", 0.0) or 0.0) for r in regimes]
    tu = [float(r.get("settled_turnup_mwh", 0.0) or 0.0) for r in regimes]
    reb = [float(r.get("unsettled_rebound_mwh", 0.0) or 0.0) for r in regimes]
    custom = [
        (
            int(r.get("sps_count", 0) or 0),
            float(r.get("avg_sbp", 0.0) or 0.0),
            float(r.get("activation_rate_pct", 0.0) or 0.0),
        )
        for r in regimes
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=x,
            y=td,
            name="Settled turn-down",
            marker_color=PALETTE["teal"],
            customdata=custom,
            hovertemplate=(
                "<b>Settled turn-down:</b> %{y:.1f} MWh"
                "<br>%{customdata[0]:,} SPs · Avg SBP £%{customdata[1]:.1f}/MWh"
                " · Active %{customdata[2]:.1f}%<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Bar(
            x=x,
            y=tu,
            name="Settled turn-up",
            marker_color=PALETTE["indigo"],
            hovertemplate="<b>Settled turn-up:</b> %{y:.1f} MWh<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=x,
            y=reb,
            name="Unsettled rebound (wmi = 0)",
            marker_color=PALETTE["vermilion"],
            hovertemplate="<b>Unsettled rebound:</b> %{y:.1f} MWh<extra></extra>",
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=295,
            barmode="group",
            yaxis={"title": "Volume (MWh)"},
        )
    )
    return fig


def render_baseline_audit(
    data: dict[str, Any],
    selected_party_id: str = "",
    selected_bmu_id: str = "",
) -> html.Div:
    """Render the Baseline Accuracy & BL01 (P376) Audit view."""
    vtps: list[dict[str, Any]] = data.get("vtps") or []
    detail: dict[str, Any] | None = data.get("selected_detail")
    baseline_days = int(data.get("baseline_days") or 0)
    start_date = data.get("start_date") or ""
    end_date = data.get("end_date") or ""
    has_data = baseline_days > 0 and len(vtps) > 0 and detail is not None

    header = html.Div(
        [
            html.Div(
                [
                    html.H1(
                        "Baseline accuracy & BL01 (P376) audit",
                        className="page-title",
                    ),
                    html.P(
                        [
                            "Empirical audit of Secondary BMU (",
                            html.Span("V__*", className="mono"),
                            ") baselines as demand forecasts, examining how P376 BL01 lookback "
                            "rules and self-nominated ",
                            html.Span("sev", className="mono"),
                            " methodologies interact with P415 wholesale settlement under "
                            "BSC Issue 127 & P510.",
                        ],
                        className="page-lead",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Button(
                        "Download policy brief (.md)",
                        id="audit-export-md-btn",
                        n_clicks=0,
                        disabled=not has_data,
                        className="btn btn-sm btn-primary",
                    ),
                    html.Button(
                        "Export audit CSV",
                        id="audit-export-csv-btn",
                        n_clicks=0,
                        disabled=not has_data,
                        className="btn btn-sm",
                    ),
                ],
                className="header-actions",
            ),
        ],
        className="page-header",
    )

    if not has_data or detail is None:
        return html.Div(
            [
                header,
                empty_state(
                    "Fetch Secondary BMU baseline data to run the BL01 & SEV audit",
                    [
                        "No ",
                        html.Span("sbmu_baseline_sp", className="mono"),
                        f" records were found between {start_date} and {end_date}. "
                        "Fetch Elexon's ",
                        html.Span("bm-unit-level", className="mono"),
                        " SAA-I014 reports with the baseline option enabled to compare actual "
                        "metered demand (qm) against settlement baselines (sev) and wholesale "
                        "notifications (wmi).",
                    ],
                    action=html.Div(
                        [
                            html.Button(
                                "Fetch Elexon baselines",
                                id={"type": "open-sync-btn", "idx": "audit-empty"},
                                n_clicks=0,
                                className="btn btn-teal",
                            ),
                            html.Span(
                                "CLI: python -m backend.ingest --baselines",
                                className="mono",
                                style={
                                    "fontSize": "12px",
                                    "color": PALETTE["ink_muted"],
                                    "marginLeft": "10px",
                                },
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "flexWrap": "wrap", "gap": "8px"},
                    ),
                ),
            ]
        )

    active_party_id = detail.get("party_id") or selected_party_id or vtps[0]["party_id"]
    active_bmu_id = detail.get("sec_bmu_id") or selected_bmu_id or ""
    selected_vtp = next((v for v in vtps if v["party_id"] == active_party_id), vtps[0])

    # Market-weighted asymmetric selection gap across audited VTPs
    total_weight = sum(max(0.0, float(v.get("settled_turndown_mwh") or 0.0)) for v in vtps)
    active_pos = 0.0
    inactive_pos = 0.0
    total_sbmus = 0
    for v in vtps:
        total_sbmus += int(v.get("sbmu_count") or 0)
        w = (
            max(0.0, float(v.get("settled_turndown_mwh") or 0.0)) / total_weight
            if total_weight > 0
            else 1.0 / len(vtps)
        )
        active_pos += float(v.get("active_positive_pct") or 0.0) * w
        inactive_pos += float(v.get("inactive_positive_pct") or 0.0) * w
    gap_pp = active_pos - inactive_pos

    ms = data.get("market_summary") or {}
    total_td = float(ms.get("total_settled_turndown_mwh") or 0.0)
    total_reb = float(ms.get("total_unsettled_rebound_mwh") or 0.0)
    leakage_pct = float(ms.get("rebound_leakage_pct") or 0.0)
    implied_comp = float(ms.get("implied_unsettled_comp_gbp") or 0.0)
    counter_econ = float(ms.get("counter_economic_turndown_mwh") or 0.0)
    counter_econ_pct = (counter_econ / total_td * 100.0) if total_td > 0 else 0.0
    bl01_cnt = int(ms.get("bl01_vtps_count") or 0)
    self_cnt = int(ms.get("self_nom_vtps_count") or 0)
    other_cnt = max(0, len(vtps) - bl01_cnt - self_cnt)

    # Concise pill switcher
    switcher_vtps = [
        v
        for v in vtps
        if v.get("methodology_class") != "Insufficient Baseline Data"
        or v["party_id"] == active_party_id
    ] or vtps

    # Dropdown options
    vtp_options = [
        {
            "label": f"{v['company_name']} ({v['party_id']}) — {_short_method_tag(v.get('methodology_class', ''))}",
            "value": v["party_id"],
        }
        for v in vtps
    ]
    bmu_options = [
        {
            "label": f"All SBMUs for {selected_vtp['company_name']} ({len(selected_vtp.get('sbmus') or [])})",
            "value": "",
        }
    ] + [
        {
            "label": (
                f"{b['sec_bmu_id']} ({b.get('gsp_group') or 'GB'}) — "
                f"{float(b.get('settled_turndown_mwh') or 0):,.0f} MWh"
            ),
            "value": b["sec_bmu_id"],
        }
        for b in (selected_vtp.get("sbmus") or [])
    ]

    dm = detail.get("metrics") or {}
    ida = detail.get("ida_pre_ramp") or {}
    ida_transitions = int(ida.get("transitions_count") or 0)
    ida_excess = float(ida.get("pre_ramp_excess_mw") or 0.0)

    # Methodology & sign-convention guide (native collapsible <details>)
    guide_box = html.Details(
        [
            html.Summary(
                "Audit methodology & SAA-I014 sign convention (Ofgem / Issue 127 & P510)",
                className="guide-toggle",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong("SAA-I014 Sign Convention & Implied Deviation"),
                            "In Elexon bm-unit-level files, demand is recorded as negative MWh "
                            "(e.g. qm = −6.72, sev = −7.88). Implied deviation is qm − sev: "
                            "positive values indicate actual demand fell below baseline "
                            "(turn-down); negative values indicate actual demand exceeded baseline "
                            "(rebound or load surge). Intraday MW charts plot positive demand "
                            "magnitudes (−qm × 2 and −sev × 2).",
                        ]
                    ),
                    html.Div(
                        [
                            html.Strong("Active (wmi > 0) vs Non-Active (wmi = 0) Baselines"),
                            "Non-active settlement periods (wmi = 0) provide a clean out-of-sample "
                            "test of how well sev forecasts metered load when no wholesale "
                            "activation is notified. High non-active MAE/bias indicates baseline "
                            "forecast error, while large negative deviations during wmi = 0 "
                            "quantify unsettled rebound.",
                        ]
                    ),
                    html.Div(
                        [
                            html.Strong("BL01 (P376) vs Self-Nominated SEV Classification"),
                            "Independently reconstructs the P376 BL01 rolling 10-working-day / "
                            "middle-2-of-4 weekend baseline (raw and excluding Event Days) and "
                            "tests fit (R²), drift, 2-decimal-place quantisation, and sev coverage "
                            "to distinguish BL01-consistent units from self-nominated counterfactuals.",
                        ]
                    ),
                ],
                className="guide-grid",
            ),
        ],
        className="guide-box",
    )

    # Verdict banner + 5-cell market ledger
    verdict = html.Section(
        [
            html.H2(ms.get("headline") or "Baseline audit summary"),
            html.P(
                [
                    "Across ",
                    html.Strong(f"{baseline_days} baseline days"),
                    " (",
                    html.Span(start_date, className="mono"),
                    " to ",
                    html.Span(end_date, className="mono"),
                    "), audited Secondary BMUs settled ",
                    html.Strong(fmt_mwh(total_td, 0)),
                    " of wholesale turn-down while recording ",
                    html.Strong(fmt_mwh(total_reb, 0)),
                    f" ({leakage_pct:.1f}%) of un-notified rebound where actual demand exceeded "
                    "baseline without wholesale settlement (",
                    html.Span("wmi = 0", className="mono"),
                    "), representing ",
                    html.Strong(fmt_gbp(implied_comp, compact=True)),
                    " in implied unsettled compensation offset.",
                ]
            ),
        ],
        className="verdict-banner",
    )

    market_strip = html.Section(
        [
            kpi_card(
                "Non-active forecast MAE & bias",
                _fmt_opt_num(ms.get("non_active_mae_mwh"), 2, " MWh"),
                f"Mean bias {_fmt_signed(ms.get('non_active_bias_mwh'), 2, 'MWh/SP')} when wmi = 0",
            ),
            kpi_card(
                "Un-notified rebound MWh & £",
                fmt_mwh(total_reb, 0),
                f"{leakage_pct:.1f}% of turn-down · {fmt_gbp(implied_comp, compact=True)} implied SSC",
                tone="vermilion" if leakage_pct >= 25 else "amber",
            ),
            kpi_card(
                "Asymmetric selection gap",
                _fmt_signed(gap_pp, 1, "pp"),
                f"{active_pos:.1f}% pos. active vs {inactive_pos:.1f}% inactive",
                tone="vermilion" if gap_pp >= 25 else "teal",
            ),
            kpi_card(
                "BL01 vs Self-nominated split",
                f"{bl01_cnt} BL01 · {self_cnt} Self",
                f"{len(vtps)} VTPs ({other_cnt} other) across {total_sbmus} V__* SBMUs",
                tone="indigo",
            ),
            kpi_card(
                "Counter-economic turn-down",
                fmt_mwh(counter_econ, 0),
                f"{counter_econ_pct:.1f}% of settled turn-down while SBP < SSC",
                tone="vermilion" if counter_econ_pct >= 40 else "amber",
            ),
        ],
        className="ledger-strip",
    )

    # Interactive VTP pills + VTP/SBMU dropdowns
    controls = html.Div(
        [
            html.Div(
                [
                    html.Span("Audit VTP:", className="vtp-switcher-label"),
                    *[
                        html.Button(
                            [
                                html.Span(v["company_name"]),
                                html.Span(
                                    _short_method_tag(v.get("methodology_class", "")),
                                    className="vtp-pill-share",
                                ),
                            ],
                            id={
                                "type": "audit-pick-vtp",
                                "vtp": v["party_id"],
                                "idx": f"pill-{v['party_id']}",
                            },
                            n_clicks=0,
                            className=(
                                "vtp-pill active"
                                if v["party_id"] == active_party_id
                                else "vtp-pill"
                            ),
                        )
                        for v in switcher_vtps
                    ],
                ],
                className="vtp-switcher",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("VTP portfolio:", htmlFor="audit-vtp-select"),
                            dcc.Dropdown(
                                id="audit-vtp-select",
                                options=vtp_options,
                                value=active_party_id,
                                clearable=False,
                                style={"minWidth": "270px"},
                            ),
                        ],
                        className="sbmu-select-wrap",
                    ),
                    html.Div(
                        [
                            html.Label("Secondary BMU:", htmlFor="audit-bmu-select"),
                            dcc.Dropdown(
                                id="audit-bmu-select",
                                options=bmu_options,
                                value=active_bmu_id,
                                clearable=False,
                                style={"minWidth": "290px"},
                            ),
                        ],
                        className="sbmu-select-wrap",
                    ),
                ],
                className="filter-bar",
            ),
        ],
        className="audit-controls-row",
    )

    # Selected VTP / SBMU hero band
    detail_sub = (
        f"Individual Secondary BMU drill-down · Settled turn-down "
        f"{fmt_mwh(dm.get('settled_turndown_mwh'), 1)} · Unsettled rebound "
        f"{fmt_mwh(dm.get('unsettled_rebound_mwh'), 1)} "
        f"({float(dm.get('rebound_leakage_pct') or 0):.1f}%)"
        if detail.get("sec_bmu_id")
        else (
            f"Portfolio aggregate across "
            f"{selected_vtp.get('sbmu_count', dm.get('sbmu_count', 0))} Secondary BMUs "
            f"({selected_vtp.get('active_days', dm.get('active_days', 0))} active days) · "
            f"Settled turn-down {fmt_mwh(dm.get('settled_turndown_mwh'), 1)} · "
            f"Unsettled rebound {fmt_mwh(dm.get('unsettled_rebound_mwh'), 1)} "
            f"({float(dm.get('rebound_leakage_pct') or 0):.1f}%)"
        )
    )

    hero_badges = [
        html.Span(
            detail.get("methodology_class", ""),
            className=_hero_badge_cls(detail.get("methodology_class", "")),
        ),
        *[
            html.Span(
                r,
                className=f"hero-badge {'teal' if r in ('AV', 'VT') else ''}".strip(),
            )
            for r in (selected_vtp.get("roles") or [])
        ],
        html.Span(f"BL01 R² {_fmt_opt_num(dm.get('bl01_r2'), 2)}", className="hero-badge"),
        html.Span(
            f"SEV cov {_fmt_opt_num(dm.get('sev_coverage_pct'), 0, '%')}",
            className="hero-badge",
        ),
    ]

    reasons = detail.get("methodology_reasons") or []
    dossier_hero = html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3(
                                [
                                    detail.get("company_name", active_party_id),
                                    " ",
                                    html.Span(
                                        (
                                            f"{detail['sec_bmu_id']} · {detail['party_id']}"
                                            if detail.get("sec_bmu_id")
                                            else detail.get("party_id", "")
                                        ),
                                        className="mono",
                                        style={
                                            "fontSize": "15px",
                                            "color": "#8ba0b7",
                                            "fontWeight": 500,
                                        },
                                    ),
                                ],
                                className="dossier-hero-name",
                            ),
                            html.P(detail_sub, className="dossier-hero-sub"),
                        ]
                    ),
                    html.Div(
                        hero_badges,
                        style={
                            "display": "flex",
                            "gap": "6px",
                            "flexWrap": "wrap",
                            "alignItems": "center",
                        },
                    ),
                ],
                className="dossier-hero-top",
            ),
            *(
                [
                    html.Ul(
                        [html.Li(r) for r in reasons],
                        className="dossier-hero-findings",
                    )
                ]
                if reasons
                else []
            ),
        ],
        className="dossier-hero",
    )

    over_rate = float(dm.get("over_forecast_rate_pct") or 0.0)
    quant_pct = float(dm.get("quantised_2dp_pct") or 0.0)
    sev_cov = float(dm.get("sev_coverage_pct") or 0.0)

    scoped_strip = html.Section(
        [
            kpi_card(
                "Non-active MAE / RMSE",
                _fmt_opt_num(dm.get("non_active_mae_mwh"), 3, " MWh"),
                f"RMSE {_fmt_opt_num(dm.get('non_active_rmse_mwh'), 3, ' MWh')} · "
                f"MAPE {_fmt_opt_num(dm.get('non_active_mape_pct'), 1, '%')}",
            ),
            kpi_card(
                "Over-forecast rate & bias",
                _fmt_opt_num(over_rate, 1, "%"),
                f"Mean non-active bias {_fmt_signed(dm.get('non_active_bias_mwh'), 3, 'MWh')}",
                tone="amber" if (over_rate >= 62 or over_rate <= 38) else "teal",
            ),
            kpi_card(
                "BL01 fit (R²) & lookback drift",
                _fmt_opt_num(dm.get("bl01_r2"), 3),
                f"BL01 MAE {_fmt_opt_num(dm.get('bl01_mae_mwh'), 3, ' MWh')} · "
                f"Drift {_fmt_signed(dm.get('bl01_drift_mwh'), 3, 'MWh')}",
                tone="indigo",
            ),
            kpi_card(
                "SEV quantisation & coverage",
                f"{_fmt_opt_num(quant_pct, 1, '%')} 2 d.p.",
                f"SEV coverage {_fmt_opt_num(sev_cov, 1, '%')} · Unsettled comp "
                f"{fmt_gbp(dm.get('implied_unsettled_comp_gbp'), compact=True)}",
                tone="vermilion" if (quant_pct >= 70 or sev_cov < 75) else None,
            ),
        ],
        className="ledger-strip",
    )

    # Centerpiece 48-SP overlay chart
    sp_overlay_card = section_card(
        "Actual metered demand (qm) vs settlement baseline (sev) across SP 1–48 (MW)",
        [
            dcc.Graph(
                figure=_build_sp_overlay_fig(detail),
                config=PLOTLY_CONFIG,
            ),
            html.Div(
                [
                    html.Span(
                        "Where baseline (sev) sits above actual load (qm) during active SPs, "
                        "turn-down is settled. Where actual load spikes above baseline during "
                        "wmi = 0, recharge rebound is absorbed outside wholesale settlement."
                    ),
                    html.Span(
                        f"48 settlement periods · {baseline_days}d avg",
                        className="mono",
                    ),
                ],
                className="chart-footnote",
            ),
        ],
        subtitle=(
            f"{detail.get('sec_bmu_id') or detail.get('company_name')} — demand magnitudes "
            "plotted as positive MW (−qm × 2 vs −sev × 2), exposing settled daytime turn-down "
            "against un-notified overnight recharge rebound."
        ),
        actions=[
            badge(f"Settled turn-down {fmt_mwh(dm.get('settled_turndown_mwh'), 0)}", "teal"),
            badge(f"Unsettled rebound {fmt_mwh(dm.get('unsettled_rebound_mwh'), 0)}", "vermilion"),
        ],
    )

    # Split 2-column charts: Cherry-picking histogram & IDA pre-event ramp
    cherry_bins = detail.get("cherry_pick_hist") or []
    cherry_card = section_card(
        "Asymmetric free-option selection (qm − sev distribution)",
        [
            (
                dcc.Graph(figure=_build_cherry_pick_fig(detail), config=PLOTLY_CONFIG)
                if cherry_bins
                else html.Div(
                    "Insufficient active/inactive observations to construct deviation histogram.",
                    className="loading-state",
                )
            ),
            html.Div(
                [
                    html.Span(
                        f"Active: {float(dm.get('active_positive_pct') or 0):.1f}% positive "
                        f"(mean {_fmt_signed(dm.get('active_mean_dev_mwh'), 3, 'MWh')})"
                    ),
                    html.Span(
                        f"Inactive: {float(dm.get('inactive_positive_pct') or 0):.1f}% positive "
                        f"(mean {_fmt_signed(dm.get('inactive_mean_dev_mwh'), 3, 'MWh')})"
                    ),
                ],
                className="chart-footnote",
            ),
        ],
        subtitle="Share of SPs by qm − sev bin: Active (wmi > 0) vs Inactive (wmi = 0)",
    )

    ida_offsets = ida.get("pre_event_window_sp_offsets") or []
    ida_card = section_card(
        "BL01 In-Day Adjustment (IDA) pre-event ramp check",
        [
            (
                dcc.Graph(figure=_build_ida_ramp_fig(detail), config=PLOTLY_CONFIG)
                if (ida_transitions > 0 and ida_offsets)
                else html.Div(
                    "No discrete wmi: 0 → >0 activation starts observed for this selection "
                    "(either continuously active across all periods or inactive during the window).",
                    className="loading-state",
                )
            ),
            html.Div(
                [
                    html.Span(
                        "Positive amber bars indicate actual demand exceeded baseline "
                        "immediately prior to activation start."
                    ),
                    html.Span(
                        f"Mean pre-ramp: {_fmt_signed(ida_excess, 2, 'MW')}",
                        className="mono",
                    ),
                ],
                className="chart-footnote",
            ),
        ],
        subtitle="Offsets −6 to −1 SPs prior to wmi: 0 → >0 activation start",
        actions=badge(
            f"{ida_transitions} starts · {_fmt_signed(ida_excess, 2, 'MW')}",
            "amber" if ida_excess > 0.2 else "neutral",
        ),
    )

    # BL01 Daily trajectory
    bl01_daily_card = section_card(
        "BL01 (P376) reconstruction vs settled baseline (sev) — daily trajectory",
        [
            dcc.Graph(figure=_build_bl01_daily_fig(detail), config=PLOTLY_CONFIG),
            html.Div(
                [
                    html.Span(
                        "Early dates serve as the lookback warmup for BL01 rolling averages; "
                        "divergence between settled sev and BL01 raw exposes Event-Day freeze "
                        "or non-BL01 self-nomination."
                    ),
                    html.Span(
                        f"{len(detail.get('bl01_daily_series') or [])} settlement days",
                        className="mono",
                    ),
                ],
                className="chart-footnote",
            ),
        ],
        subtitle=(
            f"Daily metered demand vs settled sev and reconstructed BL01 lookback curves "
            f"across the {baseline_days}-day audit window."
        ),
        actions=[
            badge(f"BL01 R² {_fmt_opt_num(dm.get('bl01_r2'), 3)}", "indigo"),
            badge(f"MAE {_fmt_opt_num(dm.get('bl01_mae_mwh'), 2, ' MWh')}", "neutral"),
            badge(f"Drift {_fmt_signed(dm.get('bl01_drift_mwh'), 2, 'MWh')}", "amber"),
        ],
    )

    # Price regime dispatch chart
    price_regime_card = section_card(
        "Dispatch vs wholesale price regime (System Buy Price buckets)",
        dcc.Graph(figure=_build_price_regime_fig(detail), config=PLOTLY_CONFIG),
        subtitle=(
            "Compares settled turn-down, settled turn-up, and un-notified rebound across "
            f"five SBP price regimes for {detail.get('sec_bmu_id') or detail.get('company_name')}."
        ),
    )

    # Per-VTP audit table + selected VTP's SBMU drill-down rows
    vtp_table_rows: list[Any] = []
    for v in vtps:
        pid = v["party_id"]
        is_sel = pid == active_party_id and not active_bmu_id
        reb_mwh = float(v.get("unsettled_rebound_mwh") or 0.0)
        vtp_table_rows.append(
            html.Tr(
                [
                    html.Td(
                        html.Button(
                            [
                                html.Div(v["company_name"], style={"fontWeight": 600, "textAlign": "left"}),
                                html.Div(
                                    f"{pid} · {v.get('active_days', 0)}d active",
                                    className="mono",
                                    style={"fontSize": "11px", "color": PALETTE["ink_muted"], "textAlign": "left"},
                                ),
                            ],
                            id={"type": "audit-pick-vtp", "vtp": pid, "idx": f"tbl-{pid}"},
                            n_clicks=0,
                            className="table-link-btn",
                        )
                    ),
                    html.Td(
                        badge(
                            v.get("methodology_class", ""),
                            _methodology_tone(v.get("methodology_class", "")),
                        )
                    ),
                    html.Td(str(v.get("sbmu_count", 0)), className="num"),
                    html.Td(
                        fmt_mwh(v.get("settled_turndown_mwh"), 1),
                        className="num",
                        style={"fontWeight": 600},
                    ),
                    html.Td(
                        fmt_mwh(reb_mwh, 1),
                        className="num",
                        style={
                            "color": PALETTE["vermilion"] if reb_mwh > 0 else PALETTE["ink"],
                            "fontWeight": 600 if reb_mwh > 0 else 400,
                        },
                    ),
                    html.Td(
                        f"{float(v.get('rebound_leakage_pct') or 0):.1f}%",
                        className="num",
                    ),
                    html.Td(_fmt_opt_num(v.get("non_active_mae_mwh"), 3), className="num"),
                    html.Td(_fmt_opt_num(v.get("bl01_r2"), 2), className="num"),
                    html.Td(
                        f"{float(v.get('quantised_2dp_pct') or 0):.0f}%",
                        className="num",
                    ),
                    html.Td(
                        f"{float(v.get('sev_coverage_pct') or 0):.0f}%",
                        className="num",
                    ),
                ],
                className="selected" if is_sel else "",
            )
        )

    vtp_table_card = section_card(
        "VTP baseline methodology classification",
        html.Div(
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("VTP"),
                                html.Th("Methodology class"),
                                html.Th("SBMUs", className="num"),
                                html.Th("Settled turn-down", className="num"),
                                html.Th("Unsettled rebound", className="num"),
                                html.Th("Leakage %", className="num"),
                                html.Th("Non-active MAE", className="num"),
                                html.Th("BL01 R²", className="num"),
                                html.Th("2 d.p. SEV", className="num"),
                                html.Th("SEV cov.", className="num"),
                            ]
                        )
                    ),
                    html.Tbody(vtp_table_rows),
                ],
                className="data-table",
            ),
            className="table-scroll",
        ),
        subtitle="Click any VTP to load its portfolio baseline audit and Secondary BMUs below.",
    )

    # Per-SBMU drill-down table for the selected VTP
    sbmus = selected_vtp.get("sbmus") or []
    sbmu_rows: list[Any] = []
    for b in sbmus:
        bmu_id = b["sec_bmu_id"]
        td_b = float(b.get("settled_turndown_mwh") or 0.0)
        reb_b = float(b.get("unsettled_rebound_mwh") or 0.0)
        leak_b = (reb_b / td_b * 100.0) if td_b > 0 else 0.0
        is_bmu_sel = bmu_id == active_bmu_id
        sbmu_rows.append(
            html.Tr(
                [
                    html.Td(
                        html.Button(
                            bmu_id,
                            id={
                                "type": "audit-pick-bmu",
                                "vtp": selected_vtp["party_id"],
                                "bmu": bmu_id,
                                "idx": f"sbmu-{bmu_id}",
                            },
                            n_clicks=0,
                            className="table-link-btn mono",
                            style={"fontWeight": 600, "fontSize": "12px"},
                        )
                    ),
                    html.Td(
                        badge(
                            b.get("methodology_class", ""),
                            _methodology_tone(b.get("methodology_class", "")),
                        )
                    ),
                    html.Td(b.get("gsp_group") or "—", className="num mono"),
                    html.Td(fmt_mwh(td_b, 1), className="num"),
                    html.Td(
                        fmt_mwh(reb_b, 1),
                        className="num",
                        style={"color": PALETTE["vermilion"] if reb_b > 0 else PALETTE["ink"]},
                    ),
                    html.Td(f"{leak_b:.1f}%", className="num"),
                    html.Td(_fmt_opt_num(b.get("non_active_mae_mwh"), 3), className="num"),
                    html.Td(_fmt_opt_num(b.get("bl01_r2"), 2), className="num"),
                    html.Td(f"{float(b.get('quantised_2dp_pct') or 0):.0f}%", className="num"),
                    html.Td(f"{float(b.get('sev_coverage_pct') or 0):.0f}%", className="num"),
                ],
                className="selected" if is_bmu_sel else "",
            )
        )

    sbmu_table_card = section_card(
        f"Secondary BMU (V__*) breakdown — {selected_vtp['company_name']} ({len(sbmus)} units)",
        (
            html.Div(
                html.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Secondary BMU"),
                                    html.Th("Methodology class"),
                                    html.Th("GSP", className="num"),
                                    html.Th("Settled turn-down", className="num"),
                                    html.Th("Unsettled rebound", className="num"),
                                    html.Th("Leakage %", className="num"),
                                    html.Th("Non-active MAE", className="num"),
                                    html.Th("BL01 R²", className="num"),
                                    html.Th("2 d.p. SEV", className="num"),
                                    html.Th("SEV cov.", className="num"),
                                ]
                            )
                        ),
                        html.Tbody(sbmu_rows),
                    ],
                    className="data-table",
                ),
                className="table-scroll",
                style={"maxHeight": "380px"},
            )
            if sbmu_rows
            else html.Div("No Secondary BMUs recorded for this VTP.", className="loading-state")
        ),
        subtitle="Click any Secondary BMU to inspect its individual SP overlay, histogram, BL01 curve, and price-regime dispatch.",
        actions=(
            html.Button(
                "Reset to full VTP portfolio",
                id={
                    "type": "audit-pick-vtp",
                    "vtp": selected_vtp["party_id"],
                    "idx": "reset-portfolio",
                },
                n_clicks=0,
                className="btn btn-sm",
            )
            if active_bmu_id
            else None
        ),
    )

    # Policy implications footer
    policy_card = section_card(
        "Policy implications — P376 (BL01), BSC Issue 127 & P510",
        html.Div(
            [
                html.Div(
                    [
                        html.Strong("1. P376 (BL01) Event-Day Freeze & IDA Calibration"),
                        "Historical 10-working-day lookbacks that exclude Event Days can lock in "
                        "obsolete high-demand profiles when assets activate daily, causing settled "
                        "baselines to drift above underlying demand. Additive In-Day Adjustments "
                        "reward elevated pre-event demand in the T−6 to T−1 window unless bounded "
                        "or replaced by symmetric counterfactual validation.",
                    ]
                ),
                html.Div(
                    [
                        html.Strong("2. BSC Issue 127 — Mandatory Register & Symmetric Rebound"),
                        "Without a public register disclosing which Secondary BMUs use BL01 versus "
                        "self-nominated sev—and without symmetric two-way settlement of post-event "
                        "load rebound—VTPs hold a structural free option: positive baseline "
                        "deviations (qm > sev) are notified for wholesale value, while negative "
                        "recharge deviations (qm < sev) remain unsettled.",
                    ]
                ),
                html.Div(
                    [
                        html.Strong("3. P510 — Supplier Compensation & Price Discipline"),
                        "Mutualising Supplier Sourcing Cost (SSC) across all suppliers insulates "
                        "VTPs from the underlying retail procurement cost of shifted energy. "
                        "Positive turn-down continues to be notified even when System Buy Price is "
                        "below SSC or negative, converting baseline forecast error into deadweight "
                        "consumer transfers unless compensation reflects real wholesale scarcity.",
                    ]
                ),
            ],
            className="guide-grid no-border",
        ),
        subtitle="Structural incentive distortions evidenced directly in public SAA-I014 baseline and metering settlement records",
    )

    return html.Div(
        [
            header,
            guide_box,
            verdict,
            market_strip,
            controls,
            dossier_hero,
            scoped_strip,
            sp_overlay_card,
            html.Div([cherry_card, ida_card], className="grid-2"),
            bl01_daily_card,
            price_regime_card,
            vtp_table_card,
            sbmu_table_card,
            policy_card,
        ]
    )
