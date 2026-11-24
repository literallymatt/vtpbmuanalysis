"""Shared editorial styling tokens, number formatters, Plotly layout helpers, and UI components."""

from __future__ import annotations

from typing import Any

from dash import html

# ---------------------------------------------------------------------------
# Color palette matching py_dashboard/assets/styles.css CSS tokens
# ---------------------------------------------------------------------------

PALETTE: dict[str, Any] = {
    "bg_canvas": "#f4f6f9",
    "bg_surface": "#ffffff",
    "bg_subtle": "#edf1f6",
    "bg_hover": "#e5ecf4",
    "border": "#e1e7ef",
    "border_strong": "#c6d0dd",
    "grid": "#eef2f6",
    "ink": "#0c1b2a",
    "ink_secondary": "#43566b",
    "ink_muted": "#6c7f94",
    "teal": "#0b7a75",
    "teal_bright": "#0d928c",
    "teal_soft": "#e6f5f4",
    "teal_border": "#b8e0dd",
    "vermilion": "#d1432a",
    "vermilion_soft": "#fdf0ed",
    "vermilion_border": "#f3c4ba",
    "amber": "#c97a12",
    "amber_soft": "#fef6e7",
    "amber_border": "#f2d8a6",
    "indigo": "#2c5cc5",
    "indigo_soft": "#ecf1fc",
    "indigo_border": "#c5d5f8",
    "chart_series": [
        "#0b7a75",
        "#2c5cc5",
        "#c97a12",
        "#d1432a",
        "#5b6b7c",
        "#0d928c",
        "#6f42c1",
    ],
}

FONT_SANS = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif"
)
FONT_MONO = (
    "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Monaco, "
    "Consolas, 'Liberation Mono', monospace"
)

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


# ---------------------------------------------------------------------------
# Numeric & date formatters
# ---------------------------------------------------------------------------


def _to_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        f = float(val)
        return default if f != f else f  # guard NaN
    except (TypeError, ValueError):
        return default


def fmt_gbp(val: Any, compact: bool = False) -> str:
    """Format a GBP amount (e.g. '£12,345' or '-£1.24m' when compact=True)."""
    num = _to_float(val)
    if compact:
        return fmt_gbp_compact(num)
    sign = "-" if num < 0 else ""
    return f"{sign}£{abs(num):,.0f}"


def fmt_gbp_exact(val: Any) -> str:
    """Format a GBP amount with two decimal places (e.g. '£1,234.56')."""
    num = _to_float(val)
    sign = "-" if num < 0 else ""
    return f"{sign}£{abs(num):,.2f}"


def fmt_gbp_compact(val: Any) -> str:
    """Format a GBP amount compactly (£1.24m, £45.2k, £812)."""
    num = _to_float(val)
    abs_v = abs(num)
    sign = "-" if num < 0 else ""
    if abs_v >= 1_000_000:
        return f"{sign}£{abs_v / 1_000_000:.2f}m"
    if abs_v >= 1_000:
        return f"{sign}£{abs_v / 1_000:.1f}k"
    return f"{sign}£{abs_v:.0f}"


def fmt_signed_gbp(val: Any, compact: bool = False) -> str:
    """Format a GBP amount with explicit '+' sign for positive values."""
    num = _to_float(val)
    prefix = "+" if num > 0 else ""
    return f"{prefix}{fmt_gbp(num, compact=compact)}"


def fmt_mwh(val: Any, decimals: int = 1) -> str:
    """Format energy volume in MWh (e.g. '1,234.5 MWh')."""
    num = _to_float(val)
    return f"{num:,.{decimals}f} MWh"


def fmt_mw(val: Any, decimals: int = 1) -> str:
    """Format power in MW (e.g. '42.3 MW')."""
    num = _to_float(val)
    return f"{num:,.{decimals}f} MW"


def fmt_pct(val: Any, decimals: int = 1) -> str:
    """Format a percentage already on 0..100 scale (e.g. '64.2%')."""
    num = _to_float(val)
    return f"{num:,.{decimals}f}%"


def fmt_num(val: Any, decimals: int = 0) -> str:
    """Format a plain number with thousands separators."""
    num = _to_float(val)
    return f"{num:,.{decimals}f}"


def sp_to_time(sp: int) -> str:
    """Convert a GB settlement period (1..50) to HH:MM clock string."""
    idx = max(0, int(sp) - 1)
    hh = (idx // 2) % 24
    mm = "00" if idx % 2 == 0 else "30"
    return f"{hh:02d}:{mm}"


def short_date(iso: str | None) -> str:
    """Format 'YYYY-MM-DD' as '14 Oct'."""
    if not iso:
        return ""
    parts = str(iso).split("-")
    if len(parts) != 3:
        return str(iso)
    try:
        month_idx = int(parts[1]) - 1
        day = int(parts[2])
        mon = _MONTHS[month_idx] if 0 <= month_idx < 12 else parts[1]
        return f"{day} {mon}"
    except ValueError:
        return str(iso)


def risk_tone(score: Any) -> str:
    """Map a 0..100 risk score to badge/CSS tone ('vermilion', 'amber', 'teal')."""
    s = _to_float(score)
    if s >= 65:
        return "vermilion"
    if s >= 45:
        return "amber"
    return "teal"


# ---------------------------------------------------------------------------
# Plotly editorial base layout
# ---------------------------------------------------------------------------


def plotly_base_layout(
    height: int = 340,
    margin: dict[str, int] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Return a clean, offline-safe editorial Plotly layout dict.

    Usage:
        fig.update_layout(**plotly_base_layout(height=360, xaxis_title="Settlement Period"))
    """
    layout: dict[str, Any] = {
        "height": height,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": PALETTE["bg_surface"],
        "font": {
            "family": FONT_SANS,
            "size": 12,
            "color": PALETTE["ink"],
        },
        "margin": margin or {"l": 56, "r": 24, "t": 34, "b": 44},
        "hovermode": "x unified",
        "hoverlabel": {
            "bgcolor": PALETTE["ink"],
            "bordercolor": "#223b56",
            "font": {
                "family": FONT_SANS,
                "size": 12,
                "color": "#f0f5fa",
            },
        },
        "legend": {
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "bgcolor": "rgba(255,255,255,0)",
            "font": {"size": 11.5, "color": PALETTE["ink_secondary"]},
        },
        "xaxis": {
            "showgrid": False,
            "linecolor": PALETTE["border"],
            "tickfont": {"size": 11, "color": PALETTE["ink_muted"]},
            "title_font": {"size": 11.5, "color": PALETTE["ink_secondary"]},
            "zeroline": False,
        },
        "yaxis": {
            "showgrid": True,
            "gridcolor": PALETTE["grid"],
            "gridwidth": 1,
            "linecolor": "rgba(0,0,0,0)",
            "tickfont": {"size": 11, "color": PALETTE["ink_muted"]},
            "title_font": {"size": 11.5, "color": PALETTE["ink_secondary"]},
            "zeroline": True,
            "zerolinecolor": PALETTE["border_strong"],
            "zerolinewidth": 1,
        },
    }

    # Deep-merge xaxis/yaxis/legend/margin dicts if caller passes them
    for key, val in overrides.items():
        if (
            key in layout
            and isinstance(layout[key], dict)
            and isinstance(val, dict)
        ):
            merged = dict(layout[key])
            merged.update(val)
            layout[key] = merged
        else:
            layout[key] = val

    return layout


PLOTLY_CONFIG: dict[str, Any] = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
}


# ---------------------------------------------------------------------------
# Reusable Dash UI building blocks
# ---------------------------------------------------------------------------


def badge(
    text: str,
    tone: str = "neutral",
    title: str | None = None,
) -> html.Span:
    """Render an inline monospace badge pill.

    tone: 'neutral' | 'teal' | 'vermilion' | 'amber' | 'indigo'
    """
    props: dict[str, Any] = {"className": f"badge badge-{tone}"}
    if title:
        props["title"] = title
    return html.Span(text, **props)


def kpi_card(
    label: str,
    value: Any,
    sub: Any = None,
    tone: str | None = None,
) -> html.Div:
    """Render a single KPI cell for use inside a `.ledger-strip` container."""
    val_cls = "ledger-value"
    if tone:
        val_cls = f"{val_cls} {tone}"
    children: list[Any] = [
        html.Div(label, className="ledger-label"),
        html.Div(value, className=val_cls),
    ]
    if sub is not None and sub != "":
        children.append(html.Div(sub, className="ledger-sub"))
    return html.Div(children, className="ledger-cell")


def section_card(
    title: Any,
    children: Any,
    subtitle: Any = None,
    actions: Any = None,
    body_class: str | None = None,
    panel_class: str | None = None,
) -> html.Section:
    """Render a clean editorial `.panel` card with header and body."""
    title_block: list[Any] = [html.H2(title, className="panel-title")]
    if subtitle:
        title_block.append(html.P(subtitle, className="panel-subtitle"))

    header_children: list[Any] = [html.Div(title_block)]
    if actions is not None:
        header_children.append(html.Div(actions, className="header-actions"))

    cls = "panel" if not panel_class else f"panel {panel_class}"
    b_cls = "panel-body" if not body_class else f"panel-body {body_class}"

    return html.Section(
        [
            html.Div(header_children, className="panel-header"),
            html.Div(children, className=b_cls),
        ],
        className=cls,
    )


def empty_state(
    title: str,
    message: Any,
    action: Any = None,
) -> html.Div:
    """Render a clear empty-data state inside a panel card."""
    items: list[Any] = [
        html.H3(title),
        html.P(message),
    ]
    if action is not None:
        items.append(html.Div(action, style={"marginTop": "6px"}))
    return html.Div(
        html.Div(items, className="empty-audit-state"),
        className="panel",
    )
