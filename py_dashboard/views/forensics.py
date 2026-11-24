"""EV Charger Footprint & Baselining Forensics Lab view for the Python Dash dashboard."""

from __future__ import annotations

import math
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
    risk_tone,
    section_card,
)


def _score_color(score: float) -> str:
    if score >= 65:
        return PALETTE["vermilion"]
    if score >= 45:
        return PALETTE["amber"]
    return PALETTE["teal"]


def _build_quadrant_fig(
    vtps: list[dict[str, Any]],
    selected_id: str,
) -> go.Figure:
    xs = [float(v.get("ev_focus_score") or 0.0) for v in vtps]
    ys = [float(v.get("baselining_risk_score") or 0.0) for v in vtps]
    comps = [abs(float(v.get("comp_gbp") or 0.0)) for v in vtps]
    max_comp = max(comps) if comps else 1.0
    sizes = [
        max(12.0, min(46.0, 12.0 + 34.0 * math.sqrt(c / max(max_comp, 1.0))))
        for c in comps
    ]
    colors = [_score_color(y) for y in ys]
    line_colors = [
        PALETTE["ink"] if v["party_id"] == selected_id else "#ffffff" for v in vtps
    ]
    line_widths = [2.6 if v["party_id"] == selected_id else 1.2 for v in vtps]
    opacities = [0.95 if v["party_id"] == selected_id else 0.72 for v in vtps]
    custom_ids = [v["party_id"] for v in vtps]
    labels = [
        v["company_name"].split(" ")[0] if (c >= max_comp * 0.04 or v["party_id"] == selected_id) else ""
        for v, c in zip(vtps, comps)
    ]
    hovers = [
        (
            f"<b>{v['company_name']} ({v['party_id']})</b>"
            f"<br>{v.get('archetype', '')}"
            f"<br>EV focus: {float(v.get('ev_focus_score') or 0):.0f}/100"
            f" · Risk: {float(v.get('baselining_risk_score') or 0):.0f}/100"
            f"<br>Compensation: {fmt_gbp(v.get('comp_gbp'))}"
            f"<br><i>Click bubble to inspect dossier</i>"
        )
        for v in vtps
    ]

    fig = go.Figure()
    fig.add_shape(
        type="rect",
        x0=65,
        x1=100,
        y0=65,
        y1=100,
        fillcolor="rgba(209, 67, 42, 0.07)",
        line_width=0,
        layer="below",
    )
    fig.add_shape(
        type="rect",
        x0=0,
        x1=65,
        y0=0,
        y1=65,
        fillcolor="rgba(11, 122, 117, 0.03)",
        line_width=0,
        layer="below",
    )
    fig.add_vline(x=65, line_dash="dash", line_color=PALETTE["border_strong"], line_width=1)
    fig.add_hline(y=65, line_dash="dash", line_color=PALETTE["border_strong"], line_width=1)

    fig.add_annotation(
        x=98,
        y=97,
        text="EV + High baselining risk",
        showarrow=False,
        xanchor="right",
        yanchor="top",
        font={"size": 10.5, "color": PALETTE["vermilion"]},
    )
    fig.add_annotation(
        x=2,
        y=3,
        text="Commercial / BESS lower risk",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font={"size": 10.5, "color": PALETTE["ink_muted"]},
    )

    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers+text",
            text=labels,
            textposition="top center",
            textfont={"size": 10.5, "color": PALETTE["ink_secondary"]},
            customdata=custom_ids,
            hovertext=hovers,
            hovertemplate="%{hovertext}<extra></extra>",
            marker={
                "size": sizes,
                "color": colors,
                "opacity": opacities,
                "line": {"color": line_colors, "width": line_widths},
            },
            showlegend=False,
        )
    )

    fig.update_layout(
        **plotly_base_layout(
            height=355,
            hovermode="closest",
            margin={"l": 54, "r": 20, "t": 20, "b": 48},
            xaxis={
                "title": "EV charger footprint score (0–100)",
                "range": [0, 102],
                "showgrid": True,
                "gridcolor": PALETTE["grid"],
            },
            yaxis={
                "title": "Baselining risk score (0–100)",
                "range": [0, 102],
            },
        )
    )
    return fig


def _build_boundary_curves_fig(selected: dict[str, Any]) -> go.Figure:
    ta = selected.get("tariff_analysis") or {}
    curves = ta.get("boundary_curves") or []
    times = [c.get("time", "") for c in curves]

    series_spec = [
        ("MERCURY", "Octopus (IOG/Go 23:30–05:30)", PALETTE["indigo"], "solid", 2.2),
        ("NITTWO01", "E.ON Next (Drive 00:00–06:00)", PALETTE["vermilion"], "solid", 2.2),
        ("BRITGAS", "British Gas (ED 00:00–05:00)", PALETTE["teal"], "solid", 2.2),
        ("LENCO", "EDF (GoElectric 23:00–06:00)", PALETTE["amber"], "dash", 1.8),
    ]

    fig = go.Figure()
    for key, label, color, dash, width in series_spec:
        vals = [float(c.get(key) or 0.0) for c in curves]
        fig.add_trace(
            go.Scatter(
                x=times,
                y=vals,
                mode="lines+markers",
                name=label,
                line={"color": color, "width": width, "dash": dash},
                marker={"size": 4},
                hovertemplate=f"<b>{label}:</b> %{{y:.1f}}% of peak SP<extra></extra>",
            )
        )

    ref_lines = [
        ("23:00", "EDF 23:00", PALETTE["amber"], "top"),
        ("23:30", "Oct 23:30", PALETTE["indigo"], "bottom"),
        ("00:00", "E.ON 00:00", PALETTE["vermilion"], "top"),
        ("05:00", "BG 05:00", PALETTE["teal"], "top"),
        ("05:30", "Oct 05:30", PALETTE["indigo"], "bottom"),
        ("06:00", "E.ON 06:00", PALETTE["vermilion"], "top"),
    ]
    for t_mark, label, color, pos in ref_lines:
        if t_mark in times:
            fig.add_shape(
                type="line",
                x0=t_mark,
                x1=t_mark,
                y0=0,
                y1=1,
                yref="paper",
                line={"color": color, "width": 1.2, "dash": "dot"},
            )
            fig.add_annotation(
                x=t_mark,
                y=0.98 if pos == "top" else 0.86,
                yref="paper",
                text=label,
                showarrow=False,
                xanchor="left",
                xshift=3,
                font={"size": 9.5, "color": color},
            )

    fig.update_layout(
        **plotly_base_layout(
            height=285,
            margin={"l": 48, "r": 16, "t": 36, "b": 40},
            xaxis={"tickangle": 0},
            yaxis={"title": "% of peak SP", "range": [0, 105], "ticksuffix": "%"},
        )
    )
    return fig


def _build_daily_sbp_scatter_fig(selected: dict[str, Any]) -> go.Figure:
    daily = selected.get("daily_series") or []
    xs = [float(d.get("avg_sbp") or 0.0) for d in daily]
    ys = [float(d.get("pos_qcv_mwh") or 0.0) for d in daily]
    ssc_val = float(daily[0].get("avg_ssc") or 106.0) if daily else 106.0
    colors = [
        PALETTE["vermilion"] if float(d.get("avg_sbp") or 0.0) < float(d.get("avg_ssc") or ssc_val)
        else PALETTE["teal"]
        for d in daily
    ]
    hovers = [
        (
            f"<b>{d.get('date', '')} ({d.get('dow', '')})</b>"
            f" — {'Cheap day (< SSC)' if float(d.get('avg_sbp') or 0) < float(d.get('avg_ssc') or ssc_val) else 'High-price day'}"
            f"<br>Turn-down: {float(d.get('pos_qcv_mwh') or 0):.1f} MWh"
            f" · Turn-up: {float(d.get('neg_qcv_mwh') or 0):.1f} MWh"
            f"<br>Avg SBP: £{float(d.get('avg_sbp') or 0):.1f}/MWh"
            f" (min £{float(d.get('min_sbp') or 0):.1f})"
            f"<br>Compensation: {fmt_gbp(d.get('comp_gbp'))}"
        )
        for d in daily
    ]

    fig = go.Figure()
    fig.add_vline(
        x=ssc_val,
        line_dash="dash",
        line_color=PALETTE["vermilion"],
        line_width=1.4,
        annotation_text=f"SSC £{ssc_val:.0f}",
        annotation_position="top right",
        annotation_font={"size": 10.5, "color": PALETTE["vermilion"]},
    )
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=ys,
            mode="markers",
            hovertext=hovers,
            hovertemplate="%{hovertext}<extra></extra>",
            marker={"size": 9, "color": colors, "opacity": 0.86, "line": {"color": "#ffffff", "width": 1}},
            showlegend=False,
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=310,
            hovermode="closest",
            margin={"l": 58, "r": 18, "t": 22, "b": 46},
            xaxis={
                "title": "Daily average System Buy Price (£/MWh)",
                "tickprefix": "£",
                "showgrid": True,
                "gridcolor": PALETTE["grid"],
            },
            yaxis={"title": "Daily turn-down (MWh)"},
        )
    )
    return fig


def _build_sp_profile_fig(selected: dict[str, Any]) -> go.Figure:
    profile = selected.get("sp_profile") or []
    times = [p.get("time", "") for p in profile]
    wkday = [float(p.get("avg_weekday_mwh") or 0.0) for p in profile]
    wkend = [float(p.get("avg_weekend_mwh") or 0.0) for p in profile]
    neg = [float(p.get("avg_neg_mwh") or 0.0) for p in profile]

    fig = go.Figure()
    if "00:00" in times and "05:30" in times:
        fig.add_vrect(
            x0="00:00",
            x1="05:30",
            fillcolor="rgba(44, 92, 197, 0.08)",
            line_width=0,
        )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=wkday,
            mode="lines",
            name="Working days",
            line={"color": PALETTE["teal"], "width": 2.1},
            hovertemplate="<b>Working days:</b> %{y:.2f} MWh/SP<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=wkend,
            mode="lines",
            name="Weekends",
            line={"color": PALETTE["indigo"], "width": 2.0, "dash": "dash"},
            hovertemplate="<b>Weekends:</b> %{y:.2f} MWh/SP<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=neg,
            mode="lines",
            name="Turn-up (-MWh)",
            line={"color": PALETTE["vermilion"], "width": 1.6},
            hovertemplate="<b>Turn-up:</b> %{y:.2f} MWh/SP<extra></extra>",
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=260,
            margin={"l": 54, "r": 14, "t": 32, "b": 38},
            xaxis={"nticks": 9},
            yaxis={"title": "MWh / SP"},
        )
    )
    return fig


def _build_gsp_fig(selected: dict[str, Any]) -> go.Figure:
    gsps = selected.get("gsp_breakdown") or []
    x = [g.get("gsp_group", "") for g in gsps]
    y = [float(g.get("share_pct") or 0.0) for g in gsps]
    custom = [
        (g.get("gsp_name", g.get("gsp_group", "")), float(g.get("abs_qcv_mwh") or 0.0))
        for g in gsps
    ]

    fig = go.Figure(
        go.Bar(
            x=x,
            y=y,
            marker_color=PALETTE["indigo"],
            customdata=custom,
            hovertemplate=(
                "<b>%{x} — %{customdata[0]}</b>"
                "<br>Share: %{y:.1f}% (%{customdata[1]:,.1f} MWh)<extra></extra>"
            ),
            showlegend=False,
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=260,
            hovermode="closest",
            margin={"l": 46, "r": 14, "t": 20, "b": 38},
            yaxis={"title": "Volume share (%)", "ticksuffix": "%"},
        )
    )
    return fig


def _build_ev_suppliers_fig(selected: dict[str, Any]) -> go.Figure:
    suppliers = (selected.get("top_suppliers") or [])[:10]
    suppliers_rev = list(reversed(suppliers))
    names = [s.get("company_name") or s.get("party_id", "") for s in suppliers_rev]
    shares = [float(s.get("share_pct") or 0.0) for s in suppliers_rev]
    colors = [
        PALETTE["vermilion"] if s.get("is_ev_supplier") else PALETTE["ink_muted"]
        for s in suppliers_rev
    ]
    custom = [
        (
            s.get("party_id", ""),
            fmt_gbp(s.get("comp_gbp")),
            fmt_mwh(s.get("qcv_mwh"), 1),
            "EV-tariff supplier" if s.get("is_ev_supplier") else "Other supplier",
        )
        for s in suppliers_rev
    ]

    fig = go.Figure(
        go.Bar(
            x=shares,
            y=names,
            orientation="h",
            marker_color=colors,
            customdata=custom,
            hovertemplate=(
                "<b>%{y} (%{customdata[0]})</b> · %{customdata[3]}"
                "<br>Share: %{x:.1f}% · Comp: %{customdata[1]} · QCV: %{customdata[2]}"
                "<extra></extra>"
            ),
            showlegend=False,
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=280,
            hovermode="closest",
            margin={"l": 145, "r": 20, "t": 16, "b": 38},
            xaxis={"title": "Share of VTP compensation (%)", "ticksuffix": "%", "showgrid": True, "gridcolor": PALETTE["grid"]},
            yaxis={"showgrid": False, "automargin": True},
        )
    )
    return fig


def render_forensics(
    data: dict[str, Any],
    selected_vtp_id: str = "",
) -> html.Div:
    """Render the EV Charger Footprint & Baselining Forensics Lab view."""
    vtps: list[dict[str, Any]] = data.get("vtps") or []
    benchmarks = data.get("benchmarks") or {}
    mv = data.get("market_verdict") or {}
    start_date = data.get("start_date") or ""
    end_date = data.get("end_date") or ""
    granular_days = int(data.get("granular_days") or 0)

    header = html.Div(
        [
            html.Div(
                [
                    html.H1(
                        "EV charger footprint & baselining forensics lab",
                        className="page-title",
                    ),
                    html.P(
                        "Tests whether P415 VTPs are targeting domestic EV chargers and profiting "
                        "from baselines during expensive tariff hours when EVs would not normally charge.",
                        className="page-lead",
                    ),
                ]
            ),
            badge(
                f"Octopus demand share: {benchmarks.get('gb_octopus_demand_share_pct', 0)}%, "
                f"EV suppliers: {benchmarks.get('gb_ev_supplier_demand_share_pct', 0)}%",
                "neutral",
            ),
        ],
        className="page-header",
    )

    if not vtps:
        return html.Div(
            [
                header,
                empty_state(
                    "No granular VTP settlement records in selected window",
                    f"No BMU × SP records were found between {start_date} and {end_date}. "
                    "Fetch Elexon SAA-I014 dates or widen the date range to run the 6-signal forensics lab.",
                    action=html.Button(
                        "Fetch Elexon dates",
                        id={"type": "open-sync-btn", "idx": "forensics-empty"},
                        n_clicks=0,
                        className="btn btn-teal",
                    ),
                ),
            ]
        )

    selected = next(
        (v for v in vtps if v["party_id"] == selected_vtp_id),
        vtps[0],
    )
    sel_id = selected["party_id"]
    ta = selected.get("tariff_analysis") or {}
    sig = selected.get("signals") or {}

    guide_box = html.Details(
        [
            html.Summary(
                "How to read this lab — plain-English guide to scores, quadrants, and baselines",
                className="guide-toggle",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong("EV Focus Score (0–100, X-axis)"),
                            "Measures whether a VTP's assets look like nationwide domestic EV "
                            "chargers rather than commercial sites or grid batteries. High scores "
                            "(≥ 65) combine concentration on EV-tariff suppliers (Octopus, E.ON "
                            "Next, British Gas), presence across all 14 GB GSP groups, hitting "
                            "domestic 2__ supplier BMUs, and holding Elexon's Asset Metering (AV) role.",
                        ]
                    ),
                    html.Div(
                        [
                            html.Strong("Baselining Risk Score (0–100, Y-axis)"),
                            "Measures four physical and economic red flags: (a) claiming turn-down "
                            "without notifying matching recharge rebound, (b) continuing to claim "
                            "turn-down on cheap/negative-price windy days, (c) claiming 14–19 "
                            "hours/day outside the 00:00–05:30 cheap tariff window, and (d) "
                            "clockwork-flat daily volumes.",
                        ]
                    ),
                    html.Div(
                        [
                            html.Strong("BL01/P376 vs Self-Nominated Baselines (SEV)"),
                            "Elexon does not publish a public register of which VTP uses BL01 "
                            "versus custom self-nominated SEV (an open proposal in BSC Issue 127). "
                            "Both paths can inflate baselines: BL01 via excluding event days so "
                            "old high-demand days stay frozen, and self-nominated SEV via "
                            "optimistic forward counterfactuals.",
                        ]
                    ),
                ],
                className="guide-grid",
            ),
        ],
        className="guide-box",
    )

    verdict = html.Section(
        [
            html.H2(mv.get("headline") or "Forensic market verdict"),
            html.P(
                [
                    f"Across {granular_days} granular days ({start_date} to {end_date}), ",
                    html.Strong(fmt_gbp(mv.get("ev_focused_comp_gbp"))),
                    f" ({mv.get('ev_focused_share_pct', 0)}%) of ",
                    fmt_gbp(mv.get("total_comp_gbp")),
                    " total compensation originates from EV-focused domestic aggregators, and ",
                    html.Strong(fmt_gbp(mv.get("ev_baselining_high_risk_gbp"))),
                    f" ({mv.get('ev_baselining_high_risk_share_pct', 0)}%) simultaneously scores "
                    "≥ 65 on multi-signal baselining distortion.",
                ]
            ),
        ],
        className="verdict-banner",
    )

    # Quadrant scatter + ranked table
    quadrant_card = section_card(
        "2D Forensic Quadrant: EV charger focus vs baselining risk",
        dcc.Graph(
            id="forensics-quadrant-chart",
            figure=_build_quadrant_fig(vtps, sel_id),
            config=PLOTLY_CONFIG,
        ),
        subtitle="Bubble area scales with total compensation (£). Click any bubble to inspect its dossier below.",
    )

    rank_rows = []
    for v in vtps:
        pid = v["party_id"]
        ev_s = float(v.get("ev_focus_score") or 0.0)
        rk_s = float(v.get("baselining_risk_score") or 0.0)
        rank_rows.append(
            html.Tr(
                [
                    html.Td(
                        html.Button(
                            [
                                html.Div(v["company_name"], style={"fontWeight": 600, "textAlign": "left"}),
                                html.Div(
                                    pid,
                                    className="mono",
                                    style={"fontSize": "11px", "color": PALETTE["ink_muted"], "textAlign": "left"},
                                ),
                            ],
                            id={"type": "forensics-pick-vtp", "vtp": pid, "idx": f"rank-{pid}"},
                            n_clicks=0,
                            className="table-link-btn",
                        )
                    ),
                    html.Td(v.get("archetype", ""), style={"fontSize": "12px"}),
                    html.Td(
                        badge(f"{ev_s:.0f}", "indigo" if ev_s >= 65 else "neutral"),
                        className="num",
                    ),
                    html.Td(badge(f"{rk_s:.0f}", risk_tone(rk_s)), className="num"),
                    html.Td(
                        fmt_gbp(v.get("comp_gbp"), compact=True),
                        className="num",
                        style={"fontWeight": 600},
                    ),
                ],
                className="selected" if pid == sel_id else "",
            )
        )

    ranking_card = section_card(
        "All active VTPs — forensic ranking",
        html.Div(
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("VTP"),
                                html.Th("Archetype"),
                                html.Th("EV", className="num"),
                                html.Th("Risk", className="num"),
                                html.Th("Comp", className="num"),
                            ]
                        )
                    ),
                    html.Tbody(rank_rows),
                ],
                className="data-table",
            ),
            className="table-scroll",
            style={"maxHeight": "392px"},
        ),
        subtitle="Select any VTP to inspect its full dossier",
    )

    # VTP selector dropdown + quick pills
    vtp_options = [
        {
            "label": f"{v['company_name']} ({v['party_id']}) — EV {float(v.get('ev_focus_score') or 0):.0f} / Risk {float(v.get('baselining_risk_score') or 0):.0f}",
            "value": v["party_id"],
        }
        for v in vtps
    ]
    vtp_controls = html.Div(
        [
            html.Div(
                [
                    html.Span("Inspect VTP:", className="vtp-switcher-label"),
                    *[
                        html.Button(
                            [
                                html.Span(v["company_name"]),
                                html.Span(
                                    "Control"
                                    if v["party_id"] == "CAPTURE"
                                    else f"{float(v.get('market_share_pct') or 0):.1f}%",
                                    className="vtp-pill-share",
                                ),
                            ],
                            id={
                                "type": "forensics-pick-vtp",
                                "vtp": v["party_id"],
                                "idx": f"pill-{v['party_id']}",
                            },
                            n_clicks=0,
                            className="vtp-pill active" if v["party_id"] == sel_id else "vtp-pill",
                        )
                        for v in vtps[:9]
                    ],
                ],
                className="vtp-switcher",
            ),
            html.Div(
                [
                    html.Label("Select any VTP:", htmlFor="forensics-vtp-select"),
                    dcc.Dropdown(
                        id="forensics-vtp-select",
                        options=vtp_options,
                        value=sel_id,
                        clearable=False,
                        style={"minWidth": "300px"},
                    ),
                ],
                className="sbmu-select-wrap",
                style={"marginBottom": "12px"},
            ),
        ]
    )

    # Dark slate dossier hero
    risk_score = float(selected.get("baselining_risk_score") or 0.0)
    dossier_hero = html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H3(
                                [
                                    selected["company_name"],
                                    " ",
                                    html.Span(
                                        sel_id,
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
                            html.P(
                                f"{selected.get('archetype', '')}, {selected.get('bmu_count', 0)} Secondary BMUs, "
                                f"{float(selected.get('market_share_pct') or 0):.1f}% of GB compensation "
                                f"({fmt_gbp(selected.get('comp_gbp'))} on {fmt_mwh(selected.get('net_qcv_mwh'))})",
                                className="dossier-hero-sub",
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            *[
                                html.Span(
                                    r,
                                    className=f"hero-badge {'teal' if r in ('AV', 'VT') else ''}".strip(),
                                )
                                for r in (selected.get("roles") or [])
                            ],
                            html.Span(
                                f"EV focus {float(selected.get('ev_focus_score') or 0):.0f}/100",
                                className="hero-badge",
                            ),
                            html.Span(
                                f"Baselining risk {risk_score:.0f}/100",
                                className=f"hero-badge {risk_tone(risk_score)}",
                            ),
                        ],
                        style={"display": "flex", "gap": "6px", "flexWrap": "wrap", "alignItems": "center"},
                    ),
                ],
                className="dossier-hero-top",
            ),
            html.Ul(
                [html.Li(line) for line in (selected.get("evidence") or [])],
                className="dossier-hero-findings",
            ),
        ],
        className="dossier-hero",
    )

    # Tariff-window & profitability 4-cell ledger strip
    peak_pct = float(ta.get("peak_tariff_share_pct") or 0.0)
    offpeak_pct = float(ta.get("offpeak_tariff_share_pct") or 0.0)
    midday_pct = float(ta.get("weekday_midday_share_pct") or 0.0)
    eflh = float(ta.get("eflh_hours_per_day") or 0.0)

    tariff_strip = html.Section(
        [
            kpi_card(
                "Claimed in expensive tariff hours",
                f"{peak_pct:.1f}%",
                f"Only {offpeak_pct:.1f}% inside cheap overnight EV windows",
                tone="vermilion" if peak_pct >= 85 else "teal",
            ),
            kpi_card(
                "Weekday midday (09:00–16:00)",
                f"{midday_pct:.1f}%",
                "Mon–Fri 09:00–16:00 (26p/kWh & work hours)",
                tone="vermilion" if midday_pct >= 15 else None,
            ),
            kpi_card(
                "Equivalent full-load hours",
                f"{eflh:.1f} h/d",
                "Typical UK EV daily charge: ~1–2 h/d at 7 kW",
                tone="vermilion" if eflh >= 8 else None,
            ),
            kpi_card(
                "Est. VTP wholesale value (MIDP)",
                fmt_gbp(ta.get("estimated_vtp_revenue_gbp"), compact=True),
                f"{fmt_gbp(ta.get('below_ssc_vtp_revenue_gbp'), compact=True)} when MIDP < SSC "
                f"({fmt_gbp(ta.get('deadweight_subsidy_gbp'), compact=True)} deadweight)",
                tone="teal",
            ),
        ],
        className="ledger-strip",
    )

    # Supplier tariff-clock boundary proof panel
    has_clock = bool(ta.get("has_tariff_clock_fingerprint"))
    clock_steps = ta.get("clock_steps") or {}
    clock_badge = (
        badge("Supplier tariff-clock fingerprint detected", "vermilion")
        if has_clock
        else (
            badge("Off-peak control: trades inside cheap EV window", "teal")
            if offpeak_pct >= 80
            else badge("Uniform / non-tariff-clock schedule", "neutral")
        )
    )
    clock_step_badges = (
        html.Div(
            [
                badge(
                    f"05:00 British Gas {clock_steps.get('bg_0500_pct', 0)}% vs Octopus {clock_steps.get('oct_0500_pct', 0)}%",
                    "neutral",
                ),
                badge(
                    f"05:30 Octopus {clock_steps.get('oct_0530_pct', 0)}% vs E.ON {clock_steps.get('eon_0530_pct', 0)}%",
                    "neutral",
                ),
                badge(
                    f"23:30 Octopus {clock_steps.get('oct_2330_pct', 0)}% vs E.ON {clock_steps.get('eon_2330_pct', 0)}%",
                    "neutral",
                ),
                badge(
                    f"00:00 E.ON drops to {clock_steps.get('eon_0000_pct', 0)}%",
                    "neutral",
                ),
            ],
            style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginBottom": "12px"},
        )
        if has_clock
        else None
    )

    boundary_card = section_card(
        "Supplier tariff-clock boundary proof (22:00–08:30, % of each supplier's peak)",
        [
            *([] if clock_step_badges is None else [clock_step_badges]),
            dcc.Graph(
                figure=_build_boundary_curves_fig(selected),
                config=PLOTLY_CONFIG,
            ),
        ],
        subtitle=(
            "Each supplier's curve drops when its own cheap EV rate begins (EDF 23:00, Octopus "
            "23:30, E.ON 00:00) and surges the exact half-hour its cheap rate ends (British Gas "
            "05:00, Octopus 05:30, E.ON 06:00)."
        ),
        actions=clock_badge,
    )

    # 6-Signal Forensic Breakdown
    daily_r = sig.get("daily_price_corr")
    daily_r_str = f"{float(daily_r):+.2f}" if daily_r is not None else "n/a"
    six_signals = [
        (
            "EV-tariff supplier over-index",
            float(sig.get("ev_affinity_score") or 0.0),
            f"Octopus Energy: {sig.get('octopus_share_pct', 0)}% ({sig.get('octopus_lift', 0)}x GB share). "
            f"All EV-tariff suppliers: {sig.get('ev_supplier_share_pct', 0)}% ({sig.get('ev_lift', 0)}x GB share).",
        ),
        (
            "National domestic footprint (14 GSPs & 2__ BMUs)",
            float(sig.get("domestic_footprint_score") or 0.0),
            f"Active in {sig.get('gsp_count', 0)}/14 GB GSP groups (entropy {sig.get('gsp_entropy', 0)}); "
            f"{sig.get('base_bmu_share_pct', 0)}% on Base Supplier (2__) domestic/SME BMUs.",
        ),
        (
            "Energy conservation violation (missing rebound)",
            float(sig.get("conservation_score") or 0.0),
            f"{sig.get('one_sided_ratio_pct', 0)}% one-sided positive turn-down "
            f"(+{float(selected.get('pos_qcv_mwh') or 0):,.1f} MWh vs "
            f"{float(selected.get('neg_qcv_mwh') or 0):,.1f} MWh turn-up).",
        ),
        (
            "Wholesale price insensitivity (low-price farming)",
            float(sig.get("low_price_farming_score") or 0.0),
            f"{sig.get('pct_below_ssc', 0)}% triggered when SBP < SSC; "
            f"{sig.get('pct_below_60', 0)}% when SBP < £60/MWh. Daily vol-price r = {daily_r_str}.",
        ),
        (
            "Continuous duty cycle & 00:00–05:30 EV cliff",
            float(sig.get("duty_cycle_score") or 0.0),
            f"Active {sig.get('active_hours_per_day', 0)} hrs/day avg; daytime/evening volume is "
            f"{sig.get('day_to_night_ratio', 0)}x overnight EV window."
            + (" Pre-evening turn-up detected." if sig.get("pre_event_turnup_flag") else ""),
        ),
        (
            "Multi-day persistence (frozen baseline)",
            float(sig.get("persistence_score") or 0.0),
            f"Active {sig.get('active_days', 0)}/{sig.get('total_days', 0)} days; daily volume "
            f"CoV = {sig.get('daily_cov', 0)} (lower = clockwork flat output).",
        ),
    ]

    signals_card = section_card(
        "Six-signal forensic breakdown",
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(name, className="signal-name"),
                            html.Span(
                                f"{score:.0f}/100",
                                className="mono",
                                style={"fontWeight": 600, "color": _score_color(score)},
                            ),
                        ],
                        className="signal-head",
                    ),
                    html.Div(
                        html.Div(
                            className="signal-bar-fill",
                            style={
                                "width": f"{min(100.0, max(0.0, score)):.1f}%",
                                "backgroundColor": _score_color(score),
                            },
                        ),
                        className="signal-bar-track",
                    ),
                    html.Div(detail_txt, className="signal-detail"),
                ],
                className="signal-row",
            )
            for name, score, detail_txt in six_signals
        ],
        subtitle=f"Decomposed forensic scores for {selected['company_name']}",
    )

    # Daily volume vs SBP scatter + Secondary BMU tranches
    sub_bmus = selected.get("sub_bmus") or []
    tranches_block = (
        html.Div(
            [
                html.Div(
                    "Secondary BMU portfolio tranches (suffix *001 / *002 / *003)",
                    style={"fontSize": "12.5px", "fontWeight": 600, "marginBottom": "8px"},
                ),
                html.Div(
                    [
                        badge(
                            f"*{sb.get('suffix', '')}: {float(sb.get('total_qcv_mwh') or 0):,.0f} MWh "
                            f"({sb.get('active_days', 0)}d)",
                            "neutral",
                        )
                        for sb in sub_bmus
                    ],
                    style={"display": "flex", "gap": "8px", "flexWrap": "wrap"},
                ),
            ],
            style={"marginTop": "14px", "paddingTop": "12px", "borderTop": f"1px solid {PALETTE['border']}"},
        )
        if sub_bmus
        else None
    )

    sbp_scatter_card = section_card(
        "Low-price farming test: daily volume vs daily average SBP",
        [
            dcc.Graph(
                figure=_build_daily_sbp_scatter_fig(selected),
                config=PLOTLY_CONFIG,
            ),
            *([] if tranches_block is None else [tranches_block]),
        ],
        subtitle="Each dot is one settled day. A flat horizontal band across cheap (left of SSC) and expensive days shows price-insensitive harvesting.",
        actions=badge(
            f"Pearson r = {daily_r_str}",
            "vermilion" if (daily_r is not None and float(daily_r) < 0.25) else "teal",
        ),
    )

    # 48-SP profile & GSP dispersion
    sp_profile_card = section_card(
        f"{selected['company_name']} — 48-SP profile (working vs non-working days)",
        dcc.Graph(figure=_build_sp_profile_fig(selected), config=PLOTLY_CONFIG),
        subtitle="Shaded 00:00–05:30 band shows domestic EV off-peak window alignment",
    )

    gsp_card = section_card(
        f"Geographic GSP footprint ({sig.get('gsp_count', 0)}/14 GB regions)",
        dcc.Graph(figure=_build_gsp_fig(selected), config=PLOTLY_CONFIG),
        subtitle="Broad Southern/Eastern/Midlands weighting mirrors UK residential EV ownership",
    )

    # EV-Tariff Supplier Over-Representation Panel (chart + table)
    top_suppliers = selected.get("top_suppliers") or []
    supplier_rows = [
        html.Tr(
            [
                html.Td(
                    [
                        html.Div(s.get("company_name") or s.get("party_id", ""), style={"fontWeight": 600}),
                        html.Div(
                            s.get("party_id", ""),
                            className="mono",
                            style={"fontSize": "11px", "color": PALETTE["ink_muted"]},
                        ),
                    ]
                ),
                html.Td(
                    badge("EV tariff", "vermilion")
                    if s.get("is_ev_supplier")
                    else badge("Standard", "neutral")
                ),
                html.Td(f"{float(s.get('share_pct') or 0):.1f}%", className="num"),
                html.Td(fmt_mwh(s.get("qcv_mwh"), 1), className="num"),
                html.Td(
                    fmt_gbp(s.get("comp_gbp"), compact=True),
                    className="num",
                    style={"fontWeight": 600},
                ),
            ]
        )
        for s in top_suppliers[:10]
    ]

    ev_suppliers_card = section_card(
        f"EV-tariff supplier over-representation — {selected['company_name']}",
        html.Div(
            [
                dcc.Graph(
                    figure=_build_ev_suppliers_fig(selected),
                    config=PLOTLY_CONFIG,
                ),
                html.Div(
                    html.Table(
                        [
                            html.Thead(
                                html.Tr(
                                    [
                                        html.Th("Primary Supplier"),
                                        html.Th("Tariff class"),
                                        html.Th("Share", className="num"),
                                        html.Th("QCV", className="num"),
                                        html.Th("Comp", className="num"),
                                    ]
                                )
                            ),
                            html.Tbody(supplier_rows),
                        ],
                        className="data-table",
                    ),
                    className="table-scroll",
                    style={"maxHeight": "280px"},
                ),
            ],
            className="grid-2",
        ),
        subtitle=(
            f"EV-tariff suppliers represent {sig.get('ev_supplier_share_pct', 0)}% of this VTP's "
            f"compensation ({sig.get('ev_lift', 0)}× their "
            f"{benchmarks.get('gb_ev_supplier_demand_share_pct', 0)}% GB demand share)."
        ),
        actions=[
            badge(f"Octopus lift {sig.get('octopus_lift', 0)}×", "indigo"),
            badge(f"EV supplier lift {sig.get('ev_lift', 0)}×", "vermilion" if float(sig.get("ev_lift") or 0) >= 1.5 else "neutral"),
        ],
    )

    # Cross-VTP Tariff-Window & Profitability Comparison Table
    comp_rows = []
    for v in vtps:
        vta = v.get("tariff_analysis") or {}
        pid = v["party_id"]
        pk = float(vta.get("peak_tariff_share_pct") or 0.0)
        dw = float(vta.get("deadweight_subsidy_gbp") or 0.0)
        comp_rows.append(
            html.Tr(
                [
                    html.Td(
                        html.Button(
                            [
                                html.Div(v["company_name"], style={"fontWeight": 600, "textAlign": "left"}),
                                html.Div(
                                    pid,
                                    className="mono",
                                    style={"fontSize": "11px", "color": PALETTE["ink_muted"], "textAlign": "left"},
                                ),
                            ],
                            id={"type": "forensics-pick-vtp", "vtp": pid, "idx": f"comp-{pid}"},
                            n_clicks=0,
                            className="table-link-btn",
                        )
                    ),
                    html.Td(
                        badge(
                            f"{pk:.1f}%",
                            "vermilion" if pk >= 85 else ("teal" if pk <= 10 else "neutral"),
                        ),
                        className="num",
                    ),
                    html.Td(f"{float(vta.get('weekday_midday_share_pct') or 0):.1f}%", className="num"),
                    html.Td(f"{float(vta.get('eflh_hours_per_day') or 0):.1f} h/d", className="num"),
                    html.Td(
                        fmt_gbp(vta.get("estimated_vtp_revenue_gbp"), compact=True),
                        className="num",
                        style={"fontWeight": 600},
                    ),
                    html.Td(
                        fmt_gbp(vta.get("below_ssc_vtp_revenue_gbp"), compact=True),
                        className="num",
                    ),
                    html.Td(
                        fmt_gbp(dw, compact=True),
                        className="num",
                        style={
                            "color": PALETTE["vermilion"] if dw > 5000 else PALETTE["ink"],
                            "fontWeight": 600 if dw > 5000 else 400,
                        },
                    ),
                    html.Td(
                        badge("Clock match", "vermilion")
                        if vta.get("has_tariff_clock_fingerprint")
                        else (
                            badge("Off-peak only", "teal")
                            if float(vta.get("offpeak_tariff_share_pct") or 0) >= 80
                            else badge("Uniform", "neutral")
                        )
                    ),
                ],
                className="selected" if pid == sel_id else "",
            )
        )

    cross_vtp_card = section_card(
        "Cross-VTP tariff-window & profitability comparison",
        html.Div(
            html.Table(
                [
                    html.Thead(
                        html.Tr(
                            [
                                html.Th("VTP"),
                                html.Th("Peak-tariff %", className="num"),
                                html.Th("Wkday 09–16", className="num"),
                                html.Th("EFLH", className="num"),
                                html.Th("Est. VTP Rev", className="num"),
                                html.Th("Rev < SSC", className="num"),
                                html.Th("Deadweight", className="num"),
                                html.Th("Tariff clock"),
                            ]
                        )
                    ),
                    html.Tbody(comp_rows),
                ],
                className="data-table",
            ),
            className="table-scroll",
        ),
        subtitle="Estimated wholesale revenue uses Elexon MIDP (mpj) as a transparent proxy; click any VTP to inspect its supplier tariff-clock curves.",
        actions=[
            badge(f"Total est. value {fmt_gbp(mv.get('total_estimated_vtp_revenue_gbp'), compact=True)}", "teal"),
            badge(f"Deadweight {fmt_gbp(mv.get('total_deadweight_subsidy_gbp'), compact=True)}", "vermilion"),
        ],
    )

    methodology_card = section_card(
        "Methodology, economic reasoning & analytical caveats",
        html.Div(
            [
                html.Div(
                    [
                        html.Strong("The EV-tariff counterfactual paradox: "),
                        "UK EV tariffs create a ~3.5–4× overnight discount (Octopus IOG 23:30–05:30, "
                        "E.ON Next Drive 00:00–06:00, British Gas Electric Driver 00:00–05:00, EDF "
                        "GoElectric 23:00–06:00). If a VTP's baseline assumes daytime charging, "
                        "routine tariff-driven non-charging looks like demand turn-down all day long.",
                    ]
                ),
                html.Div(
                    [
                        html.Strong("Why VTPs profit even on cheap windy days: "),
                        "Under P415 mutualisation, the VTP does not pay the ~£106/MWh Supplier "
                        "Sourcing Cost (ssc); all GB suppliers pay it via scvp. Turning down an EV "
                        "that was not going to charge earns MIDP while imposing SSC − MIDP deadweight "
                        "on GB billpayers whenever MIDP < SSC.",
                    ]
                ),
                html.Div(
                    [
                        html.Strong("Formulas & honest caveats: "),
                        "Est. VTP Rev = Σ(qcv × mpj); Deadweight = Σ(qcv × (ssc − mpj)) where "
                        "mpj < ssc; EFLH = avg(daily MWh ÷ daily peak MW). Portfolios may mix EV "
                        "chargers with home batteries or heat pumps, and individual MPAN baselines "
                        "are not published in public SAA-I014 files.",
                    ]
                ),
            ],
            className="guide-grid no-border",
        ),
        actions=badge("BSC Issue 127 (Oct 2026)", "amber"),
    )

    return html.Div(
        [
            header,
            guide_box,
            verdict,
            html.Div([quadrant_card, ranking_card], className="grid-asymmetric"),
            vtp_controls,
            dossier_hero,
            tariff_strip,
            boundary_card,
            html.Div([signals_card, sbp_scatter_card], className="grid-2"),
            html.Div([sp_profile_card, gsp_card], className="grid-2"),
            ev_suppliers_card,
            cross_vtp_card,
            methodology_card,
        ]
    )
