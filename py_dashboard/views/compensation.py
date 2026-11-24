"""Compensation view: supplier mutualisation ledger, diverging net transfers, over-index ratio, and VTP flows."""

from __future__ import annotations

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
    fmt_pct,
    fmt_signed_gbp,
    kpi_card,
    plotly_base_layout,
    section_card,
)


def _short_label(name: str, max_len: int = 24) -> str:
    text = str(name or "")
    return f"{text[: max_len - 1]}…" if len(text) > max_len else text


def _build_diverging_transfer_figure(suppliers: list[dict[str, Any]]) -> go.Figure:
    fig = go.Figure()
    if not suppliers:
        fig.update_layout(**plotly_base_layout(height=340))
        return fig

    sorted_net = sorted(
        suppliers,
        key=lambda s: float(s.get("net_transfer_gbp", 0.0) or 0.0),
        reverse=True,
    )
    winners = [s for s in sorted_net if float(s.get("net_transfer_gbp", 0.0) or 0.0) > 0][:7]
    payers = [s for s in sorted_net if float(s.get("net_transfer_gbp", 0.0) or 0.0) < 0][-8:]
    rows = winners + payers
    if not rows:
        fig.update_layout(**plotly_base_layout(height=300))
        return fig

    labels = [_short_label(s.get("company_name") or s.get("party_id", "")) for s in rows]
    vals = [float(s.get("net_transfer_gbp", 0.0) or 0.0) for s in rows]
    colors = [PALETTE["teal"] if v >= 0 else PALETTE["vermilion"] for v in vals]
    custom = [
        [
            s.get("company_name") or s.get("party_id", ""),
            s.get("party_id", ""),
            float(s.get("sccp_gbp", 0.0) or 0.0),
            float(s.get("scvp_gbp", 0.0) or 0.0),
            float(s.get("over_index_ratio", 0.0) or 0.0),
        ]
        for s in rows
    ]

    fig.add_trace(
        go.Bar(
            y=labels,
            x=vals,
            orientation="h",
            marker_color=colors,
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                "Net transfer: <b>£%{x:+,.0f}</b><br>"
                "Received (sccp): £%{customdata[2]:,.0f}<br>"
                "Paid (scvp): £%{customdata[3]:,.0f}<br>"
                "Over-index ratio: %{customdata[4]:.2f}x<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=0, line_color=PALETTE["ink"], line_width=1.1)

    height = max(300, min(520, 70 + len(rows) * 26))
    fig.update_layout(
        **plotly_base_layout(
            height=height,
            hovermode="closest",
            showlegend=False,
            margin={"l": 175, "r": 28, "t": 16, "b": 40},
            xaxis={
                "title": "Net mutualisation transfer (£)",
                "tickprefix": "£",
                "showgrid": True,
                "gridcolor": PALETTE["grid"],
            },
            yaxis={
                "autorange": "reversed",
                "showgrid": False,
                "tickfont": {"size": 11.5, "color": PALETTE["ink"]},
            },
        )
    )
    return fig


def _build_over_index_figure(suppliers: list[dict[str, Any]]) -> go.Figure:
    fig = go.Figure()
    eligible = [
        s
        for s in suppliers
        if float(s.get("over_index_ratio", 0.0) or 0.0) > 0
        and float(s.get("demand_share_pct", 0.0) or 0.0) >= 0.2
    ]
    eligible.sort(key=lambda s: float(s.get("over_index_ratio", 0.0) or 0.0), reverse=True)
    top = eligible[:12]
    if not top:
        fig.update_layout(**plotly_base_layout(height=280))
        return fig

    labels = [_short_label(s.get("company_name") or s.get("party_id", ""), 22) for s in top]
    ratios = [float(s.get("over_index_ratio", 0.0) or 0.0) for s in top]
    colors = [
        PALETTE["vermilion"]
        if r >= 2.0
        else (PALETTE["amber"] if r >= 1.2 else PALETTE["teal"])
        for r in ratios
    ]
    custom = [
        [
            s.get("company_name") or s.get("party_id", ""),
            s.get("party_id", ""),
            float(s.get("comp_share_pct", 0.0) or 0.0),
            float(s.get("demand_share_pct", 0.0) or 0.0),
        ]
        for s in top
    ]

    fig.add_trace(
        go.Bar(
            y=labels,
            x=ratios,
            orientation="h",
            marker_color=colors,
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                "Over-index ratio: <b>%{x:.2f}x</b><br>"
                "Comp share: %{customdata[2]:.1f}% · Demand share: %{customdata[3]:.1f}%<extra></extra>"
            ),
        )
    )
    fig.add_vline(
        x=1.0,
        line_dash="dash",
        line_color=PALETTE["ink_muted"],
        line_width=1.2,
    )
    fig.add_annotation(
        x=1.0,
        y=1.02,
        yref="paper",
        text="1.0x fair share",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        xshift=6,
        font={"size": 10.5, "color": PALETTE["ink_secondary"]},
    )

    height = max(280, min(460, 68 + len(top) * 26))
    fig.update_layout(
        **plotly_base_layout(
            height=height,
            hovermode="closest",
            showlegend=False,
            margin={"l": 168, "r": 28, "t": 20, "b": 40},
            xaxis={
                "title": "Over-index ratio (Comp share ÷ Demand share)",
                "ticksuffix": "x",
                "showgrid": True,
                "gridcolor": PALETTE["grid"],
            },
            yaxis={
                "autorange": "reversed",
                "showgrid": False,
                "tickfont": {"size": 11.5, "color": PALETTE["ink"]},
            },
        )
    )
    return fig


def _render_supplier_ledger_table(
    suppliers: list[dict[str, Any]],
    filter_supplier: str,
) -> Any:
    if not suppliers:
        return html.P(
            "No supplier settlement records in the selected window.",
            style={"color": PALETTE["ink_muted"], "margin": "0"},
        )

    rows = []
    for s in suppliers:
        pid = str(s.get("party_id", ""))
        net_val = float(s.get("net_transfer_gbp", 0.0) or 0.0)
        over_idx = float(s.get("over_index_ratio", 0.0) or 0.0)

        if over_idx > 0:
            tone = "vermilion" if over_idx >= 2.0 else ("amber" if over_idx >= 1.2 else "neutral")
            over_cell: Any = badge(f"{over_idx:.2f}x", tone)
        else:
            over_cell = "—"

        rows.append(
            html.Tr(
                [
                    html.Td(
                        [
                            html.Div(
                                s.get("company_name") or pid,
                                style={"fontWeight": "600"},
                            ),
                            html.Div(
                                pid,
                                className="mono",
                                style={"fontSize": "11px", "color": PALETTE["ink_muted"]},
                            ),
                        ]
                    ),
                    html.Td(fmt_gbp(s.get("sccp_gbp", 0.0)), className="num"),
                    html.Td(fmt_gbp(s.get("scvp_gbp", 0.0)), className="num"),
                    html.Td(
                        fmt_signed_gbp(net_val),
                        className="num",
                        style={
                            "fontWeight": "600",
                            "color": PALETTE["teal"] if net_val >= 0 else PALETTE["vermilion"],
                        },
                    ),
                    html.Td(fmt_pct(s.get("demand_share_pct", 0.0), 1), className="num"),
                    html.Td(fmt_pct(s.get("comp_share_pct", 0.0), 1), className="num"),
                    html.Td(over_cell, className="num"),
                ],
                className="selected" if filter_supplier and filter_supplier == pid else "",
            )
        )

    return html.Div(
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Supplier (BSC Party)"),
                            html.Th("Received (sccp)", className="num"),
                            html.Th("Paid (scvp)", className="num"),
                            html.Th("Net transfer", className="num"),
                            html.Th("Demand %", className="num"),
                            html.Th("Comp %", className="num"),
                            html.Th("Over-index", className="num"),
                        ]
                    )
                ),
                html.Tbody(rows),
            ],
            className="data-table",
        ),
        className="table-scroll",
        style={"maxHeight": "480px", "overflowY": "auto"},
    )


def _render_flows_table(flows: list[dict[str, Any]]) -> Any:
    if not flows:
        return html.P(
            "No VTP → Supplier attribution flows match the current filters.",
            style={"color": PALETTE["ink_muted"], "margin": "0"},
        )

    rows = []
    for idx, f in enumerate(flows):
        sec_id = str(f.get("sec_party_id", ""))
        pri_id = str(f.get("pri_party_id", ""))
        rows.append(
            html.Tr(
                [
                    html.Td(
                        [
                            html.Div(
                                f.get("sec_company_name") or sec_id,
                                style={"fontWeight": "600"},
                            ),
                            html.Div(
                                sec_id,
                                className="mono",
                                style={"fontSize": "11px", "color": PALETTE["ink_muted"]},
                            ),
                        ]
                    ),
                    html.Td(
                        [
                            html.Div(f.get("pri_company_name") or pri_id),
                            html.Div(
                                pri_id,
                                className="mono",
                                style={"fontSize": "11px", "color": PALETTE["ink_muted"]},
                            ),
                        ]
                    ),
                    html.Td(fmt_num(f.get("bmu_pair_count", 0)), className="num"),
                    html.Td(fmt_num(f.get("qcv_mwh", 0.0), 1), className="num"),
                    html.Td(
                        fmt_gbp(f.get("comp_gbp", 0.0)),
                        className="num",
                        style={"fontWeight": "600"},
                    ),
                    html.Td(fmt_pct(f.get("share_of_vtp_pct", 0.0), 1), className="num"),
                    html.Td(
                        html.Button(
                            "Inspect →",
                            id={
                                "type": "nav-vtp-btn",
                                "target": "forensics",
                                "vtp": sec_id,
                                "idx": f"comp-flow-{idx}",
                            },
                            n_clicks=0,
                            className="btn btn-sm",
                            title=f"Inspect {sec_id} in EV Forensics Lab",
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
                            html.Th("VTP (Secondary)"),
                            html.Th("Supplier (Primary)"),
                            html.Th("BMU pairs", className="num"),
                            html.Th("QCV (MWh)", className="num"),
                            html.Th("Compensation", className="num"),
                            html.Th("Share of VTP", className="num"),
                            html.Th("", className="num"),
                        ]
                    )
                ),
                html.Tbody(rows),
            ],
            className="data-table",
        ),
        className="table-scroll",
        style={"maxHeight": "480px", "overflowY": "auto"},
    )


def _render_bm_only_section(
    vtps: list[dict[str, Any]],
    bm_only: list[dict[str, Any]],
    total_vtp_comp: float,
) -> Any:
    p415_qcv = sum(float(v.get("qcv_mwh", 0.0) or 0.0) for v in vtps)
    bm_qsd = sum(float(b.get("qsd_mwh", 0.0) or 0.0) for b in bm_only)

    split_strip = html.Div(
        [
            kpi_card(
                "P415 Wholesale VTP trading",
                fmt_mwh(p415_qcv, 1),
                sub=f"{len(vtps)} active VTPs · {fmt_gbp(total_vtp_comp, True)} supplier compensation",
                tone="teal",
            ),
            kpi_card(
                "BM-only VLP actions (qcv = 0)",
                fmt_mwh(bm_qsd, 1),
                sub=f"{len(bm_only)} VLP–host pairs · £0 P415 supplier compensation",
                tone="indigo",
            ),
        ],
        className="ledger-strip",
        style={"marginBottom": "16px"},
    )

    if not bm_only:
        return section_card(
            title="P415 Wholesale VTP vs Balancing Mechanism VLP split",
            subtitle=(
                "No non-P415 BM-only VLP actions (qsd ≠ 0, qcv = 0) recorded in the selected window."
            ),
            children=split_strip,
        )

    rows = [
        html.Tr(
            [
                html.Td(
                    [
                        html.Span(
                            b.get("sec_company_name") or b.get("sec_party_id", ""),
                            style={"fontWeight": "600"},
                        ),
                        " ",
                        html.Span(
                            b.get("sec_party_id", ""),
                            className="mono",
                            style={"fontSize": "11.5px", "color": PALETTE["ink_muted"]},
                        ),
                    ]
                ),
                html.Td(
                    [
                        html.Span(b.get("pri_company_name") or b.get("pri_party_id", "")),
                        " ",
                        html.Span(
                            b.get("pri_party_id", ""),
                            className="mono",
                            style={"fontSize": "11.5px", "color": PALETTE["ink_muted"]},
                        ),
                    ]
                ),
                html.Td(fmt_num(b.get("bmu_count", 0)), className="num"),
                html.Td(fmt_mwh(b.get("qsd_mwh", 0.0)), className="num"),
                html.Td("0.0 MWh", className="num"),
            ]
        )
        for b in bm_only[:10]
    ]

    table = html.Div(
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Secondary VLP"),
                            html.Th("Primary supplier / host"),
                            html.Th("SBMUs", className="num"),
                            html.Th("Delivered BM volume (qsd)", className="num"),
                            html.Th("P415 QCV", className="num"),
                        ]
                    )
                ),
                html.Tbody(rows),
            ],
            className="data-table",
        ),
        className="table-scroll",
    )

    return section_card(
        title="Distinction: P415 Wholesale VTP vs Balancing Mechanism VLP actions",
        subtitle=(
            "Secondary BMU pairs with delivered BM volume (qsd ≠ 0) but zero wholesale compensation "
            "volume (qcv = 0) — typically grid-scale batteries or BM dispatch outside P415 wholesale trading."
        ),
        children=[split_strip, table],
    )


def render_compensation(
    data: dict[str, Any] | None,
    filter_vtp: str = "",
    filter_supplier: str = "",
) -> html.Div:
    """Render the Compensation tab (filters, £0.00 reconciliation KPIs, diverging transfer & over-index charts, tables)."""
    data = data or {}
    totals = data.get("totals") or {}
    suppliers = data.get("suppliers") or []
    vtps = data.get("vtps") or []
    flows = data.get("flows") or []
    bm_only = data.get("bm_only_vlp_activity") or []
    start_date = str(data.get("start_date") or "")
    end_date = str(data.get("end_date") or "")

    vtp_options = [{"label": "All VTPs", "value": ""}] + [
        {
            "label": f"{v.get('company_name') or v.get('party_id')} ({v.get('party_id')})",
            "value": str(v.get("party_id", "")),
        }
        for v in vtps
    ]
    if filter_vtp and not any(o["value"] == filter_vtp for o in vtp_options):
        vtp_options.append({"label": filter_vtp, "value": filter_vtp})

    supplier_options = [{"label": "All Suppliers", "value": ""}] + [
        {
            "label": f"{s.get('company_name') or s.get('party_id')} ({s.get('party_id')})",
            "value": str(s.get("party_id", "")),
        }
        for s in suppliers
    ]
    if filter_supplier and not any(o["value"] == filter_supplier for o in supplier_options):
        supplier_options.append({"label": filter_supplier, "value": filter_supplier})

    header = html.Div(
        [
            html.Div(
                [
                    html.H1(
                        "Who receives supplier compensation — and who pays",
                        className="page-title",
                    ),
                    html.P(
                        "Under BSC P415, affected suppliers receive Supplier Compensation Cashflow (sccp) "
                        "funded via a market-wide mutualised levy (scvp) across all GB suppliers in proportion to demand.",
                        className="page-lead",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label(
                                "VTP",
                                htmlFor="comp-vtp-select",
                                style={
                                    "fontSize": "12px",
                                    "color": PALETTE["ink_secondary"],
                                    "fontWeight": "600",
                                },
                            ),
                            dcc.Dropdown(
                                id="comp-vtp-select",
                                options=vtp_options,
                                value=filter_vtp or "",
                                clearable=False,
                                searchable=True,
                                style={"minWidth": "220px"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "gap": "6px"},
                    ),
                    html.Div(
                        [
                            html.Label(
                                "Supplier",
                                htmlFor="comp-supplier-select",
                                style={
                                    "fontSize": "12px",
                                    "color": PALETTE["ink_secondary"],
                                    "fontWeight": "600",
                                },
                            ),
                            dcc.Dropdown(
                                id="comp-supplier-select",
                                options=supplier_options,
                                value=filter_supplier or "",
                                clearable=False,
                                searchable=True,
                                style={"minWidth": "220px"},
                            ),
                        ],
                        style={"display": "flex", "alignItems": "center", "gap": "6px"},
                    ),
                ],
                className="filter-bar",
                style={"marginBottom": "0"},
            ),
        ],
        className="page-header",
    )

    if not suppliers and not flows and not vtps:
        return html.Div(
            [
                header,
                empty_state(
                    "No compensation data in selected window",
                    f"No supplier compensation or mutualisation records were found between {start_date or 'start'} and {end_date or 'end'}.",
                    action=html.Button(
                        "Fetch Elexon dates",
                        id={"type": "open-sync-btn", "idx": "comp-empty"},
                        n_clicks=0,
                        className="btn btn-teal",
                    ),
                ),
            ]
        )

    total_pos_sccp = float(totals.get("total_pos_sccp_gbp", 0.0) or 0.0)
    total_scvp = float(totals.get("total_scvp_gbp", 0.0) or 0.0)
    total_vtp_comp = float(totals.get("total_vtp_comp_gbp", 0.0) or 0.0)
    net_mutualisation = sum(float(s.get("net_transfer_gbp", 0.0) or 0.0) for s in suppliers)
    recon_diff = abs(total_vtp_comp - total_scvp) if not (filter_vtp or filter_supplier) else abs(net_mutualisation)

    kpi_strip = html.Section(
        [
            kpi_card(
                "Supplier compensation (sccp)",
                fmt_gbp(total_pos_sccp, compact=True),
                sub=f"Exact positive sccp: {fmt_gbp_exact(total_pos_sccp)}",
                tone="teal",
            ),
            kpi_card(
                "Mutualised levy paid (scvp)",
                fmt_gbp(total_scvp, compact=True),
                sub=f"Recovered across {len(suppliers)} GB suppliers",
            ),
            kpi_card(
                "VTP BMU-attributed total",
                fmt_gbp(total_vtp_comp, compact=True),
                sub=f"{len(vtps)} active VTPs · {len(flows)} attribution flows",
                tone="indigo",
            ),
            kpi_card(
                "Mutualisation reconciliation",
                fmt_gbp_exact(0.0 if recon_diff < 0.05 else recon_diff),
                sub=(
                    "Exact £0.00 zero-sum mutualised pot"
                    if recon_diff < 0.05
                    else f"Filtered / net ledger variance ({fmt_signed_gbp(net_mutualisation)})"
                ),
                tone="teal" if recon_diff < 0.05 else "amber",
            ),
        ],
        className="ledger-strip",
    )

    charts_grid = html.Div(
        [
            section_card(
                title="Net mutualisation transfer by supplier (sccp − scvp)",
                subtitle=(
                    "Suppliers with large smart-EV customer bases receive multiples of their demand share; "
                    "commercial/I&C and non-EV suppliers subsidise the mutualised pot."
                ),
                actions=[
                    badge("Net recipient (+£)", "teal"),
                    badge("Net contributor (-£)", "vermilion"),
                ],
                children=dcc.Graph(
                    id="comp-diverging-chart",
                    figure=_build_diverging_transfer_figure(suppliers),
                    config=PLOTLY_CONFIG,
                ),
            ),
            section_card(
                title="Supplier over-index ratio (Comp % ÷ Demand %)",
                subtitle=(
                    "Values above 1.0x indicate a supplier receives more P415 compensation than its GB "
                    "demand share (shown for suppliers with ≥0.2% demand share)."
                ),
                actions=[
                    badge("≥2.0x high over-index", "vermilion"),
                    badge("1.2–2.0x elevated", "amber"),
                ],
                children=dcc.Graph(
                    id="comp-over-index-chart",
                    figure=_build_over_index_figure(suppliers),
                    config=PLOTLY_CONFIG,
                ),
            ),
        ],
        className="grid-asymmetric",
    )

    ledger_panel = section_card(
        title="GB supplier compensation & over-index ledger",
        subtitle=(
            "Full party-level reconciliation of sccp received, scvp mutualised levy paid, and over-index "
            "ratio (Comp share ÷ GB demand share)."
        ),
        children=_render_supplier_ledger_table(suppliers, filter_supplier),
    )

    filter_tags = []
    if filter_vtp:
        filter_tags.append(f"VTP: {filter_vtp}")
    if filter_supplier:
        filter_tags.append(f"Supplier: {filter_supplier}")
    filter_desc = f" · {', '.join(filter_tags)}" if filter_tags else ""

    flows_panel = section_card(
        title="VTP → Supplier attribution flows",
        subtitle=f"Exact Primary × Secondary BMU-pair aggregation ({len(flows)} active pairs{filter_desc})",
        children=_render_flows_table(flows),
    )

    bm_split_panel = _render_bm_only_section(vtps, bm_only, total_vtp_comp)

    return html.Div(
        [
            header,
            kpi_strip,
            charts_grid,
            ledger_panel,
            flows_panel,
            bm_split_panel,
        ]
    )
