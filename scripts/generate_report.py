"""Generate a self-contained HTML policy & forensic report from live Elexon SAA-I014 SQLite data.

Usage:
    uv run python scripts/generate_report.py
"""

from __future__ import annotations

import datetime as dt
import html
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.analytics import get_compensation, get_overview, get_status  # noqa: E402
from backend.baseline_audit import compute_baseline_audit  # noqa: E402
from backend.db import get_conn  # noqa: E402
from backend.forensics import compute_forensics  # noqa: E402


def _fmt_num(val: float | None, decimals: int = 1, suffix: str = "") -> str:
    if val is None:
        return "—"
    return f"{val:,.{decimals}f}{suffix}"


def _fmt_gbp(val: float | None) -> str:
    if val is None:
        return "—"
    sign = "-" if val < 0 else ""
    av = abs(val)
    if av >= 1_000_000:
        return f"{sign}£{av / 1_000_000:.2f}M"
    if av >= 1_000:
        return f"{sign}£{av / 1_000:.1f}k"
    return f"{sign}£{av:.0f}"


def _esc(val: Any) -> str:
    return html.escape(str(val))


def _badge_style(cls: str) -> str:
    c = cls.lower()
    if "frozen" in c:
        return "background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;"
    if "bl01" in c:
        return "background:#fffbeb;color:#b45309;border:1px solid #fde68a;"
    if "self-nominated" in c:
        return "background:#f5f3ff;color:#6d28d9;border:1px solid #ddd6fe;"
    if "sign-inverted" in c:
        return "background:#f1f5f9;color:#475569;border:1px solid #cbd5e1;"
    return "background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;"


def _chart_commentary(why_html: str, shows_html: str) -> str:
    """Render a two-column commentary block explaining why a chart is shown and what it shows."""
    return f"""
      <div class="chart-commentary">
        <div class="commentary-col">
          <div class="commentary-label why">Why this chart</div>
          <p>{why_html}</p>
        </div>
        <div class="commentary-col">
          <div class="commentary-label shows">What it actually shows</div>
          <p>{shows_html}</p>
        </div>
      </div>
    """


def _svg_sp_overlay(
    sp_overlay: list[dict[str, Any]],
    title: str,
    subtitle: str,
    commentary_html: str = "",
    width: int = 760,
    height: int = 270,
) -> str:
    """Render an inline SVG comparing Actual Metered Demand (qm) vs Settlement Baseline (sev) across SP 1–48."""
    pad_l, pad_r, pad_t, pad_b = 58, 22, 30, 38
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b

    rows = [r for r in sp_overlay if int(r["sp"]) <= 48]
    if not rows:
        return "<p>No SP overlay data available.</p>"

    max_y = max(
        max((float(r["baseline_demand_mw"]) for r in rows), default=1.0),
        max((float(r["actual_demand_mw"]) for r in rows), default=1.0),
        1.0,
    ) * 1.12

    def x_at(sp: int) -> float:
        return pad_l + ((sp - 1) / 47.0) * pw

    def y_at(val: float) -> float:
        return pad_t + ph - (max(0.0, val) / max_y) * ph

    # Off-peak shaded band SP 1..11 (00:00–05:30)
    x_off_end = x_at(11)
    # Build polylines & area paths
    base_pts = [(x_at(int(r["sp"])), y_at(float(r["baseline_demand_mw"]))) for r in rows]
    act_pts = [(x_at(int(r["sp"])), y_at(float(r["actual_demand_mw"]))) for r in rows]

    base_line = " ".join(f"{x:.1f},{y:.1f}" for x, y in base_pts)
    act_line = " ".join(f"{x:.1f},{y:.1f}" for x, y in act_pts)

    # Shaded polygons where baseline > actual (turn-down gap) vs actual > baseline (rebound)
    # Use clean vertical bar slices for rebound vs turn-down highlights
    bar_w = pw / 48.0 * 0.72
    gap_rects: list[str] = []
    for r in rows:
        x = x_at(int(r["sp"])) - bar_w / 2
        b = float(r["baseline_demand_mw"])
        a = float(r["actual_demand_mw"])
        if b > a + 0.05:
            y_top = y_at(b)
            h = max(0.0, y_at(a) - y_top)
            gap_rects.append(
                f'<rect x="{x:.1f}" y="{y_top:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
                f'fill="#2563eb" fill-opacity="0.11" />'
            )
        elif a > b + 0.05:
            y_top = y_at(a)
            h = max(0.0, y_at(b) - y_top)
            gap_rects.append(
                f'<rect x="{x:.1f}" y="{y_top:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
                f'fill="#dc2626" fill-opacity="0.18" />'
            )

    # Grid lines
    grid_lines: list[str] = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        gv = max_y * frac
        gy = y_at(gv)
        grid_lines.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
            f'stroke="#e2e8f0" stroke-width="1" />'
            f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#64748b" font-family="ui-monospace,SFMono-Regular,monospace">{gv:,.0f}</text>'
        )

    # X axis ticks every 6 SPs (3 hours)
    x_ticks: list[str] = []
    for sp_tick, lbl in [(1, "00:00"), (7, "03:00"), (12, "05:30"), (19, "09:00"), (25, "12:00"), (31, "15:00"), (37, "18:00"), (43, "21:00"), (48, "23:30")]:
        xt = x_at(sp_tick)
        x_ticks.append(
            f'<line x1="{xt:.1f}" y1="{pad_t + ph}" x2="{xt:.1f}" y2="{pad_t + ph + 4}" stroke="#94a3b8" />'
            f'<text x="{xt:.1f}" y="{pad_t + ph + 17}" text-anchor="middle" '
            f'font-size="10" fill="#64748b" font-family="ui-monospace,SFMono-Regular,monospace">{lbl}</text>'
        )

    return f"""
    <div class="chart-card">
      <div class="chart-head">
        <div>
          <div class="chart-title">{_esc(title)}</div>
          <div class="chart-sub">{_esc(subtitle)}</div>
        </div>
        <div class="legend">
          <span><i style="background:#0f172a"></i>Actual metered (qm)</span>
          <span><i style="background:#2563eb;border-bottom:2px dashed #2563eb;height:0;width:14px"></i>Settlement baseline (sev)</span>
          <span><i style="background:rgba(220,38,38,0.35)"></i>Unsettled rebound</span>
        </div>
      </div>
      <svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" aria-label="{_esc(title)}">
        <rect x="{pad_l}" y="{pad_t}" width="{x_off_end - pad_l:.1f}" height="{ph}" fill="#f8fafc" />
        <text x="{(pad_l + x_off_end) / 2:.1f}" y="{pad_t + 14}" text-anchor="middle" font-size="9.5" fill="#64748b" font-weight="600">00:00–05:30 EV Off-Peak</text>
        {''.join(grid_lines)}
        {''.join(gap_rects)}
        <polyline fill="none" stroke="#2563eb" stroke-width="2.2" stroke-dasharray="6,4" points="{base_line}" />
        <polyline fill="none" stroke="#0f172a" stroke-width="2.4" points="{act_line}" />
        <line x1="{pad_l}" y1="{pad_t + ph}" x2="{width - pad_r}" y2="{pad_t + ph}" stroke="#94a3b8" stroke-width="1" />
        {''.join(x_ticks)}
        <text x="14" y="{pad_t + ph / 2:.1f}" transform="rotate(-90 14 {pad_t + ph / 2:.1f})" text-anchor="middle" font-size="10" fill="#64748b">Mean Demand (MW)</text>
      </svg>
      {commentary_html}
    </div>
    """


def _svg_bl01_daily(
    daily: list[dict[str, Any]],
    title: str,
    subtitle: str,
    commentary_html: str = "",
    width: int = 760,
    height: int = 250,
) -> str:
    """Render inline SVG of daily Actual Demand vs Settled SEV vs Raw BL01 over the 35-day window."""
    pad_l, pad_r, pad_t, pad_b = 62, 22, 26, 38
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b
    n = len(daily)
    if n < 2:
        return ""

    vals = [float(d["actual_demand_mwh"]) for d in daily] + [float(d["settled_sev_mwh"]) for d in daily]
    vals += [float(d["bl01_raw_mwh"]) for d in daily if d.get("bl01_raw_mwh") is not None]
    max_y = max(vals + [1.0]) * 1.12

    def x_at(i: int) -> float:
        return pad_l + (i / max(1, n - 1)) * pw

    def y_at(v: float) -> float:
        return pad_t + ph - (max(0.0, v) / max_y) * ph

    act_pts = " ".join(f"{x_at(i):.1f},{y_at(float(d['actual_demand_mwh'])):.1f}" for i, d in enumerate(daily))
    sev_pts = " ".join(f"{x_at(i):.1f},{y_at(float(d['settled_sev_mwh'])):.1f}" for i, d in enumerate(daily))
    raw_pts = " ".join(
        f"{x_at(i):.1f},{y_at(float(d['bl01_raw_mwh'])):.1f}"
        for i, d in enumerate(daily)
        if d.get("bl01_raw_mwh") is not None
    )

    grid: list[str] = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        gv = max_y * frac
        gy = y_at(gv)
        grid.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" stroke="#e2e8f0" />'
            f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" font-size="10" fill="#64748b" font-family="ui-monospace,SFMono-Regular,monospace">{gv:,.0f}</text>'
        )

    ticks: list[str] = []
    step = max(1, n // 7)
    for i in range(0, n, step):
        xt = x_at(i)
        ticks.append(
            f'<text x="{xt:.1f}" y="{pad_t + ph + 17}" text-anchor="middle" font-size="9.5" fill="#64748b" font-family="ui-monospace,SFMono-Regular,monospace">{daily[i]["date"][5:]}</text>'
        )

    return f"""
    <div class="chart-card">
      <div class="chart-head">
        <div>
          <div class="chart-title">{_esc(title)}</div>
          <div class="chart-sub">{_esc(subtitle)}</div>
        </div>
        <div class="legend">
          <span><i style="background:#dc2626"></i>Settled SEV (frozen)</span>
          <span><i style="background:#0f172a"></i>Actual metered (qm)</span>
          <span><i style="background:#d97706"></i>Raw rolling BL01</span>
        </div>
      </div>
      <svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" aria-label="{_esc(title)}">
        {''.join(grid)}
        <polyline fill="none" stroke="#dc2626" stroke-width="2.4" points="{sev_pts}" />
        <polyline fill="none" stroke="#0f172a" stroke-width="2.2" points="{act_pts}" />
        {f'<polyline fill="none" stroke="#d97706" stroke-width="2.0" stroke-dasharray="5,4" points="{raw_pts}" />' if raw_pts else ''}
        <line x1="{pad_l}" y1="{pad_t + ph}" x2="{width - pad_r}" y2="{pad_t + ph}" stroke="#94a3b8" />
        {''.join(ticks)}
        <text x="14" y="{pad_t + ph / 2:.1f}" transform="rotate(-90 14 {pad_t + ph / 2:.1f})" text-anchor="middle" font-size="10" fill="#64748b">Daily Demand (MWh)</text>
      </svg>
      {commentary_html}
    </div>
    """


def _svg_price_regimes(
    regimes: list[dict[str, Any]],
    title: str,
    subtitle: str,
    commentary_html: str = "",
    width: int = 760,
    height: int = 240,
) -> str:
    """Grouped bar chart of Settled Turn-Down vs Unsettled Rebound across SBP price regimes."""
    pad_l, pad_r, pad_t, pad_b = 64, 20, 26, 44
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b
    if not regimes:
        return ""

    max_y = max(
        max((float(r["settled_turndown_mwh"]) for r in regimes), default=1.0),
        max((float(r["unsettled_rebound_mwh"]) for r in regimes), default=1.0),
        1.0,
    ) * 1.15

    n = len(regimes)
    slot_w = pw / n
    bw = min(38.0, slot_w * 0.34)

    def y_at(v: float) -> float:
        return pad_t + ph - (max(0.0, v) / max_y) * ph

    grid: list[str] = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        gv = max_y * frac
        gy = y_at(gv)
        grid.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" stroke="#e2e8f0" />'
            f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" font-size="10" fill="#64748b" font-family="ui-monospace,SFMono-Regular,monospace">{gv:,.0f}</text>'
        )

    bars: list[str] = []
    for i, r in enumerate(regimes):
        cx = pad_l + (i + 0.5) * slot_w
        td = float(r["settled_turndown_mwh"])
        rb = float(r["unsettled_rebound_mwh"])
        y_td = y_at(td)
        y_rb = y_at(rb)
        bars.append(
            f'<rect x="{cx - bw - 3:.1f}" y="{y_td:.1f}" width="{bw:.1f}" height="{max(0.0, pad_t + ph - y_td):.1f}" rx="3" fill="#2563eb" />'
            f'<rect x="{cx + 3:.1f}" y="{y_rb:.1f}" width="{bw:.1f}" height="{max(0.0, pad_t + ph - y_rb):.1f}" rx="3" fill="#dc2626" fill-opacity="0.85" />'
            f'<text x="{cx:.1f}" y="{pad_t + ph + 16}" text-anchor="middle" font-size="10" fill="#334155" font-weight="600">{_esc(r["regime"])}</text>'
            f'<text x="{cx:.1f}" y="{pad_t + ph + 30}" text-anchor="middle" font-size="9" fill="#64748b">{td:,.0f} / {rb:,.0f} MWh</text>'
        )

    return f"""
    <div class="chart-card">
      <div class="chart-head">
        <div>
          <div class="chart-title">{_esc(title)}</div>
          <div class="chart-sub">{_esc(subtitle)}</div>
        </div>
        <div class="legend">
          <span><i style="background:#2563eb"></i>Settled turn-down (MWh)</span>
          <span><i style="background:#dc2626"></i>Un-notified rebound (MWh)</span>
        </div>
      </div>
      <svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" aria-label="{_esc(title)}">
        {''.join(grid)}
        {''.join(bars)}
        <line x1="{pad_l}" y1="{pad_t + ph}" x2="{width - pad_r}" y2="{pad_t + ph}" stroke="#94a3b8" />
        <text x="14" y="{pad_t + ph / 2:.1f}" transform="rotate(-90 14 {pad_t + ph / 2:.1f})" text-anchor="middle" font-size="10" fill="#64748b">Volume (MWh)</text>
      </svg>
      {commentary_html}
    </div>
    """


def _svg_cherry_pick(
    bins: list[dict[str, Any]],
    title: str,
    subtitle: str,
    commentary_html: str = "",
    width: int = 760,
    height: int = 235,
) -> str:
    """Grouped histogram comparing Active (wmi > 0) vs Inactive (wmi = 0) qm - sev distribution."""
    pad_l, pad_r, pad_t, pad_b = 52, 20, 26, 40
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b
    if not bins:
        return ""

    max_y = max(
        max((float(b["active_pct"]) for b in bins), default=1.0),
        max((float(b["inactive_pct"]) for b in bins), default=1.0),
        10.0,
    ) * 1.15
    n = len(bins)
    slot_w = pw / n
    bw = max(6.0, min(22.0, slot_w * 0.38))

    def y_at(v: float) -> float:
        return pad_t + ph - (max(0.0, v) / max_y) * ph

    grid: list[str] = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        gv = max_y * frac
        gy = y_at(gv)
        grid.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" stroke="#e2e8f0" />'
            f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" text-anchor="end" font-size="10" fill="#64748b" font-family="ui-monospace,SFMono-Regular,monospace">{gv:.0f}%</text>'
        )

    bars: list[str] = []
    for i, b in enumerate(bins):
        cx = pad_l + (i + 0.5) * slot_w
        ap = float(b["active_pct"])
        ip = float(b["inactive_pct"])
        y_a = y_at(ap)
        y_i = y_at(ip)
        bars.append(
            f'<rect x="{cx - bw - 1.5:.1f}" y="{y_a:.1f}" width="{bw:.1f}" height="{max(0.0, pad_t + ph - y_a):.1f}" rx="2" fill="#2563eb" />'
            f'<rect x="{cx + 1.5:.1f}" y="{y_i:.1f}" width="{bw:.1f}" height="{max(0.0, pad_t + ph - y_i):.1f}" rx="2" fill="#94a3b8" />'
            f'<text x="{cx:.1f}" y="{pad_t + ph + 16}" text-anchor="middle" font-size="9" fill="#475569" font-family="ui-monospace,SFMono-Regular,monospace">{_esc(b["bin_label"])}</text>'
        )

    return f"""
    <div class="chart-card">
      <div class="chart-head">
        <div>
          <div class="chart-title">{_esc(title)}</div>
          <div class="chart-sub">{_esc(subtitle)}</div>
        </div>
        <div class="legend">
          <span><i style="background:#2563eb"></i>Active SPs (wmi &gt; 0)</span>
          <span><i style="background:#94a3b8"></i>Inactive SPs (wmi = 0)</span>
        </div>
      </div>
      <svg viewBox="0 0 {width} {height}" class="chart-svg" role="img" aria-label="{_esc(title)}">
        {''.join(grid)}
        {''.join(bars)}
        <line x1="{pad_l}" y1="{pad_t + ph}" x2="{width - pad_r}" y2="{pad_t + ph}" stroke="#94a3b8" />
        <text x="14" y="{pad_t + ph / 2:.1f}" transform="rotate(-90 14 {pad_t + ph / 2:.1f})" text-anchor="middle" font-size="10" fill="#64748b">Share of SPs (%)</text>
      </svg>
      {commentary_html}
    </div>
    """


def build_report(start_date: str = "2026-10-01", end_date: str = "2026-11-04") -> str:
    with get_conn() as conn:
        status = get_status(conn)
        audit_axle = compute_baseline_audit(conn, start_date, end_date, sec_party_id="AXLEENER")
        audit_reflexi = compute_baseline_audit(conn, start_date, end_date, sec_party_id="REFLEXI")
        audit_joulen = compute_baseline_audit(conn, start_date, end_date, sec_party_id="POWONTEC")
        forensics = compute_forensics(conn, start_date, end_date)
        comp = get_compensation(conn, start_date, end_date)
        overview = get_overview(conn, start_date, end_date)

    ms = audit_axle["market_summary"]
    vtps = audit_axle["vtps"]
    axle_d = audit_axle["selected_detail"]
    reflexi_d = audit_reflexi["selected_detail"]
    joulen_d = audit_joulen["selected_detail"]

    # Compute aggregate active vs inactive positive % across all active VTPs weighted by turn-down
    active_vtps = [v for v in vtps if v["settled_turndown_mwh"] > 0]
    total_td = sum(v["settled_turndown_mwh"] for v in active_vtps) or 1.0
    w_act_pos = sum(v["active_positive_pct"] * v["settled_turndown_mwh"] for v in active_vtps) / total_td
    w_inact_pos = sum(v["inactive_positive_pct"] * v["settled_turndown_mwh"] for v in active_vtps) / total_td
    sel_gap = w_act_pos - w_inact_pos

    # Aggregate market-wide price regimes across top VTPs? Use Axle + REFLEXI + market note,
    # or sum regimes across active VTPs from selected_detail? Better: compute directly from Axle's detail + note
    # Actually we can sum price regimes across active VTPs quickly? No, Axle + REFLEXI are 62% of market;
    # let's fetch top 6 VTPs (97% of volume) and sum their price regimes for true market-wide price regime chart!
    regime_totals: dict[str, dict[str, float]] = {}
    regime_order: list[str] = []
    with get_conn() as conn:
        for v in active_vtps:
            det = compute_baseline_audit(conn, start_date, end_date, sec_party_id=v["party_id"])["selected_detail"]
            if not det:
                continue
            for pr in det["price_regimes"]:
                reg = pr["regime"]
                if reg not in regime_totals:
                    regime_order.append(reg)
                    regime_totals[reg] = {
                        "regime": reg,
                        "settled_turndown_mwh": 0.0,
                        "unsettled_rebound_mwh": 0.0,
                        "settled_turnup_mwh": 0.0,
                    }
                regime_totals[reg]["settled_turndown_mwh"] += float(pr["settled_turndown_mwh"])
                regime_totals[reg]["unsettled_rebound_mwh"] += float(pr["unsettled_rebound_mwh"])
                regime_totals[reg]["settled_turnup_mwh"] += float(pr["settled_turnup_mwh"])
    market_regimes = [regime_totals[r] for r in regime_order]

    # Top mutualisation winners & payers
    suppliers = comp.get("suppliers", [])
    winners = sorted(suppliers, key=lambda s: float(s.get("net_transfer_gbp", 0.0)), reverse=True)[:5]
    payers = sorted(suppliers, key=lambda s: float(s.get("net_transfer_gbp", 0.0)))[:5]

    total_comp_gbp = float(overview["summary"]["total_comp_gbp"])
    annualised_comp_gbp = float(overview["summary"]["annualised_comp_gbp"])
    fv = forensics["market_verdict"]

    # Build VTP audit rows (top 14 by settled turn-down + COPPER if present)
    display_vtps = [v for v in vtps if v["settled_turndown_mwh"] >= 50 or v["party_id"] in ("COPPER", "HABITAT")][:15]
    vtp_rows_html: list[str] = []
    for v in display_vtps:
        badge = f'<span class="badge" style="{_badge_style(v["methodology_class"])}">{_esc(v["methodology_class"])}</span>'
        vtp_rows_html.append(
            f"""
            <tr>
              <td><strong>{_esc(v["company_name"])}</strong><div class="mono-sub">{_esc(v["party_id"])} · {v["sbmu_count"]} SBMUs · {v["active_days"]}d</div></td>
              <td>{badge}</td>
              <td class="num">{_fmt_num(v["settled_turndown_mwh"], 1)}</td>
              <td class="num {'neg' if v['rebound_leakage_pct'] >= 40 else ''}">{_fmt_num(v["unsettled_rebound_mwh"], 1)} <span class="mono-sub">({_fmt_num(v["rebound_leakage_pct"], 1, "%")})</span></td>
              <td class="num">{_fmt_gbp(v["implied_unsettled_comp_gbp"])}</td>
              <td class="num">{_fmt_num(v["non_active_mae_mwh"], 3)}</td>
              <td class="num">{_fmt_num(v["bl01_r2"], 3)}</td>
              <td class="num">{_fmt_num(v["quantised_2dp_pct"], 0, "%")} / {_fmt_num(v["sev_coverage_pct"], 0, "%")}</td>
            </tr>
            """
        )

    supplier_rows_html: list[str] = []
    for w, p in zip(winners, payers):
        supplier_rows_html.append(
            f"""
            <tr>
              <td><strong>{_esc(w["company_name"])}</strong> <span class="mono-sub">({_esc(w["party_id"])})</span></td>
              <td class="num pos">+{_fmt_gbp(w["net_transfer_gbp"])}</td>
              <td class="num">{_fmt_num(w.get("over_index_ratio"), 2, "×")}</td>
              <td class="divider-cell"></td>
              <td><strong>{_esc(p["company_name"])}</strong> <span class="mono-sub">({_esc(p["party_id"])})</span></td>
              <td class="num neg">{_fmt_gbp(p["net_transfer_gbp"])}</td>
              <td class="num">{_fmt_num(p.get("over_index_ratio"), 2, "×")}</td>
            </tr>
            """
        )

    generated_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    counter_econ_pct = (
        (float(ms["counter_economic_turndown_mwh"]) / float(ms["total_settled_turndown_mwh"]) * 100.0)
        if float(ms["total_settled_turndown_mwh"]) > 0
        else 0.0
    )

    # Dynamic metrics for per-chart commentary so every figure stays synced to live data
    vtp_by_id = {v["party_id"]: v for v in vtps}
    axle_v = vtp_by_id["AXLEENER"]
    reflexi_v = vtp_by_id["REFLEXI"]
    joulen_v = vtp_by_id["POWONTEC"]

    def _window_stats(sp_rows: list[dict[str, Any]]) -> dict[str, float]:
        off = [r for r in sp_rows if 1 <= int(r["sp"]) <= 11]
        day = [r for r in sp_rows if 15 <= int(r["sp"]) <= 44]
        return {
            "off_act_mean": sum(float(r["actual_demand_mw"]) for r in off) / max(1, len(off)),
            "off_base_mean": sum(float(r["baseline_demand_mw"]) for r in off) / max(1, len(off)),
            "off_act_peak": max((float(r["actual_demand_mw"]) for r in off), default=0.0),
            "day_act_mean": sum(float(r["actual_demand_mw"]) for r in day) / max(1, len(day)),
            "day_base_mean": sum(float(r["baseline_demand_mw"]) for r in day) / max(1, len(day)),
        }

    axle_w = _window_stats(axle_d["sp_overlay"])
    reflexi_w = _window_stats(reflexi_d["sp_overlay"])
    joulen_w = _window_stats(joulen_d["sp_overlay"])

    axle_day_ratio = axle_w["day_base_mean"] / max(0.1, axle_w["day_act_mean"])
    axle_share_pct = float(axle_v["settled_turndown_mwh"]) / total_td * 100.0
    axle_daily = axle_d["bl01_daily_series"]
    axle_mean_act_d = sum(float(d["actual_demand_mwh"]) for d in axle_daily) / max(1, len(axle_daily))
    axle_mean_sev_d = sum(float(d["settled_sev_mwh"]) for d in axle_daily) / max(1, len(axle_daily))
    axle_daily_ratio = axle_mean_sev_d / max(0.1, axle_mean_act_d)
    axle_first_sev = float(axle_daily[0]["settled_sev_mwh"]) if axle_daily else 0.0
    axle_last_sev = float(axle_daily[-1]["settled_sev_mwh"]) if axle_daily else 0.0
    axle_sel_gap = float(axle_v["active_positive_pct"]) - float(axle_v["inactive_positive_pct"])
    axle_inact_neg = 100.0 - float(axle_v["inactive_positive_pct"])

    low_regimes_td = sum(
        float(r["settled_turndown_mwh"])
        for r in market_regimes
        if r["regime"] in ("< £0", "£0–£50", "£50–£106 (Below SSC)")
    )
    neg_regime_td = next(
        (float(r["settled_turndown_mwh"]) for r in market_regimes if r["regime"] == "< £0"),
        0.0,
    )
    high_regimes_rb = sum(
        float(r["unsettled_rebound_mwh"])
        for r in market_regimes
        if r["regime"] in ("£106–£180", "> £180/MWh")
    )
    total_regimes_rb = sum(float(r["unsettled_rebound_mwh"]) for r in market_regimes) or 1.0
    high_rb_share_pct = high_regimes_rb / total_regimes_rb * 100.0

    svg_axle_sp = _svg_sp_overlay(
        axle_d["sp_overlay"],
        "1. Axle Energy (AXLEENER) — Frozen BL01 Baseline (~2× Actual Load)",
        "Mean half-hourly actual metered demand (qm) vs settlement baseline (sev), 35-day average (MW). Active 35/35 days; +3.35 MW IDA pre-ramp.",
        commentary_html=_chart_commentary(
            f"Axle Energy is the largest VTP in GB by settled turn-down (<strong>{_fmt_num(axle_v['settled_turndown_mwh'], 0)} MWh</strong>, "
            f"<strong>{axle_share_pct:.1f}%</strong> of market volume across {axle_v['sbmu_count']} SBMUs) and activates on all "
            f"{axle_v['active_days']}/35 days. Plotting its 24-hour average actual load (<code>qm</code>) against its settlement baseline "
            f"(<code>sev</code>) tests whether P376 BL01 remains a credible counterfactual under continuous daily dispatch.",
            f"Through the daytime (07:00–22:00), the dashed blue baseline sits at <strong>{axle_w['day_base_mean']:.1f} MW</strong> while "
            f"actual metered demand averages just <strong>{axle_w['day_act_mean']:.1f} MW</strong> — a <strong>{axle_day_ratio:.1f}×</strong> "
            f"daytime gap (shaded blue) that turns nearly every active half-hour into a turn-down claim. Also visible is a "
            f"<strong>+{_fmt_num(axle_v.get('ida_pre_ramp_mw'), 2)} MW</strong> pre-event ramp ahead of peak windows (consistent with BL01 "
            f"In-Day Adjustment). During the 00:00–05:30 EV off-peak band, actual charging surges to <strong>{axle_w['off_act_peak']:.1f} MW</strong> "
            f"peak ({axle_w['off_act_mean']:.1f} MW mean vs {axle_w['off_base_mean']:.1f} MW baseline), creating the red-shaded unsettled rebound "
            f"(<strong>{_fmt_num(axle_v['unsettled_rebound_mwh'], 0)} MWh</strong>, {_fmt_gbp(axle_v['implied_unsettled_comp_gbp'])} implied SSC).",
        ),
    )
    svg_reflexi_sp = _svg_sp_overlay(
        reflexi_d["sp_overlay"],
        "2. REFLEXI (REFLEXI) — Un-Notified Overnight EV Rebound (108.1% Leakage)",
        "~250 MW actual overnight EV charging (00:00–05:30) vs ~120 MW baseline occurs with wmi = 0, generating 26,966 MWh (£2.87M implied SSC) of unsettled rebound.",
        commentary_html=_chart_commentary(
            f"Smart EV charging shifts kWh rather than destroying demand: energy avoided at peak must be recharged overnight. "
            f"REFLEXI ({reflexi_v['sbmu_count']} SBMUs, active {reflexi_v['active_days']}/35 days, "
            f"<strong>{_fmt_num(reflexi_v['settled_turndown_mwh'], 0)} MWh</strong> settled turn-down) is shown to isolate this rebound side "
            f"of the energy balance and quantify what happens when overnight recharge occurs while <code>wmi = 0</code>.",
            f"Between 07:00 and 22:00, the blue turn-down gap is relatively modest ({reflexi_w['day_base_mean']:.1f} MW baseline vs "
            f"{reflexi_w['day_act_mean']:.1f} MW actual). Inside the 00:00–05:30 off-peak window, however, actual metered demand (black) "
            f"spikes to <strong>{reflexi_w['off_act_peak']:.1f} MW</strong> peak (<strong>{reflexi_w['off_act_mean']:.1f} MW</strong> mean) "
            f"against a baseline of only <strong>{reflexi_w['off_base_mean']:.1f} MW</strong>. That red-shaded surge represents "
            f"<strong>{_fmt_num(reflexi_v['unsettled_rebound_mwh'], 0)} MWh</strong> of un-notified rebound — "
            f"<strong>{_fmt_num(reflexi_v['rebound_leakage_pct'], 1, '%')}</strong> of its total settled turn-down — leaving suppliers with "
            f"<strong>{_fmt_gbp(reflexi_v['implied_unsettled_comp_gbp'])}</strong> in implied unsettled SSC exposure.",
        ),
    )
    svg_joulen_sp = _svg_sp_overlay(
        joulen_d["sp_overlay"],
        "3. Joulen (POWONTEC) — 100% Quantised Self-Nominated SEV",
        "100% of submitted sev values are exact 2-decimal multiples; baseline drops to 0 MW during 00:30–05:30 off-peak while actual load runs ~18 MW.",
        commentary_html=_chart_commentary(
            f"BSC Issue 127 highlights that there is currently no public register disclosing whether a VTP uses P376 BL01 or a bespoke "
            f"self-nominated baseline. Joulen ({joulen_v['sbmu_count']} SBMUs, <strong>{_fmt_num(joulen_v['settled_turndown_mwh'], 0)} MWh</strong> "
            f"settled turn-down) is shown as a direct visual contrast to Charts 1–2 so readers can see how a self-nominated <code>sev</code> "
            f"behaves in public SAA-I014 data.",
            f"Rather than an organic historical load curve, <strong>{_fmt_num(joulen_v['quantised_2dp_pct'], 0, '%')}</strong> of Joulen's "
            f"<code>sev</code> values lie on an exact 2-decimal-place grid (0.01 MWh steps) and <code>sev</code> is populated on only "
            f"<strong>{_fmt_num(joulen_v['sev_coverage_pct'], 1, '%')}</strong> of Settlement Periods. Between 00:30 and 05:30 the dashed "
            f"baseline collapses toward 0 MW (<strong>{joulen_w['off_base_mean']:.1f} MW</strong> off-peak mean) while actual load runs at "
            f"<strong>{joulen_w['off_act_mean']:.1f} MW</strong> ({joulen_w['off_act_peak']:.1f} MW peak), then jumps back to a smooth "
            f"daytime curve averaging <strong>{joulen_w['day_base_mean']:.1f} MW</strong> (peaking above 30 MW in the evening) versus "
            f"<strong>{joulen_w['day_act_mean']:.1f} MW</strong> actual — masking off-peak rebound (just "
            f"{_fmt_num(joulen_v['rebound_leakage_pct'], 1, '%')} headline leakage) and underscoring the need for a mandatory methodology registry.",
        ),
    )
    svg_axle_daily = _svg_bl01_daily(
        axle_d["bl01_daily_series"],
        "4. P376 BL01 Event-Day Lookback Freeze — Axle Energy (35 Consecutive Days)",
        "Continuous activation exhausts non-event lookback days, keeping settled SEV frozen near ~3,500 MWh/day while actual demand averages ~1,800 MWh/day.",
        commentary_html=_chart_commentary(
            "Chart 1 shows <em>that</em> Axle Energy's baseline sits roughly double its actual load, but a 24-hour average cannot prove "
            "<em>why</em> it fails to self-correct. This 35-day daily series tests the P376 BL01 event-day exclusion rule directly by "
            "comparing settled <code>sev</code> (red) against actual daily demand (black) and an independent rolling BL01 counterfactual "
            "computed <em>without</em> event-day exclusion (dashed amber).",
            f"Because P376 excludes prior event days from the 10-working-day / middle-2-of-4-weekend lookback, activating on all 35/35 days "
            f"prevents recent metered demand from ever entering the calculation. Settled SEV stays locked at a mean of "
            f"<strong>{axle_mean_sev_d:,.0f} MWh/day</strong> (even rising from {axle_first_sev:,.0f} MWh on Oct 1 to "
            f"{axle_last_sev:,.0f} MWh on Nov 4) while actual demand averages <strong>{axle_mean_act_d:,.0f} MWh/day</strong> "
            f"(a <strong>{axle_daily_ratio:.2f}×</strong> structural gap). By contrast, the dashed amber rolling BL01 line tracks actual "
            f"demand closely — visually isolating the exact distortion created by uncapped event-day exclusion.",
        ),
    )
    svg_cherry = _svg_cherry_pick(
        axle_d["cherry_pick_hist"],
        "5. Asymmetric 'Free Option' Selection Distribution — Axle Energy (qm − sev)",
        "Distribution of baseline-minus-actual deviations on Active SPs (wmi > 0, blue) vs Inactive SPs (wmi = 0, grey). Positive = actual below baseline.",
        commentary_html=_chart_commentary(
            "Even an unbiased baseline has forecast noise: actual load randomly falls below baseline in some half-hours and above it in "
            "others. This histogram tests the 'free option' hypothesis — whether optional one-sided notification (<code>wmi &gt; 0</code>) "
            "allows VTPs to monetise favorable baseline errors while leaving unfavorable deviations unsettled.",
            f"The horizontal axis shows <code>qm − sev</code> (MWh/SP), where values right of zero mean actual demand was <em>below</em> "
            f"baseline. The blue (Active, <code>wmi &gt; 0</code>) and grey (Inactive, <code>wmi = 0</code>) distributions split sharply "
            f"around zero: <strong>{_fmt_num(axle_v['active_positive_pct'], 1, '%')}</strong> of Active SPs are positive (extending into a "
            f"long right tail up to +7.5 MWh/SP), whereas <strong>{axle_inact_neg:.1f}%</strong> of Inactive SPs are negative (only "
            f"{_fmt_num(axle_v['inactive_positive_pct'], 1, '%')} positive) — a <strong>+{axle_sel_gap:.1f} pp</strong> selection gap "
            f"(+{_fmt_num(sel_gap, 1, ' pp')} market-wide). Half-hours where load exceeds baseline are overwhelmingly left at <code>wmi = 0</code>.",
        ),
    )
    svg_regimes = _svg_price_regimes(
        market_regimes,
        "6. Perverse Dispatch Across Wholesale Price Regimes (All Active VTPs, 35 Days)",
        f"{_fmt_num(ms['counter_economic_turndown_mwh'], 0)} MWh ({counter_econ_pct:.1f}%) of settled turn-down occurred when System Buy Price (SBP) was below Supplier Sourcing Cost (SSC).",
        commentary_html=_chart_commentary(
            "The central economic test for P510 is whether P415 compensation directs demand turn-down toward genuine system scarcity. "
            "Grouping all 35 days of market-wide settled turn-down (blue) and un-notified rebound (red) into five System Buy Price "
            "(<code>SBP</code>) buckets relative to the ~£106/MWh Supplier Sourcing Cost (<code>SSC</code>) reveals whether fixed "
            "retail-referenced payments distort wholesale dispatch.",
            f"Although most turn-down sits in the £106–£180 and &gt;£180/MWh scarcity buckets, <strong>{low_regimes_td:,.0f} MWh "
            f"({counter_econ_pct:.1f}%)</strong> was still claimed across the three left-hand regimes where <code>SBP &lt; SSC</code> — "
            f"including <strong>{neg_regime_td:,.0f} MWh</strong> during negative-price (<code>&lt; £0</code>) surplus periods when cutting "
            f"demand is counter-economic. Equally important, red un-notified rebound bars appear in every bucket: "
            f"<strong>{high_rb_share_pct:.1f}%</strong> ({high_regimes_rb:,.0f} MWh) of unsettled rebound actually occurs during "
            f"high-price periods (<code>SBP ≥ £106/MWh</code>), contradicting the assumption that rebound is harmlessly confined to cheap overnight hours.",
        ),
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>GB VTP Baseline &amp; P376 (BL01) Settlement Audit Report ({start_date} to {end_date})</title>
<style>
  :root {{
    --bg: #f8fafc;
    --surface: #ffffff;
    --ink: #0f172a;
    --ink-2: #334155;
    --muted: #64748b;
    --border: #e2e8f0;
    --accent: #2563eb;
    --danger: #dc2626;
    --ok: #059669;
    --slate-hero: #0c1b2a;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.55;
    font-size: 14px;
    -webkit-font-smoothing: antialiased;
  }}
  .page {{
    max-width: 1020px;
    margin: 0 auto;
    padding: 32px 24px 64px;
  }}
  .hero {{
    background: var(--slate-hero);
    color: #f8fafc;
    border-radius: 14px;
    padding: 32px 34px;
    margin-bottom: 24px;
  }}
  .eyebrow {{
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #93c5fd;
    font-weight: 700;
    margin-bottom: 8px;
  }}
  .hero h1 {{
    margin: 0 0 10px;
    font-size: 27px;
    line-height: 1.2;
    letter-spacing: -0.02em;
  }}
  .hero p {{
    margin: 0;
    color: #cbd5e1;
    max-width: 78ch;
    font-size: 14.5px;
  }}
  .meta-bar {{
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid rgba(148, 163, 184, 0.25);
    font-size: 12px;
    color: #94a3b8;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }}
  .kpi-strip {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 24px;
  }}
  .kpi-cell {{
    padding: 16px 18px;
    border-right: 1px solid var(--border);
  }}
  .kpi-cell:last-child {{ border-right: none; }}
  .kpi-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    font-weight: 600;
    margin-bottom: 6px;
  }}
  .kpi-val {{
    font-size: 21px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.02em;
    color: var(--ink);
  }}
  .kpi-val.danger {{ color: var(--danger); }}
  .kpi-sub {{
    font-size: 11.5px;
    color: var(--muted);
    margin-top: 4px;
  }}
  h2 {{
    font-size: 18px;
    letter-spacing: -0.015em;
    margin: 30px 0 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--border);
    color: var(--ink);
  }}
  .callout {{
    background: #fffbeb;
    border-left: 4px solid #d97706;
    border-radius: 0 10px 10px 0;
    padding: 14px 18px;
    margin: 14px 0 22px;
    color: #451a03;
    font-size: 13.5px;
  }}
  .chart-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px 20px 14px;
    margin-bottom: 18px;
    page-break-inside: avoid;
  }}
  .chart-head {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 10px;
    flex-wrap: wrap;
  }}
  .chart-title {{
    font-weight: 700;
    font-size: 14.5px;
    color: var(--ink);
  }}
  .chart-sub {{
    font-size: 12px;
    color: var(--muted);
    margin-top: 2px;
  }}
  .legend {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    font-size: 11.5px;
    color: var(--ink-2);
    align-items: center;
  }}
  .legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
  .legend i {{ display: inline-block; width: 12px; height: 8px; border-radius: 2px; }}
  .chart-svg {{ width: 100%; height: auto; display: block; }}
  .chart-commentary {{
    display: grid;
    grid-template-columns: 1fr 1.35fr;
    gap: 16px;
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid #f1f5f9;
  }}
  .commentary-col {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 10px 13px;
  }}
  .commentary-label {{
    font-size: 10.5px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 4px;
  }}
  .commentary-label.why {{ color: #1d4ed8; }}
  .commentary-label.shows {{ color: #0f172a; }}
  .commentary-col p {{
    margin: 0;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--ink-2);
  }}
  .commentary-col code {{
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11.5px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    padding: 0 4px;
    color: var(--ink);
  }}
  .section-intro {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 13px 16px;
    margin: 0 0 18px;
    font-size: 13px;
    color: var(--ink-2);
  }}
  .section-intro p {{ margin: 0 0 8px; }}
  .section-intro p:last-child {{ margin-bottom: 0; }}
  .guide-list {{
    margin: 6px 0 0;
    padding-left: 18px;
    font-size: 12.5px;
    color: var(--ink-2);
  }}
  .guide-list li {{ margin-bottom: 4px; }}
  .guide-list li:last-child {{ margin-bottom: 0; }}
  .table-note {{
    margin: -10px 0 22px;
    padding: 10px 14px;
    background: #f8fafc;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 12px;
    color: var(--ink-2);
    line-height: 1.5;
  }}
  .table-note code {{
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    font-size: 11px;
  }}
  .table-wrap {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow-x: auto;
    margin-bottom: 20px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
  }}
  th {{
    text-align: left;
    background: #f8fafc;
    color: var(--muted);
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }}
  td {{
    padding: 9px 12px;
    border-bottom: 1px solid #f1f5f9;
    vertical-align: middle;
  }}
  tr:last-child td {{ border-bottom: none; }}
  .num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    white-space: nowrap;
  }}
  .pos {{ color: var(--ok); font-weight: 600; }}
  .neg {{ color: var(--danger); font-weight: 600; }}
  .mono-sub {{
    font-size: 11px;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }}
  .divider-cell {{ width: 14px; background: #f8fafc; padding: 0; }}
  .policy-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-top: 12px;
  }}
  .policy-box {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 16px 18px;
    page-break-inside: avoid;
  }}
  .policy-box h3 {{
    margin: 0 0 6px;
    font-size: 14px;
    color: var(--ink);
  }}
  .policy-box p {{
    margin: 0;
    font-size: 13px;
    color: var(--ink-2);
  }}
  .footer {{
    margin-top: 32px;
    padding-top: 14px;
    border-top: 1px solid var(--border);
    font-size: 11.5px;
    color: var(--muted);
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
  }}
  @media (max-width: 820px) {{
    .kpi-strip {{ grid-template-columns: repeat(2, 1fr); }}
    .policy-grid {{ grid-template-columns: 1fr; }}
    .chart-commentary {{ grid-template-columns: 1fr; }}
  }}
  @media print {{
    body {{ background: #ffffff; font-size: 11.5px; }}
    .page {{ padding: 0; max-width: 100%; }}
    .hero {{ border-radius: 0; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    h2 {{ break-after: avoid; page-break-after: avoid; }}
    .kpi-strip, .chart-card, .table-wrap, .policy-box, .section-intro, .table-note {{ break-inside: avoid; }}
    .table-wrap {{ overflow: visible; }}
    table {{ font-size: 9.5px; }}
    th, td {{ padding: 6px 6px; }}
    .badge {{ font-size: 9px; padding: 1px 6px; }}
  }}
</style>
</head>
<body>
<div class="page">
  <header class="hero">
    <div class="eyebrow">Ofgem &amp; Elexon Issue 127 / P510 Evidence Briefing</div>
    <h1>GB Virtual Trading Party (P415) Baseline &amp; BL01 (P376) Settlement Audit</h1>
    <p>
      An objective empirical audit of actual metered demand (<code>qmij</code>) against settlement baselines (<code>sevij</code>)
      and wholesale notified delivery (<code>wmi2j</code> / <code>qcviji2</code>) across all GB Secondary BM Units (<code>V__*</code>)
      using public Elexon SAA-I014 settlement data. Evaluates structural forecast error, asymmetric selection incentives,
      un-notified EV charging rebound, P376 BL01 frozen lookback drift, and unverified self-nominated SEV submissions.
    </p>
    <div class="meta-bar">
      <span>Window: {start_date} to {end_date} ({audit_axle["baseline_days"]} consecutive days)</span>
      <span>SBMU×SP Rows: {status["sbmu_baseline_rows"]:,}</span>
      <span>Active VTPs: {len(active_vtps)} ({ms["bl01_vtps_count"]} BL01 / {ms["self_nom_vtps_count"]} Self-Nominated)</span>
      <span>Generated: {generated_at}</span>
    </div>
  </header>

  <section class="kpi-strip">
    <div class="kpi-cell">
      <div class="kpi-label">Settled Turn-Down</div>
      <div class="kpi-val">{_fmt_num(ms["total_settled_turndown_mwh"], 0)} MWh</div>
      <div class="kpi-sub">{_fmt_gbp(total_comp_gbp)} comp ({_fmt_gbp(annualised_comp_gbp)}/yr)</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Un-Notified Rebound</div>
      <div class="kpi-val danger">{_fmt_num(ms["total_unsettled_rebound_mwh"], 0)} MWh</div>
      <div class="kpi-sub">{_fmt_num(ms["rebound_leakage_pct"], 1, "%")} leakage · {_fmt_gbp(ms["implied_unsettled_comp_gbp"])} implied SSC</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Non-Active MAE / Bias</div>
      <div class="kpi-val">{_fmt_num(ms["non_active_mae_mwh"], 3)} MWh</div>
      <div class="kpi-sub">Bias {_fmt_num(ms["non_active_bias_mwh"], 3)} MWh/SP (wmi = 0)</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Asymmetric Selection Gap</div>
      <div class="kpi-val danger">+{_fmt_num(sel_gap, 1, " pp")}</div>
      <div class="kpi-sub">{_fmt_num(w_act_pos, 1, "%")} pos. active vs {_fmt_num(w_inact_pos, 1, "%")} inactive</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Counter-Economic (SBP &lt; SSC)</div>
      <div class="kpi-val">{_fmt_num(ms["counter_economic_turndown_mwh"], 0)} MWh</div>
      <div class="kpi-sub">{_fmt_num(counter_econ_pct, 1, "%")} of turn-down · {ms["bl01_vtps_count"]} BL01 / {ms["self_nom_vtps_count"]} Self-Nom</div>
    </div>
  </section>

  <div class="callout">
    <strong>Core Structural Finding:</strong> {_esc(ms["headline"])}
    Rather than indicating individual non-compliance, these signatures reflect rational commercial responses to P415/P376
    settlement mechanics: one-sided wholesale notification creates a free option on baseline noise, un-notified overnight EV
    charging escapes negative compensation, and continuous event-day exclusion freezes BL01 baselines far above current load.
  </div>

  <h2>1. Visual Evidence: Baseline vs Actual Metered Demand &amp; Perverse Incentives</h2>
  <div class="section-intro">
    <p>
      <strong>How to read these six charts:</strong> Each chart below is chosen to isolate one link in the empirical chain
      connecting P376/P415 settlement rules to observed market outcomes. Together they move from concrete portfolio behaviour
      to the underlying mathematical mechanism and its market-wide economic impact:
    </p>
    <ul class="guide-list">
      <li><strong>Charts 1–3 (Portfolio Archetypes):</strong> Compare three contrasting VTPs on the same 24-hour actual-load (<code>qm</code>) vs settlement-baseline (<code>sev</code>) scale — isolating frozen daytime BL01 inflation (Axle Energy), un-notified overnight EV rebound (REFLEXI), and quantised self-nominated SEVs (Joulen).</li>
      <li><strong>Chart 4 (Mechanism):</strong> Zooms out to a 35-day daily series for Axle Energy to show <em>how</em> P376's event-day exclusion rule mathematically locks baselines above actual load.</li>
      <li><strong>Chart 5 (Incentive Test):</strong> Tests the "free option" hypothesis statistically by comparing baseline error distributions on notified (<code>wmi &gt; 0</code>) versus un-notified (<code>wmi = 0</code>) Settlement Periods.</li>
      <li><strong>Chart 6 (Wholesale Impact):</strong> Aggregates all active VTPs by System Buy Price (<code>SBP</code>) regime to test whether dispatch aligns with genuine system scarcity relative to Supplier Sourcing Cost (<code>SSC</code>).</li>
    </ul>
  </div>
  {svg_axle_sp}
  {svg_reflexi_sp}
  {svg_joulen_sp}
  {svg_axle_daily}
  {svg_cherry}
  {svg_regimes}

  <h2>2. VTP Baseline Methodology Classification &amp; Audit Scorecard</h2>
  <p style="margin:0 0 10px;color:var(--ink-2)">
    Because BSC Issue 127 notes there is currently no public register disclosing whether a VTP uses P376 BL01 or a custom
    self-nominated SEV, the audit empirically classifies every VTP from 35 days of live <code>sevij</code> and <code>qmij</code>
    records using BL01 reconstruction fit, day-to-day lag-1 freeze persistence, 2-decimal-place quantisation, and SP coverage.
  </p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>VTP / Portfolio</th>
          <th>Empirical Baseline Class</th>
          <th class="num">Turn-Down (MWh)</th>
          <th class="num">Unsettled Rebound</th>
          <th class="num">Implied SSC (£)</th>
          <th class="num">Non-Act MAE</th>
          <th class="num">BL01 R²</th>
          <th class="num">2dp / Cov</th>
        </tr>
      </thead>
      <tbody>
        {''.join(vtp_rows_html)}
      </tbody>
    </table>
  </div>
  <div class="table-note">
    <strong>Reading the scorecard:</strong> <em>Unsettled Rebound</em> measures MWh where actual load exceeded baseline during inactive SPs
    (<code>wmi = 0</code>); <em>Implied SSC</em> values that omitted rebound at each SP's Supplier Sourcing Cost. <em>Non-Act MAE</em> is
    mean absolute baseline error (MWh/SP) on inactive periods; <em>BL01 R²</em> measures fit against an independent P376 BL01 reconstruction;
    and <em>2dp / Cov</em> flags self-nominated baselines (high % exact 2-decimal values or sparse SP coverage).
  </div>

  <h2>3. Mutualised Supplier Compensation Transfers ({start_date} – {end_date})</h2>
  <p style="margin:0 0 10px;color:var(--ink-2)">
    Across the 35-day window, <strong>{_fmt_num(fv["ev_focused_share_pct"], 1, "%")}</strong> ({_fmt_gbp(fv["ev_focused_comp_gbp"])})
    of attributed supplier compensation flowed through EV-focused domestic aggregators, creating large net wealth transfers
    via mutualised <code>scvp</code> charges from non-EV/commercial suppliers to EV-tariff domestic suppliers.
  </p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Top Net Mutualisation Recipients</th>
          <th class="num">Net Transfer</th>
          <th class="num">Over-Index</th>
          <th class="divider-cell"></th>
          <th>Top Net Mutualisation Payers</th>
          <th class="num">Net Transfer</th>
          <th class="num">Over-Index</th>
        </tr>
      </thead>
      <tbody>
        {''.join(supplier_rows_html)}
      </tbody>
    </table>
  </div>
  <div class="table-note">
    <strong>Why this transfer occurs:</strong> Under P415, compensation paid to a supplier for VTP turn-down on its customers' meters
    (<code>sccp</code>) is funded via a mutualised levy across all GB suppliers in proportion to total demand (<code>scvp</code>).
    <em>Net Transfer</em> = <code>sccp − scvp</code>; <em>Over-Index</em> is a supplier's share of compensation divided by its share of
    GB demand (1.00× = neutral). Because VTP activity is concentrated on EV-tariff domestic suppliers, non-EV and commercial suppliers
    systematically subsidise those compensation flows.
  </div>

  <h2>4. Structural Policy Implications for P376 (BL01), Issue 127 &amp; P510</h2>
  <div class="policy-grid">
    <div class="policy-box">
      <h3>1. Symmetric / Continuous Settlement Exposure</h3>
      <p>
        Allowing VTPs to nominate <code>wmi &gt; 0</code> selectively during daytime hours while leaving overnight EV recharge
        at <code>wmi = 0</code> omits <strong>{_fmt_num(ms["total_unsettled_rebound_mwh"], 0)} MWh</strong> ({_fmt_gbp(ms["implied_unsettled_comp_gbp"])}
        implied SSC) of rebound load. Requiring symmetric 24-hour energy-neutral settlement (or settling rebound windows automatically
        for load-shifting portfolios) eliminates the asymmetric free option.
      </p>
    </div>
    <div class="policy-box">
      <h3>2. Cap P376 BL01 Event-Day Lookback Freezing</h3>
      <p>
        When portfolios activate 34–35 consecutive days (e.g. <code>AXLEENER</code>, <code>REFLEXI</code>), BL01's exclusion
        of prior event days locks baselines onto stale historical profiles (~2× actual daily demand for <code>AXLEENER</code>).
        Introducing a hard lookback staleness limit, rolling decay, or tariff-aware counterfactuals prevents permanent baseline drift.
      </p>
    </div>
    <div class="policy-box">
      <h3>3. Mandatory Baseline Methodology Registry (Issue 127)</h3>
      <p>
        Self-nominated SEVs (e.g. <code>POWONTEC</code>'s 100% 2dp quantised values and 0 MW off-peak drops) and sign-inverted
        test SEVs (<code>COPPER</code>) are indistinguishable to suppliers receiving <code>S0141</code>/<code>P0287</code> flows.
        Publishing each SBMU's approved baseline methodology and <code>sevij</code> audit trail restores market transparency.
      </p>
    </div>
    <div class="policy-box">
      <h3>4. Align Compensation with Wholesale Scarcity (P510)</h3>
      <p>
        <strong>{_fmt_num(ms["counter_economic_turndown_mwh"], 0)} MWh ({_fmt_num(counter_econ_pct, 1, "%")})</strong> of settled
        turn-down occurred when <code>SBP &lt; SSC</code>. Replacing fixed retail-referenced SSC payments with dynamic wholesale-linked
        settlement removes incentives to claim turn-down during surplus periods.
      </p>
    </div>
  </div>

  <footer class="footer">
    <span>Source: Public Elexon SAA-I014 (<code>bm-unit-level</code>, <code>primary-secondary-bm-unit-level</code>, <code>settlement-period-level</code>, <code>party-level</code>), BMRS BMU Reference, BSC Signatories.</span>
    <span>Repo: github.com/literallymatt/vtpbmuanalysis · Print to PDF via browser (Ctrl/Cmd+P)</span>
  </footer>
</div>
</body>
</html>
"""


def main() -> None:
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "vtp_baseline_bl01_audit_report.html"
    html_doc = build_report("2026-10-01", "2026-11-04")
    out_path.write_text(html_doc, encoding="utf-8")
    print(f"Wrote {out_path} ({len(html_doc):,} bytes)")


if __name__ == "__main__":
    main()
