"""Overview view: P415 Virtual Trading Party settlement ledger, macro trend, and top participants."""

from __future__ import annotations

import datetime as dt
from typing import Any

import plotly.graph_objects as go
from dash import dcc, html

from ..formatting import (
    PALETTE,
    PLOTLY_CONFIG,
    badge,
    empty_state,
    fmt_gbp,
    fmt_gbp_exact,
    fmt_mwh,
    fmt_num,
    fmt_signed_gbp,
    kpi_card,
    plotly_base_layout,
    section_card,
)


def _snap_milestone_date(target_iso: str, dates: list[str]) -> str | None:
    if not dates:
        return None
    try:
        target = dt.date.fromisoformat(target_iso)
    except ValueError:
        return None
    best = dates[0]
    best_diff = abs((dt.date.fromisoformat(best) - target).days)
    for d in dates[1:]:
        try:
            diff = abs((dt.date.fromisoformat(d) - target).days)
        except ValueError:
            continue
        if diff < best_diff:
            best_diff = diff
            best = d
    return best


def _build_macro_figure(
    macro_timeline: list[dict[str, Any]],
    milestones: list[dict[str, Any]],
) -> go.Figure:
    fig = go.Figure()
    if not macro_timeline:
        fig.update_layout(**plotly_base_layout(height=300))
        return fig

    dates = [pt["date"] for pt in macro_timeline]
    pos_sccp = [float(pt.get("pos_sccp_gbp", 0.0) or 0.0) for pt in macro_timeline]
    oct_sccp = [float(pt.get("octopus_sccp_gbp", 0.0) or 0.0) for pt in macro_timeline]
    qcv_mwh = [float(pt.get("qcv_mwh", 0.0) or 0.0) for pt in macro_timeline]

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=pos_sccp,
            name="Total GB compensation (sccp)",
            mode="lines",
            line={"color": PALETTE["teal"], "width": 2.1},
            fill="tozeroy",
            fillcolor="rgba(11, 122, 117, 0.16)",
            hovertemplate="£%{y:,.0f}<extra>Total GB sccp</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=oct_sccp,
            name="Octopus Energy (MERCURY)",
            mode="lines",
            line={"color": PALETTE["indigo"], "width": 1.8},
            fill="tozeroy",
            fillcolor="rgba(44, 92, 197, 0.15)",
            hovertemplate="£%{y:,.0f}<extra>Octopus Energy (MERCURY)</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=qcv_mwh,
            name="Daily QCV (MWh)",
            mode="lines",
            yaxis="y2",
            line={"color": PALETTE["amber"], "width": 1.4, "dash": "dot"},
            hovertemplate="%{y:,.1f} MWh<extra>Daily QCV</extra>",
        )
    )

    for m in milestones or []:
        snapped = _snap_milestone_date(str(m.get("date", "")), dates)
        if not snapped:
            continue
        code = str(m.get("code", ""))
        label = f"{code} ({str(m.get('date', ''))[:7]})"
        fig.add_vline(
            x=snapped,
            line_dash="dash",
            line_color=PALETTE["vermilion"],
            line_width=1.4,
        )
        fig.add_annotation(
            x=snapped,
            y=1.0,
            yref="paper",
            text=label,
            showarrow=False,
            xanchor="left" if code == "P415" else "right",
            xshift=6 if code == "P415" else -6,
            yshift=-6,
            font={"size": 11, "color": PALETTE["vermilion"]},
            bgcolor="rgba(255,255,255,0.85)",
            borderpad=2,
        )

    fig.update_layout(
        **plotly_base_layout(
            height=320,
            margin={"l": 64, "r": 64, "t": 38, "b": 42},
            xaxis={"title": None},
            yaxis={
                "title": "Daily compensation (£)",
                "tickprefix": "£",
            },
            yaxis2={
                "title": "Daily QCV (MWh)",
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
                "zeroline": False,
                "tickfont": {"size": 11, "color": PALETTE["amber"]},
                "title_font": {"size": 11.5, "color": PALETTE["amber"]},
                "ticksuffix": " MWh",
            },
        )
    )
    return fig


def _build_granular_daily_figure(
    macro_timeline: list[dict[str, Any]],
    start_date: str,
    end_date: str,
) -> go.Figure | None:
    window_pts = [
        pt
        for pt in macro_timeline
        if start_date <= str(pt.get("date", "")) <= end_date
        and pt.get("has_bmu_sp")
    ]
    if not window_pts:
        window_pts = [
            pt
            for pt in macro_timeline
            if start_date <= str(pt.get("date", "")) <= end_date
        ]
    if not window_pts:
        return None

    dates = [pt["date"] for pt in window_pts]
    pos_sccp = [float(pt.get("pos_sccp_gbp", 0.0) or 0.0) for pt in window_pts]
    oct_sccp = [float(pt.get("octopus_sccp_gbp", 0.0) or 0.0) for pt in window_pts]
    qcv_mwh = [float(pt.get("qcv_mwh", 0.0) or 0.0) for pt in window_pts]
    avg_sbp = [float(pt.get("avg_sbp", 0.0) or 0.0) for pt in window_pts]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=dates,
            y=pos_sccp,
            name="Total GB compensation (£)",
            marker_color=PALETTE["teal"],
            opacity=0.82,
            customdata=avg_sbp,
            hovertemplate="£%{y:,.0f} (Avg SBP £%{customdata:.1f}/MWh)<extra>Total GB sccp</extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=dates,
            y=oct_sccp,
            name="Octopus Energy (MERCURY)",
            marker_color=PALETTE["indigo"],
            opacity=0.85,
            hovertemplate="£%{y:,.0f}<extra>Octopus Energy</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=qcv_mwh,
            name="Daily QCV (MWh)",
            mode="lines+markers",
            yaxis="y2",
            line={"color": PALETTE["amber"], "width": 2.0},
            marker={"size": 4.5, "color": PALETTE["amber"]},
            hovertemplate="%{y:,.1f} MWh<extra>Daily QCV</extra>",
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=280,
            barmode="overlay",
            margin={"l": 64, "r": 64, "t": 38, "b": 42},
            xaxis={"title": None},
            yaxis={
                "title": "Daily compensation (£)",
                "tickprefix": "£",
            },
            yaxis2={
                "title": "Daily QCV (MWh)",
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
                "zeroline": False,
                "tickfont": {"size": 11, "color": PALETTE["amber"]},
                "title_font": {"size": 11.5, "color": PALETTE["amber"]},
                "ticksuffix": " MWh",
            },
        )
    )
    return fig


def _render_top_vtps_table(top_vtps: list[dict[str, Any]]) -> Any:
    if not top_vtps:
        return html.P(
            "No active Virtual Trading Parties in the selected date window.",
            style={"color": PALETTE["ink_muted"], "margin": "0"},
        )

    rows = []
    for idx, v in enumerate(top_vtps):
        party_id = str(v.get("party_id", ""))
        roles = v.get("roles") or []
        share_pct = float(v.get("share_pct", 0.0) or 0.0)
        bar_width = f"{min(100.0, max(2.0, share_pct)):.1f}%"

        role_badges = html.Div(
            [
                badge(str(r), "teal" if r in ("VT", "AV") else "neutral")
                for r in roles
            ],
            style={"display": "flex", "gap": "4px", "flexWrap": "wrap"},
        )

        rows.append(
            html.Tr(
                [
                    html.Td(
                        [
                            html.Div(
                                v.get("company_name") or party_id,
                                style={"fontWeight": "600"},
                            ),
                            html.Div(
                                party_id,
                                className="mono",
                                style={"fontSize": "11.5px", "color": PALETTE["ink_muted"]},
                            ),
                        ]
                    ),
                    html.Td(role_badges),
                    html.Td(fmt_num(v.get("bmu_count", 0)), className="num"),
                    html.Td(fmt_num(v.get("net_qcv_mwh", 0.0), 1), className="num"),
                    html.Td(
                        fmt_gbp(v.get("comp_gbp", 0.0)),
                        className="num",
                        style={"fontWeight": "600"},
                    ),
                    html.Td(
                        html.Span(
                            [
                                html.Span(
                                    html.Span(
                                        className="share-bar-fill",
                                        style={"width": bar_width},
                                    ),
                                    className="share-bar-track",
                                ),
                                html.Span(f"{share_pct:.1f}%"),
                            ],
                            className="share-bar-cell",
                        ),
                        className="num",
                    ),
                    html.Td(
                        html.Button(
                            "Inspect →",
                            id={
                                "type": "nav-vtp-btn",
                                "target": "forensics",
                                "vtp": party_id,
                                "idx": f"ov-vtp-{idx}",
                            },
                            n_clicks=0,
                            className="btn btn-sm",
                            title=f"Open EV & baselining forensic dossier for {party_id}",
                        ),
                        className="num",
                    ),
                ]
            )
        )

    return html.Div(
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("VTP / Company"),
                            html.Th("Roles"),
                            html.Th("SBMUs", className="num"),
                            html.Th("Net QCV (MWh)", className="num"),
                            html.Th("Compensation", className="num"),
                            html.Th("Share", className="num"),
                            html.Th("", className="num"),
                        ]
                    )
                ),
                html.Tbody(rows),
            ],
            className="data-table",
        ),
        className="table-scroll",
    )


def _render_suppliers_table(
    top_winners: list[dict[str, Any]],
    top_payers: list[dict[str, Any]],
) -> Any:
    if not top_winners and not top_payers:
        return html.P(
            "No supplier mutualisation records in the selected date window.",
            style={"color": PALETTE["ink_muted"], "margin": "0"},
        )

    rows: list[Any] = []
    for s in top_winners[:5]:
        rows.append(
            html.Tr(
                [
                    html.Td(
                        [
                            html.Div(
                                s.get("company_name") or s.get("party_id", ""),
                                style={"fontWeight": "600"},
                            ),
                            html.Div(
                                s.get("party_id", ""),
                                className="mono",
                                style={"fontSize": "11px", "color": PALETTE["ink_muted"]},
                            ),
                        ]
                    ),
                    html.Td(fmt_gbp(s.get("sccp_gbp", 0.0), True), className="num"),
                    html.Td(fmt_gbp(s.get("scvp_gbp", 0.0), True), className="num"),
                    html.Td(
                        fmt_signed_gbp(s.get("net_gbp", 0.0), True),
                        className="num",
                        style={"color": PALETTE["teal"], "fontWeight": "600"},
                    ),
                ]
            )
        )

    if top_payers:
        rows.append(
            html.Tr(
                html.Td(
                    "Largest net contributors to mutualised pot",
                    colSpan=4,
                    style={
                        "background": PALETTE["bg_subtle"],
                        "fontSize": "11.5px",
                        "fontWeight": "600",
                        "color": PALETTE["ink_secondary"],
                        "padding": "5px 14px",
                    },
                )
            )
        )
        for s in top_payers[:5]:
            rows.append(
                html.Tr(
                    [
                        html.Td(
                            [
                                html.Div(
                                    s.get("company_name") or s.get("party_id", ""),
                                    style={"fontWeight": "600"},
                                ),
                                html.Div(
                                    s.get("party_id", ""),
                                    className="mono",
                                    style={"fontSize": "11px", "color": PALETTE["ink_muted"]},
                                ),
                            ]
                        ),
                        html.Td(fmt_gbp(s.get("sccp_gbp", 0.0), True), className="num"),
                        html.Td(fmt_gbp(s.get("scvp_gbp", 0.0), True), className="num"),
                        html.Td(
                            fmt_signed_gbp(s.get("net_gbp", 0.0), True),
                            className="num",
                            style={"color": PALETTE["vermilion"], "fontWeight": "600"},
                        ),
                    ]
                )
            )

    return html.Div(
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Supplier"),
                            html.Th("Received", className="num"),
                            html.Th("Paid", className="num"),
                            html.Th("Net", className="num"),
                        ]
                    )
                ),
                html.Tbody(rows),
            ],
            className="data-table",
        ),
        className="table-scroll",
    )


def render_overview(data: dict[str, Any] | None) -> html.Div:
    """Render the Overview tab (KPI strip, 2-year macro trend, daily granular chart, VTP & supplier tables)."""
    if not data:
        return html.Div(
            empty_state(
                "No settlement data available",
                "Fetch Elexon SAA-I014 settlement dates to populate the P415 overview.",
                action=html.Button(
                    "Fetch Elexon dates",
                    id={"type": "open-sync-btn", "idx": "overview-none"},
                    n_clicks=0,
                    className="btn btn-teal",
                ),
            )
        )

    summary = data.get("summary") or {}
    top_vtps = data.get("top_vtps") or []
    top_winners = data.get("top_winners") or []
    top_payers = data.get("top_payers") or []
    macro_timeline = data.get("macro_timeline") or []
    milestones = data.get("milestones") or []
    granular_days = int(data.get("granular_days", 0) or 0)
    start_date = str(data.get("start_date") or "")
    end_date = str(data.get("end_date") or "")

    if granular_days == 0 and not macro_timeline and not top_vtps:
        return html.Div(
            empty_state(
                "No granular or macro settlement data in selected window",
                f"No Elexon SAA-I014 settlement records were found between {start_date or 'start'} and {end_date or 'end'}.",
                action=html.Button(
                    "Fetch Elexon dates",
                    id={"type": "open-sync-btn", "idx": "overview-empty"},
                    n_clicks=0,
                    className="btn btn-teal",
                ),
            )
        )

    max_recon_diff = float(summary.get("max_reconciliation_diff_gbp", 0.0) or 0.0)
    recon_exact = max_recon_diff < 0.05
    pos_qcv = float(summary.get("pos_qcv_mwh", 0.0) or 0.0)
    neg_qcv = float(summary.get("neg_qcv_mwh", 0.0) or 0.0)
    abs_tot_qcv = pos_qcv + abs(neg_qcv)
    one_sided_pct = (pos_qcv / abs_tot_qcv * 100.0) if abs_tot_qcv > 0 else 0.0

    recon_badge = badge(
        (
            f"BMU × SP reconciled to SAA mutualised pot (diff £{max_recon_diff:.2f})"
            if recon_exact
            else f"Market reconciliation variance £{max_recon_diff:.2f}"
        ),
        tone="teal" if recon_exact else "amber",
    )

    header = html.Div(
        [
            html.Div(
                [
                    html.H1("P415 Virtual Trading Party settlement overview", className="page-title"),
                    html.P(
                        f"Reconciled from Elexon SAA-I014 Primary/Secondary BMU records and daily party "
                        f"settlement accounts across {granular_days} granular days ({start_date} to {end_date}).",
                        className="page-lead",
                    ),
                ]
            ),
            recon_badge,
        ],
        className="page-header",
    )

    kpi_strip = html.Section(
        [
            kpi_card(
                "BMU-attributed compensation",
                fmt_gbp(summary.get("total_comp_gbp", 0.0), compact=True),
                sub=(
                    f"{fmt_gbp(summary.get('daily_avg_comp_gbp', 0.0), True)}/day "
                    f"({fmt_gbp(summary.get('annualised_comp_gbp', 0.0), True)}/yr run-rate)"
                ),
                tone="teal",
            ),
            kpi_card(
                "Net compensation volume",
                fmt_mwh(summary.get("net_qcv_mwh", 0.0), 0),
                sub=f"{one_sided_pct:.1f}% turn-down ({fmt_mwh(neg_qcv, 0)} turn-up)",
            ),
            kpi_card(
                "Active VTPs & SBMUs",
                [
                    str(int(summary.get("active_vtps", 0) or 0)),
                    html.Span(
                        f" / {int(summary.get('active_sbmus', 0) or 0)}",
                        style={"fontSize": "14px", "color": PALETTE["ink_muted"]},
                    ),
                ],
                sub=f"Affecting {int(summary.get('active_suppliers', 0) or 0)} licensed GB suppliers",
            ),
            kpi_card(
                "Supplier Sourcing Cost (SSC)",
                f"£{float(summary.get('avg_ssc', 0.0) or 0.0):.2f}",
                sub=(
                    f"Avg SBP £{float(summary.get('avg_sbp', 0.0) or 0.0):.1f}/MWh, "
                    f"Market Price £{float(summary.get('avg_mpj', 0.0) or 0.0):.1f}/MWh"
                ),
            ),
            kpi_card(
                "Mutualised levy recovered",
                fmt_gbp(summary.get("party_total_scvp_gbp", 0.0), compact=True),
                sub="Paid by all GB suppliers in proportion to demand",
            ),
        ],
        className="ledger-strip",
    )

    macro_panel = section_card(
        title="Two-year GB supplier compensation trajectory",
        subtitle=(
            f"Daily positive supplier compensation cashflow (sccp) and daily QCV volume across "
            f"{len(macro_timeline)} settled dates, highlighting Octopus Energy’s share and the P511 "
            f"large-generation cap."
        ),
        actions=[
            badge("Total GB positive sccp", "teal"),
            badge("Octopus Energy (MERCURY)", "indigo"),
            badge("Daily QCV (MWh)", "amber"),
        ],
        children=(
            dcc.Graph(
                id="overview-macro-chart",
                figure=_build_macro_figure(macro_timeline, milestones),
                config=PLOTLY_CONFIG,
            )
            if macro_timeline
            else html.P(
                "No macro timeline records ingested yet.",
                style={"color": PALETTE["ink_muted"], "margin": "0"},
            )
        ),
    )

    granular_fig = _build_granular_daily_figure(macro_timeline, start_date, end_date)
    granular_panel = (
        section_card(
            title="Daily granular compensation & volume (selected window)",
            subtitle=(
                f"Daily GB supplier compensation (£), Octopus Energy share (£), and total QCV (MWh) "
                f"from {start_date} to {end_date}."
            ),
            children=dcc.Graph(
                id="overview-granular-chart",
                figure=granular_fig,
                config=PLOTLY_CONFIG,
            ),
        )
        if granular_fig is not None
        else None
    )

    tables_grid = html.Div(
        [
            section_card(
                title="Active Virtual Trading Parties",
                subtitle="Inspect any VTP to open its 6-signal EV & baselining forensic dossier",
                actions=html.Button(
                    "Open EV lab",
                    id={
                        "type": "nav-vtp-btn",
                        "target": "forensics",
                        "vtp": "",
                        "idx": "overview-ev-lab",
                    },
                    n_clicks=0,
                    className="btn btn-sm",
                ),
                children=_render_top_vtps_table(top_vtps),
            ),
            section_card(
                title="Mutualisation net winners and payers",
                subtitle="Supplier compensation received (sccp) minus mutualised levy paid (scvp)",
                actions=html.Button(
                    "Full ledger",
                    id={
                        "type": "nav-vtp-btn",
                        "target": "compensation",
                        "vtp": "",
                        "idx": "overview-full-ledger",
                    },
                    n_clicks=0,
                    className="btn btn-sm",
                ),
                children=_render_suppliers_table(top_winners, top_payers),
            ),
        ],
        className="grid-asymmetric",
    )

    recon_note = html.Div(
        html.Div(
            [
                html.Strong("Settlement reconciliation note: "),
                html.Span(
                    f"BMU × SP attributed compensation totals {fmt_gbp_exact(summary.get('total_comp_gbp', 0.0))} "
                    f"against {fmt_gbp_exact(summary.get('party_total_scvp_gbp', 0.0))} recovered via the "
                    f"market-wide mutualised levy (scvp) and {fmt_gbp_exact(summary.get('party_pos_sccp_gbp', 0.0))} "
                    f"in positive supplier sccp across {granular_days} granular settlement days "
                    f"(variance {fmt_gbp_exact(max_recon_diff)})."
                ),
            ],
            className="chart-footnote",
            style={"marginTop": "0", "paddingTop": "0", "borderTop": "none"},
        ),
        className="panel",
        style={"padding": "14px 20px"},
    )

    children: list[Any] = [header, kpi_strip, macro_panel]
    if granular_panel is not None:
        children.append(granular_panel)
    children.extend([tables_grid, recon_note])
    return html.Div(children)
