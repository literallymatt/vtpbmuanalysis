"""Timing view: half-hourly SP 1–48 trading profile, Day × 48-SP heatmap, weekday/weekend & VTP schedules."""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from dash import dcc, html

from ..formatting import (
    PALETTE,
    PLOTLY_CONFIG,
    badge,
    empty_state,
    fmt_mwh,
    fmt_mw,
    fmt_num,
    fmt_pct,
    kpi_card,
    plotly_base_layout,
    section_card,
    sp_to_time,
)

VTP_COLORS = [
    PALETTE["teal"],
    PALETTE["indigo"],
    PALETTE["vermilion"],
    PALETTE["amber"],
    "#6d4c9e",
    "#2d8a4e",
]


def _build_intraday_figure(intraday: list[dict[str, Any]]) -> go.Figure:
    fig = go.Figure()
    if not intraday:
        fig.update_layout(**plotly_base_layout(height=340))
        return fig

    times = [row["time"] for row in intraday]
    pos_mwh = [float(row.get("avg_pos_mwh", 0.0) or 0.0) for row in intraday]
    neg_mwh = [float(row.get("avg_neg_mwh", 0.0) or 0.0) for row in intraday]
    sbp = [float(row.get("avg_sbp", 0.0) or 0.0) for row in intraday]
    mpj = [float(row.get("avg_mpj", 0.0) or 0.0) for row in intraday]
    ssc = [float(row.get("avg_ssc", 0.0) or 0.0) for row in intraday]

    # Shaded 00:00–05:30 (SP 1–11) and 23:30–00:00 (SP 48) EV off-peak windows
    if len(times) >= 11:
        fig.add_vrect(
            x0=times[0],
            x1=times[10],
            fillcolor="rgba(44, 92, 197, 0.08)",
            line_width=0,
            layer="below",
            annotation_text="00:00–05:30 EV off-peak",
            annotation_position="top left",
            annotation_font={"size": 10.5, "color": PALETTE["indigo"]},
        )
    if len(times) >= 48:
        fig.add_vrect(
            x0=times[46],
            x1=times[47],
            fillcolor="rgba(44, 92, 197, 0.08)",
            line_width=0,
            layer="below",
        )

    fig.add_trace(
        go.Bar(
            x=times,
            y=pos_mwh,
            name="Turn-down QCV (+MWh)",
            marker_color=PALETTE["teal"],
            hovertemplate="%{y:.2f} MWh/SP<extra>Turn-down QCV</extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=times,
            y=neg_mwh,
            name="Turn-up QCV (-MWh)",
            marker_color=PALETTE["vermilion"],
            hovertemplate="%{y:.2f} MWh/SP<extra>Turn-up QCV</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=sbp,
            name="Avg System Buy Price (SBP)",
            yaxis="y2",
            mode="lines",
            line={"color": PALETTE["amber"], "width": 2.2},
            hovertemplate="£%{y:.2f}/MWh<extra>Avg SBP</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=mpj,
            name="Avg Market Price (MIDP)",
            yaxis="y2",
            mode="lines",
            line={"color": PALETTE["indigo"], "width": 1.7, "dash": "dash"},
            hovertemplate="£%{y:.2f}/MWh<extra>Avg MIDP</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=ssc,
            name="Supplier Sourcing Cost (SSC)",
            yaxis="y2",
            mode="lines",
            line={"color": PALETTE["ink_muted"], "width": 1.6, "dash": "dot"},
            hovertemplate="£%{y:.2f}/MWh<extra>Avg SSC</extra>",
        )
    )

    fig.update_layout(
        **plotly_base_layout(
            height=340,
            barmode="relative",
            margin={"l": 64, "r": 64, "t": 40, "b": 44},
            xaxis={
                "title": "Settlement period start (HH:MM)",
                "dtick": 4,
            },
            yaxis={
                "title": "Volume (MWh / SP)",
                "ticksuffix": " MWh",
                "tickfont": {"size": 11, "color": PALETTE["teal"]},
                "title_font": {"size": 11.5, "color": PALETTE["teal"]},
            },
            yaxis2={
                "title": "Wholesale price (£/MWh)",
                "overlaying": "y",
                "side": "right",
                "showgrid": False,
                "zeroline": False,
                "tickprefix": "£",
                "tickfont": {"size": 11, "color": PALETTE["amber"]},
                "title_font": {"size": 11.5, "color": PALETTE["amber"]},
            },
        )
    )
    return fig


def _build_heatmap_figure(
    heatmap: list[dict[str, Any]],
    max_cell_mwh: float,
) -> go.Figure:
    fig = go.Figure()
    if not heatmap:
        fig.update_layout(**plotly_base_layout(height=280))
        return fig

    x_labels = [sp_to_time(sp) for sp in range(1, 49)]
    y_labels = [
        f"{row['date']} ({row['dow']}) · £{float(row.get('avg_sbp', 0.0) or 0.0):.0f}"
        for row in heatmap
    ]

    z_rows: list[list[float]] = []
    custom_rows: list[list[list[Any]]] = []
    for row in heatmap:
        cells = row.get("cells") or []
        cell_by_sp = {int(c["sp"]): c for c in cells}
        z_line: list[float] = []
        c_line: list[list[Any]] = []
        day_total = float(row.get("total_qcv_mwh", 0.0) or 0.0)
        for sp in range(1, 49):
            c = cell_by_sp.get(sp, {"qcv_mwh": 0.0, "comp_gbp": 0.0, "sbp": 0.0})
            qcv = float(c.get("qcv_mwh", 0.0) or 0.0)
            z_line.append(qcv)
            c_line.append(
                [
                    row["date"],
                    row["dow"],
                    sp,
                    sp_to_time(sp),
                    float(c.get("comp_gbp", 0.0) or 0.0),
                    float(c.get("sbp", 0.0) or 0.0),
                    day_total,
                ]
            )
        z_rows.append(z_line)
        custom_rows.append(c_line)

    bound = max(1.0, float(max_cell_mwh or 0.0))
    colorscale = [
        [0.0, PALETTE["vermilion"]],
        [0.45, "#f7cfc6"],
        [0.5, "#f2f5f8"],
        [0.55, "#c5e7e5"],
        [1.0, PALETTE["teal"]],
    ]

    fig.add_trace(
        go.Heatmap(
            x=x_labels,
            y=y_labels,
            z=z_rows,
            customdata=custom_rows,
            zmin=-bound,
            zmax=bound,
            zmid=0.0,
            colorscale=colorscale,
            xgap=1,
            ygap=1,
            colorbar={
                "title": {"text": "QCV (MWh)", "font": {"size": 11}},
                "thickness": 12,
                "len": 0.85,
                "tickfont": {"size": 10.5},
            },
            hovertemplate=(
                "<b>%{customdata[0]} (%{customdata[1]})</b> · SP %{customdata[2]:02d} (%{customdata[3]})<br>"
                "QCV: <b>%{z:.2f} MWh</b><br>"
                "Compensation: £%{customdata[4]:,.0f}<br>"
                "SBP: £%{customdata[5]:.1f}/MWh<br>"
                "Day total: %{customdata[6]:,.1f} MWh<extra></extra>"
            ),
        )
    )

    chart_height = max(280, min(680, 120 + len(heatmap) * 16))
    fig.update_layout(
        **plotly_base_layout(
            height=chart_height,
            hovermode="closest",
            margin={"l": 148, "r": 24, "t": 20, "b": 42},
            xaxis={
                "title": "Settlement period start (HH:MM)",
                "dtick": 4,
                "showgrid": False,
            },
            yaxis={
                "title": None,
                "autorange": "reversed",
                "showgrid": False,
                "tickfont": {"size": 10.5, "color": PALETTE["ink_secondary"]},
            },
        )
    )
    return fig


def _build_vtp_curves_figure(vtp_profiles: list[dict[str, Any]]) -> go.Figure:
    fig = go.Figure()
    times = [sp_to_time(sp) for sp in range(1, 49)]
    for idx, vp in enumerate(vtp_profiles):
        vals = vp.get("avg_sp_mwh") or [0.0] * 48
        label = f"{vp.get('company_name') or vp.get('party_id')} ({vp.get('party_id')})"
        fig.add_trace(
            go.Scatter(
                x=times,
                y=vals,
                name=label,
                mode="lines",
                line={"color": VTP_COLORS[idx % len(VTP_COLORS)], "width": 2.0},
                hovertemplate="%{y:.2f} MWh/SP<extra>" + label + "</extra>",
            )
        )
    fig.update_layout(
        **plotly_base_layout(
            height=280,
            margin={"l": 58, "r": 16, "t": 44, "b": 40},
            xaxis={"dtick": 6},
            yaxis={"ticksuffix": " MWh"},
        )
    )
    return fig


def _build_weekday_weekend_figure(intraday: list[dict[str, Any]]) -> go.Figure:
    fig = go.Figure()
    if not intraday:
        fig.update_layout(**plotly_base_layout(height=280))
        return fig

    times = [row["time"] for row in intraday]
    wkday = [float(row.get("avg_weekday_mwh", 0.0) or 0.0) for row in intraday]
    wkend = [float(row.get("avg_weekend_mwh", 0.0) or 0.0) for row in intraday]

    fig.add_trace(
        go.Scatter(
            x=times,
            y=wkday,
            name="Working days (Mon–Fri)",
            mode="lines",
            line={"color": PALETTE["teal"], "width": 2.1},
            hovertemplate="%{y:.2f} MWh/SP<extra>Working days</extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times,
            y=wkend,
            name="Non-working days (Sat–Sun)",
            mode="lines",
            line={"color": PALETTE["indigo"], "width": 2.0, "dash": "dash"},
            hovertemplate="%{y:.2f} MWh/SP<extra>Non-working days</extra>",
        )
    )
    fig.update_layout(
        **plotly_base_layout(
            height=280,
            margin={"l": 58, "r": 16, "t": 44, "b": 40},
            xaxis={"dtick": 6},
            yaxis={"ticksuffix": " MWh"},
        )
    )
    return fig


def _render_vtp_schedule_table(vtp_profiles: list[dict[str, Any]]) -> Any:
    if not vtp_profiles:
        return html.P(
            "No VTP intraday schedules available for this filter.",
            style={"color": PALETTE["ink_muted"], "margin": "0"},
        )

    rows = []
    for idx, vp in enumerate(vtp_profiles):
        party_id = str(vp.get("party_id", ""))
        vals = [float(x or 0.0) for x in (vp.get("avg_sp_mwh") or [])]
        if not vals:
            continue
        daily_mwh = sum(vals)
        peak_idx = max(range(len(vals)), key=lambda i: abs(vals[i]))
        peak_sp = peak_idx + 1
        peak_val = vals[peak_idx]
        offpeak_mwh = sum(max(0.0, vals[i]) for i in range(len(vals)) if (i + 1) <= 11 or (i + 1) == 48)
        day_mwh = sum(max(0.0, vals[i]) for i in range(len(vals)) if 12 <= (i + 1) <= 47)
        tot_pos = offpeak_mwh + day_mwh
        day_pct = (day_mwh / tot_pos * 100.0) if tot_pos > 1e-6 else 0.0
        offpeak_pct = (offpeak_mwh / tot_pos * 100.0) if tot_pos > 1e-6 else 0.0
        active_sps = sum(1 for v in vals if abs(v) > 0.05)

        rows.append(
            html.Tr(
                [
                    html.Td(
                        [
                            html.Div(
                                vp.get("company_name") or party_id,
                                style={"fontWeight": "600"},
                            ),
                            html.Div(
                                party_id,
                                className="mono",
                                style={"fontSize": "11.5px", "color": PALETTE["ink_muted"]},
                            ),
                        ]
                    ),
                    html.Td(fmt_mwh(daily_mwh, 1), className="num", style={"fontWeight": "600"}),
                    html.Td(f"{sp_to_time(peak_sp)} (SP {peak_sp:02d})", className="num"),
                    html.Td(
                        f"{fmt_mwh(peak_val, 2)} (~{fmt_mw(peak_val * 2.0, 1)})",
                        className="num",
                    ),
                    html.Td(fmt_pct(day_pct, 1), className="num"),
                    html.Td(fmt_pct(offpeak_pct, 1), className="num"),
                    html.Td(f"{fmt_num(active_sps)} / 48", className="num"),
                    html.Td(
                        html.Button(
                            "Forensics →",
                            id={
                                "type": "nav-vtp-btn",
                                "target": "forensics",
                                "vtp": party_id,
                                "idx": f"timing-vtp-{idx}",
                            },
                            n_clicks=0,
                            className="btn btn-sm",
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
                            html.Th("Avg daily QCV", className="num"),
                            html.Th("Peak SP", className="num"),
                            html.Th("Peak SP volume", className="num"),
                            html.Th("05:30–23:30 share", className="num"),
                            html.Th("EV off-peak share", className="num"),
                            html.Th("Active SPs", className="num"),
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


def render_timing(data: dict[str, Any] | None, selected_vtp: str = "") -> html.Div:
    """Render the Timing tab (VTP selector, 48-SP profile, Day × 48-SP heatmap, weekday/weekend, VTP summary)."""
    data = data or {}
    intraday = data.get("intraday") or []
    heatmap = data.get("heatmap") or []
    vtp_profiles = data.get("vtp_profiles") or []
    vtp_choices = data.get("vtp_choices") or []
    granular_days = int(data.get("granular_days", 0) or 0)
    start_date = str(data.get("start_date") or "")
    end_date = str(data.get("end_date") or "")
    max_cell_mwh = float(data.get("max_cell_mwh", 0.0) or 0.0)

    vtp_options = [{"label": "All active VTPs", "value": ""}] + [
        {
            "label": f"{v.get('company_name') or v.get('party_id')} ({v.get('party_id')})",
            "value": str(v.get("party_id", "")),
        }
        for v in vtp_choices
    ]
    if selected_vtp and not any(o["value"] == selected_vtp for o in vtp_options):
        vtp_options.append({"label": selected_vtp, "value": selected_vtp})

    header = html.Div(
        [
            html.Div(
                [
                    html.H1("When Virtual Trading Parties trade", className="page-title"),
                    html.P(
                        "Half-hourly settlement period (SP 1–48) trading footprint overlaid against GB wholesale "
                        "prices, System Buy Price, and the 23:30–05:30 domestic EV off-peak tariff window.",
                        className="page-lead",
                    ),
                ]
            ),
            html.Div(
                [
                    html.Label(
                        "Filter VTP",
                        htmlFor="timing-vtp-select",
                        style={"fontSize": "12.5px", "color": PALETTE["ink_secondary"], "fontWeight": "600"},
                    ),
                    dcc.Dropdown(
                        id="timing-vtp-select",
                        options=vtp_options,
                        value=selected_vtp or "",
                        clearable=False,
                        searchable=True,
                        style={"minWidth": "270px"},
                    ),
                ],
                className="filter-bar",
                style={"marginBottom": "0"},
            ),
        ],
        className="page-header",
    )

    if granular_days == 0 or not intraday:
        return html.Div(
            [
                header,
                empty_state(
                    "No half-hourly timing data in selected window",
                    f"No granular BMU × SP records were found between {start_date or 'start'} and {end_date or 'end'}.",
                    action=html.Button(
                        "Fetch Elexon dates",
                        id={"type": "open-sync-btn", "idx": "timing-empty"},
                        n_clicks=0,
                        className="btn btn-teal",
                    ),
                ),
            ]
        )

    night_vol = sum(float(x.get("avg_pos_mwh", 0.0) or 0.0) for x in intraday if x.get("is_ev_offpeak"))
    day_vol = sum(float(x.get("avg_pos_mwh", 0.0) or 0.0) for x in intraday if not x.get("is_ev_offpeak"))
    tot_vol = max(0.01, day_vol + night_vol)
    peak_sp = max(intraday, key=lambda x: float(x.get("avg_pos_mwh", 0.0) or 0.0))
    peak_pos = float(peak_sp.get("avg_pos_mwh", 0.0) or 0.0)

    kpi_strip = html.Section(
        [
            kpi_card(
                "Peak half-hour (avg)",
                [
                    str(peak_sp.get("time", "00:00")),
                    html.Span(
                        f" SP {int(peak_sp.get('sp', 1))}",
                        style={"fontSize": "13px", "color": PALETTE["ink_muted"]},
                    ),
                ],
                sub=f"{fmt_mwh(peak_pos)}/SP (~{peak_pos * 2.0:.0f} MW avg)",
                tone="teal",
            ),
            kpi_card(
                "05:30–23:30 daytime/evening",
                fmt_mwh(day_vol, 0),
                sub=f"{day_vol / tot_vol * 100.0:.1f}% of daily turn-down",
            ),
            kpi_card(
                "23:30–05:30 EV off-peak window",
                fmt_mwh(night_vol, 1),
                sub=f"{night_vol / tot_vol * 100.0:.1f}% of daily turn-down",
            ),
            kpi_card(
                "Granular days analysed",
                str(granular_days),
                sub=f"{start_date} to {end_date}",
            ),
        ],
        className="ledger-strip",
    )

    intraday_panel = section_card(
        title="Average intraday VTP volume (MWh/SP) vs System Buy Price and Market Price",
        subtitle=(
            "Shaded bands mark 23:30–05:30 (SP 48 & SP 1–11), matching Intelligent Octopus Go / Next Drive "
            "cheap EV charging windows. Positive bars = claimed demand turn-down; negative bars = turn-up."
        ),
        actions=badge("Shaded: 23:30–05:30 EV off-peak", "indigo"),
        children=dcc.Graph(
            id="timing-intraday-chart",
            figure=_build_intraday_figure(intraday),
            config=PLOTLY_CONFIG,
        ),
    )

    heatmap_panel = section_card(
        title="Daily × 48-settlement-period trading heatmap",
        subtitle=(
            "Every row is a settled day with its daily average SBP shown on the left axis. Hover any half-hour "
            "cell to inspect exact QCV (MWh), compensation (£), and SBP (£/MWh)."
        ),
        actions=[
            badge("Teal: turn-down (+MWh)", "teal"),
            badge("Vermilion: turn-up (-MWh)", "vermilion"),
        ],
        children=(
            dcc.Graph(
                id="timing-heatmap-chart",
                figure=_build_heatmap_figure(heatmap, max_cell_mwh),
                config=PLOTLY_CONFIG,
            )
            if heatmap
            else html.P(
                "No daily heatmap rows available.",
                style={"color": PALETTE["ink_muted"], "margin": "0"},
            )
        ),
    )

    comparison_grid = html.Div(
        [
            section_card(
                title="Trading schedules by VTP (top 6)",
                subtitle=(
                    "Compare continuous daytime schedules against evening-only blocks and overnight windows."
                ),
                children=(
                    dcc.Graph(
                        id="timing-vtp-curves-chart",
                        figure=_build_vtp_curves_figure(vtp_profiles),
                        config=PLOTLY_CONFIG,
                    )
                    if vtp_profiles
                    else html.P(
                        "No VTP profiles available.",
                        style={"color": PALETTE["ink_muted"], "margin": "0"},
                    )
                ),
            ),
            section_card(
                title="Weekday vs weekend profile",
                subtitle="Tests whether VTPs separate BL01 working-day vs non-working-day baselines",
                children=dcc.Graph(
                    id="timing-weekday-weekend-chart",
                    figure=_build_weekday_weekend_figure(intraday),
                    config=PLOTLY_CONFIG,
                ),
            ),
        ],
        className="grid-2",
    )

    schedule_table_panel = section_card(
        title="Per-VTP schedule summary",
        subtitle=(
            "Daily average QCV, peak settlement period, daytime vs EV off-peak split, and active half-hour "
            "duty cycle for top active VTPs."
        ),
        children=_render_vtp_schedule_table(vtp_profiles),
    )

    return html.Div(
        [
            header,
            kpi_strip,
            intraday_panel,
            heatmap_panel,
            comparison_grid,
            schedule_table_panel,
        ]
    )
