"""BMU × Settlement Period Explorer & BSC Party Registry view."""

from __future__ import annotations

from typing import Any

from dash import dcc, html

from py_dashboard.formatting import (
    PALETTE,
    badge,
    empty_state,
    fmt_gbp,
    section_card,
    sp_to_time,
)

GSP_LIST: tuple[str, ...] = (
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "G",
    "H",
    "J",
    "K",
    "L",
    "M",
    "N",
    "P",
)

ROLE_OPTIONS: list[dict[str, str]] = [
    {"label": "All BSC roles", "value": ""},
    {"label": "VT — Virtual Trading Party", "value": "VT"},
    {"label": "VP — Virtual Lead Party", "value": "VP"},
    {"label": "AV — Asset Metering VLP", "value": "AV"},
    {"label": "TS — Licensed Supplier", "value": "TS"},
    {"label": "TG — Generator", "value": "TG"},
]


def render_explorer_shell(
    start_date: str,
    end_date: str,
    state: dict[str, Any] | None = None,
) -> html.Div:
    """Render the Explorer filter shell and placeholder for live results."""
    st = state or {}
    group_by = st.get("group_by") if st.get("group_by") in ("bmu_pair", "raw") else "bmu_pair"
    vtp_val = st.get("sec_party_id") or ""
    sup_val = st.get("pri_party_id") or ""
    gsp_val = st.get("gsp_group") or ""
    sp_val = st.get("sp") if st.get("sp") not in (None, "") else ""
    search_val = st.get("search") or ""
    party_role_val = st.get("party_role") if "party_role" in st else "VT"
    party_search_val = st.get("party_search") or ""

    gsp_options = [{"label": "All GSP groups", "value": ""}] + [
        {"label": f"GSP _{g}", "value": g} for g in GSP_LIST
    ]
    sp_options = [{"label": "All SPs (1–50)", "value": ""}] + [
        {"label": f"SP {sp:02d} ({sp_to_time(sp)})", "value": str(sp)}
        for sp in range(1, 51)
    ]

    header = html.Div(
        [
            html.Div(
                [
                    html.H1(
                        "BMU × Settlement Period explorer & BSC party registry",
                        className="page-title",
                    ),
                    html.P(
                        "Inspect raw Primary/Secondary BMU records from SAA-I014 or search the "
                        "Elexon BSC Signatories directory (Party ID → Company Name and registered market roles).",
                        className="page-lead",
                    ),
                ]
            ),
            html.Div(
                [
                    badge(f"{start_date} → {end_date}", "neutral"),
                    html.Button(
                        "Export CSV",
                        id="explorer-export-csv-btn",
                        n_clicks=0,
                        className="btn btn-sm btn-teal",
                    ),
                ],
                className="header-actions",
            ),
        ],
        className="page-header",
    )

    bmu_filters = html.Div(
        [
            html.Div(
                [
                    html.Label("Aggregation:", htmlFor="explorer-group-by"),
                    dcc.RadioItems(
                        id="explorer-group-by",
                        options=[
                            {"label": "BMU pairs (aggregated)", "value": "bmu_pair"},
                            {"label": "Raw BMU × SP rows", "value": "raw"},
                        ],
                        value=group_by,
                        inline=True,
                        className="explorer-radio-group",
                        inputStyle={"marginRight": "5px"},
                        labelStyle={"marginRight": "14px", "fontSize": "12.5px", "fontWeight": 500},
                    ),
                ],
                style={"display": "flex", "alignItems": "center", "gap": "8px", "flexWrap": "wrap"},
            ),
            dcc.Input(
                id="explorer-search-input",
                type="search",
                value=search_val,
                debounce=True,
                placeholder="Search BMU ID or Party ID (e.g. V__AAXLE001, MERCURY)...",
                className="input",
                style={"minWidth": "260px", "flex": "1 1 240px"},
            ),
            dcc.Input(
                id="explorer-vtp-input",
                type="text",
                value=vtp_val,
                debounce=True,
                placeholder="VTP ID (e.g. AXLE0001)",
                className="input mono",
                style={"width": "155px"},
            ),
            dcc.Input(
                id="explorer-supplier-input",
                type="text",
                value=sup_val,
                debounce=True,
                placeholder="Supplier ID (e.g. MERCURY)",
                className="input mono",
                style={"width": "165px"},
            ),
            html.Div(
                dcc.Dropdown(
                    id="explorer-gsp-select",
                    options=gsp_options,
                    value=gsp_val,
                    clearable=False,
                    placeholder="All GSP groups",
                ),
                style={"minWidth": "145px"},
            ),
            html.Div(
                dcc.Dropdown(
                    id="explorer-sp-select",
                    options=sp_options,
                    value=str(sp_val) if sp_val != "" else "",
                    clearable=False,
                    placeholder="All SPs (1–50)",
                ),
                style={"minWidth": "155px"},
            ),
        ],
        className="filter-bar",
    )

    party_filters = html.Div(
        [
            html.Span(
                "BSC Signatories filters:",
                style={"fontSize": "12px", "fontWeight": 600, "color": PALETTE["ink_secondary"]},
            ),
            html.Div(
                dcc.Dropdown(
                    id="explorer-party-role-select",
                    options=ROLE_OPTIONS,
                    value=party_role_val,
                    clearable=False,
                    placeholder="Filter BSC role",
                ),
                style={"minWidth": "230px"},
            ),
            dcc.Input(
                id="explorer-party-search-input",
                type="search",
                value=party_search_val,
                debounce=True,
                placeholder="Search Party ID or company name...",
                className="input",
                style={"minWidth": "240px", "flex": "0 1 320px"},
            ),
        ],
        className="filter-bar",
        style={"marginTop": "-4px"},
    )

    return html.Div(
        [
            header,
            bmu_filters,
            party_filters,
            html.Div(id="explorer-results-container"),
        ]
    )


def render_explorer_results(
    data: dict[str, Any],
    parties_data: dict[str, Any],
    state: dict[str, Any],
) -> html.Div:
    """Render paginated BMU × SP records table and BSC Signatories registry table."""
    mode = data.get("group_by") or state.get("group_by") or "bmu_pair"
    total = int(data.get("total") or 0)
    limit = int(data.get("limit") or state.get("limit") or 200)
    offset = int(data.get("offset") or 0)
    items: list[dict[str, Any]] = data.get("items") or []

    start_row = offset + 1 if total > 0 else 0
    end_row = min(offset + limit, total)
    has_prev = offset > 0
    has_next = offset + limit < total

    pagination_controls = html.Div(
        [
            html.Button(
                "Previous",
                id={"type": "explorer-page-btn", "dir": "prev"},
                n_clicks=0,
                disabled=not has_prev,
                className="btn btn-sm",
            ),
            html.Span(
                f"{start_row:,}–{end_row:,} of {total:,}" if total > 0 else "0 results",
                className="mono",
                style={"fontSize": "12px", "color": PALETTE["ink_secondary"]},
            ),
            html.Button(
                "Next",
                id={"type": "explorer-page-btn", "dir": "next"},
                n_clicks=0,
                disabled=not has_next,
                className="btn btn-sm",
            ),
        ],
        style={"display": "flex", "gap": "8px", "alignItems": "center"},
    )

    if mode == "raw":
        bmu_thead = html.Tr(
            [
                html.Th("Date"),
                html.Th("SP"),
                html.Th("Secondary BMU (VTP)"),
                html.Th("Primary BMU (Supplier)"),
                html.Th("GSP"),
                html.Th("QSD (MWh)", className="num"),
                html.Th("QCV (MWh)", className="num"),
                html.Th("SSC", className="num"),
                html.Th("Comp (£)", className="num"),
            ]
        )
        bmu_rows = [
            html.Tr(
                [
                    html.Td(r.get("settlement_date", ""), className="mono"),
                    html.Td(
                        f"{int(r.get('sp') or 0):02d} ({r.get('time') or sp_to_time(int(r.get('sp') or 1))})",
                        className="mono",
                    ),
                    html.Td(
                        [
                            html.Span(r.get("sec_bmu_id", ""), className="mono", style={"fontWeight": 600}),
                            " ",
                            html.Span(
                                r.get("sec_party_id", ""),
                                style={"fontSize": "11.5px", "color": PALETTE["ink_muted"]},
                            ),
                        ]
                    ),
                    html.Td(
                        [
                            html.Span(r.get("pri_bmu_id", ""), className="mono", style={"fontWeight": 600}),
                            " ",
                            html.Span(
                                r.get("pri_party_id", ""),
                                style={"fontSize": "11.5px", "color": PALETTE["ink_muted"]},
                            ),
                        ]
                    ),
                    html.Td(badge(f"_{r.get('gsp_group', '')}", "neutral")),
                    html.Td(f"{float(r.get('qsd_mwh') or 0):.3f}", className="num"),
                    html.Td(f"{float(r.get('qcv_mwh') or 0):.3f}", className="num"),
                    html.Td(f"£{float(r.get('ssc') or 0):.2f}", className="num"),
                    html.Td(
                        fmt_gbp(r.get("comp_gbp")),
                        className="num",
                        style={"fontWeight": 600},
                    ),
                ]
            )
            for r in items
        ]
        bmu_title = f"Raw BMU × SP records ({total:,} total)"
    else:
        bmu_thead = html.Tr(
            [
                html.Th("Secondary BMU (VTP)"),
                html.Th("Primary BMU (Supplier)"),
                html.Th("GSP"),
                html.Th("Days", className="num"),
                html.Th("Active SPs", className="num"),
                html.Th("QSD (MWh)", className="num"),
                html.Th("QCV (MWh)", className="num"),
                html.Th("Compensation", className="num"),
            ]
        )
        bmu_rows = [
            html.Tr(
                [
                    html.Td(
                        [
                            html.Div(
                                r.get("sec_bmu_id", ""),
                                className="mono",
                                style={"fontWeight": 600},
                            ),
                            html.Div(
                                f"{r.get('sec_company_name') or r.get('sec_party_id', '')} ({r.get('sec_party_id', '')})",
                                style={"fontSize": "11.5px", "color": PALETTE["ink_secondary"]},
                            ),
                        ]
                    ),
                    html.Td(
                        [
                            html.Div(
                                r.get("pri_bmu_id", ""),
                                className="mono",
                                style={"fontWeight": 600},
                            ),
                            html.Div(
                                f"{r.get('pri_company_name') or r.get('pri_party_id', '')} ({r.get('pri_party_id', '')})",
                                style={"fontSize": "11.5px", "color": PALETTE["ink_secondary"]},
                            ),
                        ]
                    ),
                    html.Td(badge(f"_{r.get('gsp_group', '')}", "neutral")),
                    html.Td(str(r.get("active_days", 0)), className="num"),
                    html.Td(str(r.get("active_sps", 0)), className="num"),
                    html.Td(f"{float(r.get('qsd_mwh') or 0):,.2f}", className="num"),
                    html.Td(f"{float(r.get('qcv_mwh') or 0):,.2f}", className="num"),
                    html.Td(
                        fmt_gbp(r.get("comp_gbp")),
                        className="num",
                        style={"fontWeight": 600},
                    ),
                ]
            )
            for r in items
        ]
        bmu_title = f"Aggregated Secondary → Primary BMU pairs ({total:,} total)"

    bmu_panel = section_card(
        bmu_title,
        (
            html.Div(
                html.Table(
                    [html.Thead(bmu_thead), html.Tbody(bmu_rows)],
                    className="data-table",
                ),
                className="table-scroll",
                style={"maxHeight": "520px"},
            )
            if bmu_rows
            else empty_state(
                "No matching BMU records",
                "Try clearing one or more filters (VTP ID, Supplier ID, GSP Group, SP, or search text) "
                "or widening the date window.",
            )
        ),
        actions=pagination_controls,
    )

    # BSC Signatories / Parties table
    p_total = int(parties_data.get("total") or 0)
    role_desc = parties_data.get("role_descriptions") or {}
    p_items: list[dict[str, Any]] = parties_data.get("items") or []

    party_rows = []
    for p in p_items[:200]:
        roles = p.get("roles") or []
        vtp_comp = float(p.get("vtp_comp_gbp") or 0.0)
        party_rows.append(
            html.Tr(
                [
                    html.Td(p.get("party_id", ""), className="mono", style={"fontWeight": 600}),
                    html.Td(p.get("company_name", "")),
                    html.Td(
                        html.Div(
                            [
                                badge(
                                    r,
                                    "teal"
                                    if r in ("VT", "AV")
                                    else ("indigo" if r == "TS" else "neutral"),
                                    title=role_desc.get(r, r),
                                )
                                for r in roles
                            ],
                            style={"display": "flex", "gap": "4px", "flexWrap": "wrap"},
                        )
                    ),
                    html.Td(str(p.get("bmu_count", 0)), className="num"),
                    html.Td(
                        fmt_gbp(vtp_comp) if abs(vtp_comp) > 0.01 else "—",
                        className="num",
                    ),
                    html.Td(
                        p.get("source", ""),
                        style={"fontSize": "12px", "color": PALETTE["ink_muted"]},
                    ),
                ]
            )
        )

    parties_panel = section_card(
        f"Elexon BSC Signatories ({p_total:,} matching parties)",
        (
            html.Div(
                html.Table(
                    [
                        html.Thead(
                            html.Tr(
                                [
                                    html.Th("Party ID"),
                                    html.Th("Company name"),
                                    html.Th("Registered BSC roles"),
                                    html.Th("BMUs", className="num"),
                                    html.Th("VTP comp (stored)", className="num"),
                                    html.Th("Source"),
                                ]
                            )
                        ),
                        html.Tbody(party_rows),
                    ],
                    className="data-table",
                ),
                className="table-scroll",
                style={"maxHeight": "460px"},
            )
            if party_rows
            else empty_state(
                "No matching BSC signatories",
                "Try selecting 'All BSC roles' or clearing the party search filter.",
            )
        ),
        subtitle=(
            "Showing first 200 matching parties"
            if p_total > 200
            else "Live party registry from Elexon BSC Signatories"
        ),
    )

    return html.Div([bmu_panel, parties_panel])
