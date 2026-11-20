import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { OverviewResponse, TabId } from '../types';
import { fmtGbp, fmtMwh, fmtSignedGbp } from '../utils/format';

interface Props {
  data: OverviewResponse;
  onNavigate: (tab: TabId, vtpId?: string) => void;
}

export function OverviewView({ data, onNavigate }: Props) {
  const { summary, top_vtps, top_winners, top_payers, macro_timeline, milestones } = data;
  const reconExact = summary.max_reconciliation_diff_gbp < 0.05;
  const oneSidedPct =
    summary.pos_qcv_mwh + Math.abs(summary.neg_qcv_mwh) > 0
      ? (summary.pos_qcv_mwh / (summary.pos_qcv_mwh + Math.abs(summary.neg_qcv_mwh))) * 100
      : 0;

  // Snap regulatory milestones to the nearest settled date present on the categorical X-axis
  const snappedMilestones = milestones
    .map((m) => {
      if (macro_timeline.length === 0) return null;
      const target = Date.parse(m.date);
      let nearest = macro_timeline[0].date;
      let bestDiff = Math.abs(Date.parse(nearest) - target);
      for (const pt of macro_timeline) {
        const diff = Math.abs(Date.parse(pt.date) - target);
        if (diff < bestDiff) {
          bestDiff = diff;
          nearest = pt.date;
        }
      }
      return { ...m, xDate: nearest };
    })
    .filter((m): m is { date: string; code: string; label: string; xDate: string } => m !== null);

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">P415 Virtual Trading Party settlement overview</h2>
          <p className="page-lead">
            Reconciled from Elexon SAA-I014 Primary/Secondary BMU records and daily party
            settlement accounts across {data.granular_days} granular days ({data.start_date} to{' '}
            {data.end_date}).
          </p>
        </div>
        <span className={`badge ${reconExact ? 'badge-teal' : 'badge-amber'}`}>
          {reconExact
            ? `BMU × SP reconciled to SAA mutualised pot (diff £${summary.max_reconciliation_diff_gbp.toFixed(2)})`
            : `Market reconciliation variance £${summary.max_reconciliation_diff_gbp.toFixed(2)}`}
        </span>
      </div>

      {/* Flush Settlement Ledger Strip */}
      <section className="ledger-strip" aria-label="Reconciled settlement totals">
        <div className="ledger-cell">
          <div className="ledger-label">BMU-attributed compensation</div>
          <div className="ledger-value teal">{fmtGbp(summary.total_comp_gbp, true)}</div>
          <div className="ledger-sub">
            {fmtGbp(summary.daily_avg_comp_gbp, true)}/day ({fmtGbp(summary.annualised_comp_gbp, true)}/yr run-rate)
          </div>
        </div>
        <div className="ledger-cell">
          <div className="ledger-label">Net compensation volume</div>
          <div className="ledger-value">{fmtMwh(summary.net_qcv_mwh, 0)}</div>
          <div className="ledger-sub">
            {oneSidedPct.toFixed(1)}% turn-down ({fmtMwh(summary.neg_qcv_mwh, 0)} turn-up)
          </div>
        </div>
        <div className="ledger-cell">
          <div className="ledger-label">Active VTPs & SBMUs</div>
          <div className="ledger-value">
            {summary.active_vtps} <span style={{ fontSize: 14, color: 'var(--ink-muted)' }}>/ {summary.active_sbmus}</span>
          </div>
          <div className="ledger-sub">
            Affecting {summary.active_suppliers} licensed GB suppliers
          </div>
        </div>
        <div className="ledger-cell">
          <div className="ledger-label">Supplier Sourcing Cost (SSC)</div>
          <div className="ledger-value">£{summary.avg_ssc.toFixed(2)}</div>
          <div className="ledger-sub">
            Avg SBP £{summary.avg_sbp.toFixed(1)}/MWh, Market Price £{summary.avg_mpj.toFixed(1)}/MWh
          </div>
        </div>
        <div className="ledger-cell">
          <div className="ledger-label">Mutualised levy recovered</div>
          <div className="ledger-value">{fmtGbp(summary.party_total_scvp_gbp, true)}</div>
          <div className="ledger-sub">
            Paid by all GB suppliers in proportion to demand
          </div>
        </div>
      </section>

      {/* Long-Term Macro P415 Timeline */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3 className="panel-title">
              Two-year GB supplier compensation trajectory (Nov 2024 – Nov 2026)
            </h3>
            <p className="panel-subtitle">
              Daily positive supplier compensation cashflow (sccp) across {macro_timeline.length}{' '}
              settled dates, highlighting Octopus Energy’s share and the P511 large-generation cap
              in August 2026.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <span className="badge badge-teal">Total GB positive sccp</span>
            <span className="badge badge-indigo">Octopus Energy (MERCURY)</span>
          </div>
        </div>
        <div className="panel-body">
          <div style={{ width: '100%', height: 290 }}>
            <ResponsiveContainer>
              <AreaChart
                data={macro_timeline}
                margin={{ top: 16, right: 16, left: 6, bottom: 4 }}
              >
                <defs>
                  <linearGradient id="tealGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#006b6b" stopOpacity={0.25} />
                    <stop offset="95%" stopColor="#006b6b" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="indigoGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#2b59c3" stopOpacity={0.28} />
                    <stop offset="95%" stopColor="#2b59c3" stopOpacity={0.03} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: '#6c7e91' }}
                  minTickGap={36}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#6c7e91' }}
                  tickFormatter={(v: number) => fmtGbp(v, true)}
                  width={68}
                />
                <Tooltip
                  formatter={(value: number, name: string) => [
                    fmtGbp(value),
                    name === 'pos_sccp_gbp'
                      ? 'Total GB compensation (sccp)'
                      : 'Octopus Energy (MERCURY)',
                  ]}
                  labelFormatter={(label: string) => `Settlement date: ${label}`}
                  contentStyle={{
                    border: '1px solid #bcc7d5',
                    borderRadius: 3,
                    fontSize: 12.5,
                  }}
                />
                {snappedMilestones.map((m) => (
                  <ReferenceLine
                    key={m.code}
                    x={m.xDate}
                    stroke="#d1432a"
                    strokeDasharray="4 3"
                    label={{
                      value: `${m.code} (${m.date.slice(0, 7)})`,
                      position: m.code === 'P415' ? 'insideTopLeft' : 'insideTopRight',
                      dx: m.code === 'P415' ? 8 : -8,
                      dy: 6,
                      fill: '#d1432a',
                      fontSize: 11,
                      fontWeight: 600,
                    }}
                  />
                ))}
                <Area
                  type="monotone"
                  dataKey="pos_sccp_gbp"
                  stroke="#006b6b"
                  strokeWidth={2}
                  fill="url(#tealGrad)"
                  isAnimationActive={false}
                />
                <Area
                  type="monotone"
                  dataKey="octopus_sccp_gbp"
                  stroke="#2b59c3"
                  strokeWidth={1.75}
                  fill="url(#indigoGrad)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* Split Breakdown: Top VTPs vs Net Mutualisation Winners & Payers */}
      <div className="grid-asymmetric">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">Active Virtual Trading Parties</h3>
              <p className="panel-subtitle">
                Click any VTP to inspect its 6-signal EV & baselining forensic dossier
              </p>
            </div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => onNavigate('forensics')}
            >
              Open EV lab
            </button>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>VTP / Company</th>
                  <th>Roles</th>
                  <th className="num">SBMUs</th>
                  <th className="num">Net QCV</th>
                  <th className="num">Compensation</th>
                  <th className="num">Share</th>
                </tr>
              </thead>
              <tbody>
                {top_vtps.map((v) => (
                  <tr
                    key={v.party_id}
                    className="clickable"
                    onClick={() => onNavigate('forensics', v.party_id)}
                  >
                    <td>
                      <div style={{ fontWeight: 600 }}>{v.company_name}</div>
                      <div className="mono" style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>
                        {v.party_id}
                      </div>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {v.roles.map((r) => (
                          <span
                            key={r}
                            className={`badge ${
                              r === 'VT' || r === 'AV' ? 'badge-teal' : 'badge-neutral'
                            }`}
                          >
                            {r}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="num">{v.bmu_count}</td>
                    <td className="num">{v.net_qcv_mwh.toLocaleString('en-GB', { maximumFractionDigits: 1 })}</td>
                    <td className="num" style={{ fontWeight: 600 }}>
                      {fmtGbp(v.comp_gbp)}
                    </td>
                    <td className="num">
                      <span className="share-bar-cell">
                        <span className="share-bar-track" aria-hidden="true">
                          <span
                            className="share-bar-fill"
                            style={{ width: `${Math.min(100, Math.max(2, v.share_pct))}%` }}
                          />
                        </span>
                        <span>{v.share_pct.toFixed(1)}%</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">Mutualisation net winners and payers</h3>
              <p className="panel-subtitle">
                Supplier compensation received (sccp) minus mutualised levy paid (scvp)
              </p>
            </div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => onNavigate('compensation')}
            >
              Full ledger
            </button>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Supplier</th>
                  <th className="num">Received</th>
                  <th className="num">Paid</th>
                  <th className="num">Net</th>
                </tr>
              </thead>
              <tbody>
                {top_winners.slice(0, 5).map((s) => (
                  <tr key={`w-${s.party_id}`}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{s.company_name}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)' }}>
                        {s.party_id}
                      </div>
                    </td>
                    <td className="num">{fmtGbp(s.sccp_gbp, true)}</td>
                    <td className="num">{fmtGbp(s.scvp_gbp, true)}</td>
                    <td className="num" style={{ color: 'var(--teal)', fontWeight: 600 }}>
                      {fmtSignedGbp(s.net_gbp, true)}
                    </td>
                  </tr>
                ))}
                <tr>
                  <td
                    colSpan={4}
                    style={{
                      background: 'var(--bg-subtle)',
                      fontSize: 11.5,
                      fontWeight: 600,
                      color: 'var(--ink-secondary)',
                      padding: '5px 12px',
                    }}
                  >
                    Largest net contributors to mutualised pot
                  </td>
                </tr>
                {top_payers.slice(0, 5).map((s) => (
                  <tr key={`p-${s.party_id}`}>
                    <td>
                      <div style={{ fontWeight: 600 }}>{s.company_name}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)' }}>
                        {s.party_id}
                      </div>
                    </td>
                    <td className="num">{fmtGbp(s.sccp_gbp, true)}</td>
                    <td className="num">{fmtGbp(s.scvp_gbp, true)}</td>
                    <td className="num" style={{ color: 'var(--vermilion)', fontWeight: 600 }}>
                      {fmtSignedGbp(s.net_gbp, true)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
