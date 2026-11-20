import { useState } from 'react';
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TimingResponse } from '../types';
import { fmtGbp, fmtMwh, spToTime } from '../utils/format';

interface Props {
  data: TimingResponse;
  selectedVtp: string;
  onSelectVtp: (vtp: string) => void;
}

const VTP_COLORS = ['#006b6b', '#2b59c3', '#c84b31', '#c47a0e', '#6d4c9e', '#2d8a4e'];

function cellColor(qcv: number, maxAbs: number): string {
  if (Math.abs(qcv) < 0.05 || maxAbs <= 0) return '#f2f5f8';
  const ratio = Math.min(1, Math.abs(qcv) / maxAbs);
  const eased = Math.pow(ratio, 0.58);
  if (qcv > 0) {
    // Crisp teal intensity ramp
    const r = Math.round(230 - eased * 230);
    const g = Math.round(244 - eased * 137);
    const b = Math.round(244 - eased * 137);
    return `rgb(${r}, ${g}, ${b})`;
  }
  // Vermilion intensity ramp for turn-up / negative QCV
  const r = Math.round(252 - eased * 52);
  const g = Math.round(236 - eased * 161);
  const b = Math.round(232 - eased * 183);
  return `rgb(${r}, ${g}, ${b})`;
}

export function TimingView({ data, selectedVtp, onSelectVtp }: Props) {
  const [hoverCell, setHoverCell] = useState<{
    date: string;
    dow: string;
    sp: number;
    qcv_mwh: number;
    comp_gbp: number;
    sbp: number;
  } | null>(null);

  const avgSsc =
    data.intraday.length > 0
      ? data.intraday.reduce((a, b) => a + b.avg_ssc, 0) / data.intraday.length
      : 0;

  // Build comparative per-VTP chart dataset (SP 1..48)
  const vtpCompareRows = Array.from({ length: 48 }, (_, idx) => {
    const row: Record<string, string | number> = {
      sp: idx + 1,
      time: spToTime(idx + 1),
    };
    for (const vp of data.vtp_profiles) {
      row[vp.party_id] = vp.avg_sp_mwh[idx] ?? 0;
    }
    return row;
  });

  // Compute off-peak vs daytime/evening totals
  const nightVol = data.intraday
    .filter((x) => x.is_ev_offpeak)
    .reduce((a, b) => a + b.avg_pos_mwh, 0);
  const dayVol = data.intraday
    .filter((x) => !x.is_ev_offpeak)
    .reduce((a, b) => a + b.avg_pos_mwh, 0);
  const peakSp = data.intraday.reduce(
    (best, cur) => (cur.avg_pos_mwh > best.avg_pos_mwh ? cur : best),
    data.intraday[0] ?? { sp: 1, time: '00:00', avg_pos_mwh: 0 },
  );

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">When Virtual Trading Parties trade</h2>
          <p className="page-lead">
            Half-hourly settlement period (SP 1–48) trading footprint overlaid against GB wholesale
            prices, System Buy Price, and the 23:30–05:30 domestic EV off-peak tariff window.
          </p>
        </div>

        <div className="filter-bar" style={{ marginBottom: 0 }}>
          <label htmlFor="timing-vtp" style={{ fontSize: 12.5, color: 'var(--ink-secondary)' }}>
            Filter VTP
          </label>
          <select
            id="timing-vtp"
            className="select"
            value={selectedVtp}
            onChange={(e) => onSelectVtp(e.target.value)}
          >
            <option value="">All active VTPs</option>
            {data.vtp_choices.map((v) => (
              <option key={v.party_id} value={v.party_id}>
                {v.company_name} ({v.party_id})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Quick Timing Summary Strip */}
      <section className="ledger-strip">
        <div className="ledger-cell">
          <div className="ledger-label">Peak half-hour (avg)</div>
          <div className="ledger-value teal">
            {peakSp.time} <span style={{ fontSize: 13, color: 'var(--ink-muted)' }}>SP {peakSp.sp}</span>
          </div>
          <div className="ledger-sub">
            {fmtMwh(peakSp.avg_pos_mwh)}/SP (~{(peakSp.avg_pos_mwh * 2).toFixed(0)} MW avg)
          </div>
        </div>
        <div className="ledger-cell">
          <div className="ledger-label">05:30–23:30 daytime/evening</div>
          <div className="ledger-value">{fmtMwh(dayVol, 0)}</div>
          <div className="ledger-sub">
            {((dayVol / Math.max(0.01, dayVol + nightVol)) * 100).toFixed(1)}% of daily turn-down
          </div>
        </div>
        <div className="ledger-cell">
          <div className="ledger-label">23:30–05:30 EV off-peak window</div>
          <div className="ledger-value">{fmtMwh(nightVol, 1)}</div>
          <div className="ledger-sub">
            {((nightVol / Math.max(0.01, dayVol + nightVol)) * 100).toFixed(1)}% of daily turn-down
          </div>
        </div>
        <div className="ledger-cell">
          <div className="ledger-label">Granular days analysed</div>
          <div className="ledger-value">{data.granular_days}</div>
          <div className="ledger-sub">
            {data.start_date} to {data.end_date}
          </div>
        </div>
      </section>

      {/* Main Chart: 48-SP Profile vs Wholesale Prices */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3 className="panel-title">
              Average intraday VTP volume (MWh/SP) vs System Buy Price and Market Price
            </h3>
            <p className="panel-subtitle">
              Shaded band marks 00:00–05:30 (SP 1–11), matching Intelligent Octopus Go / Next Drive
              cheap EV charging windows. Positive bars = claimed demand turn-down; negative bars =
              turn-up.
            </p>
          </div>
          <span className="badge badge-indigo">Shaded: 00:00–05:30 EV off-peak</span>
        </div>
        <div className="panel-body">
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <ComposedChart
                data={data.intraday}
                margin={{ top: 12, right: 16, left: 4, bottom: 4 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                <ReferenceArea
                  x1="00:00"
                  x2="05:00"
                  yAxisId="vol"
                  fill="#2b59c3"
                  fillOpacity={0.07}
                />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 11, fill: '#6c7e91' }}
                  interval={3}
                />
                <YAxis
                  yAxisId="vol"
                  tick={{ fontSize: 11, fill: '#006b6b' }}
                  unit=" MWh"
                  width={72}
                />
                <YAxis
                  yAxisId="price"
                  orientation="right"
                  tick={{ fontSize: 11, fill: '#c47a0e' }}
                  tickFormatter={(v: number) => `£${v}`}
                  width={56}
                />
                <Tooltip
                  formatter={(val: number, name: string) => {
                    if (name.includes('Price') || name.includes('SBP') || name.includes('SSC')) {
                      return [`£${val.toFixed(2)}/MWh`, name];
                    }
                    return [`${val.toFixed(2)} MWh`, name];
                  }}
                  labelFormatter={(label: string) => `Settlement period start: ${label}`}
                  contentStyle={{ border: '1px solid #bcc7d5', borderRadius: 3, fontSize: 12.5 }}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {avgSsc > 0 && (
                  <ReferenceLine
                    yAxisId="price"
                    y={avgSsc}
                    stroke="#6c7e91"
                    strokeDasharray="4 4"
                    label={{
                      value: `SSC £${avgSsc.toFixed(0)}`,
                      position: 'insideTopLeft',
                      dx: 6,
                      fill: '#485c70',
                      fontSize: 11,
                      fontWeight: 600,
                    }}
                  />
                )}
                <Bar
                  yAxisId="vol"
                  dataKey="avg_pos_mwh"
                  name="Turn-down QCV (+MWh)"
                  fill="#006b6b"
                  radius={[2, 2, 0, 0]}
                />
                <Bar
                  yAxisId="vol"
                  dataKey="avg_neg_mwh"
                  name="Turn-up QCV (-MWh)"
                  fill="#c84b31"
                />
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="avg_sbp"
                  name="Avg System Buy Price (SBP)"
                  stroke="#c47a0e"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="avg_mpj"
                  name="Avg Market Price (MIDP)"
                  stroke="#2b59c3"
                  strokeWidth={1.6}
                  strokeDasharray="4 2"
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* Interactive Day × 48-SP Heatmap */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3 className="panel-title">Daily × 48-settlement-period trading heatmap</h3>
            <p className="panel-subtitle">
              Every row is a settled day with its daily average SBP shown on the right. Notice how
              volume persists across low-price windy days as well as high-price peak days.
            </p>
          </div>
          <div style={{ fontSize: 12.5, fontFamily: 'var(--font-mono)', color: 'var(--ink)' }}>
            {hoverCell ? (
              <span>
                {hoverCell.date} ({hoverCell.dow}) SP {String(hoverCell.sp).padStart(2, '0')} (
                {spToTime(hoverCell.sp)}) —{' '}
                <strong style={{ color: hoverCell.qcv_mwh >= 0 ? 'var(--teal)' : 'var(--vermilion)' }}>
                  {hoverCell.qcv_mwh.toFixed(2)} MWh
                </strong>{' '}
                | {fmtGbp(hoverCell.comp_gbp)} | SBP £{hoverCell.sbp.toFixed(1)}
              </span>
            ) : (
              <span style={{ color: 'var(--ink-muted)' }}>Hover any half-hour cell to inspect</span>
            )}
          </div>
        </div>
        <div className="panel-body">
          <div className="heatmap-wrap">
            <table className="heatmap-grid">
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', paddingRight: 8 }}>Date</th>
                  {Array.from({ length: 48 }, (_, i) => (
                    <th key={i} title={`SP ${i + 1} (${spToTime(i + 1)})`}>
                      {i % 4 === 0 ? spToTime(i + 1).slice(0, 2) : ''}
                    </th>
                  ))}
                  <th style={{ textAlign: 'right', paddingLeft: 8 }}>Day MWh</th>
                  <th style={{ textAlign: 'right', paddingLeft: 8 }}>Avg SBP</th>
                </tr>
              </thead>
              <tbody>
                {data.heatmap.map((row) => (
                  <tr key={row.date}>
                    <td className={`hm-date ${row.is_weekend ? 'weekend' : ''}`}>
                      {row.date} {row.dow}
                    </td>
                    {row.cells.map((c) => (
                      <td
                        key={c.sp}
                        className="hm-cell"
                        style={{ backgroundColor: cellColor(c.qcv_mwh, data.max_cell_mwh) }}
                        onMouseEnter={() =>
                          setHoverCell({
                            date: row.date,
                            dow: row.dow,
                            ...c,
                          })
                        }
                      />
                    ))}
                    <td className="hm-total">{row.total_qcv_mwh.toFixed(0)}</td>
                    <td
                      className="hm-total"
                      style={{
                        color:
                          row.avg_sbp < 70
                            ? 'var(--vermilion)'
                            : row.avg_sbp > 160
                              ? 'var(--teal)'
                              : 'var(--ink-secondary)',
                        fontWeight: row.avg_sbp < 70 ? 600 : 400,
                      }}
                    >
                      £{row.avg_sbp.toFixed(0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Bottom Split: Per-VTP Curves + Weekday vs Weekend */}
      <div className="grid-2">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">Trading schedules by VTP (top 6)</h3>
              <p className="panel-subtitle">
                Compare continuous daytime schedules (Axle, Joulen) against evening-only blocks
                (Reflexi) and overnight windows (Capture).
              </p>
            </div>
          </div>
          <div className="panel-body">
            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={vtpCompareRows} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: '#6c7e91' }} interval={5} />
                  <YAxis tick={{ fontSize: 11, fill: '#6c7e91' }} unit=" MWh" width={64} />
                  <Tooltip
                    contentStyle={{ border: '1px solid #bcc7d5', borderRadius: 3, fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11.5 }} />
                  {data.vtp_profiles.map((vp, idx) => (
                    <Line
                      key={vp.party_id}
                      type="monotone"
                      dataKey={vp.party_id}
                      name={`${vp.company_name} (${vp.party_id})`}
                      stroke={VTP_COLORS[idx % VTP_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">Weekday vs weekend profile</h3>
              <p className="panel-subtitle">
                Tests whether VTPs separate BL01 working-day vs non-working-day baselines
              </p>
            </div>
          </div>
          <div className="panel-body">
            <div style={{ width: '100%', height: 260 }}>
              <ResponsiveContainer>
                <LineChart data={data.intraday} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                  <XAxis dataKey="time" tick={{ fontSize: 11, fill: '#6c7e91' }} interval={5} />
                  <YAxis tick={{ fontSize: 11, fill: '#6c7e91' }} unit=" MWh" width={64} />
                  <Tooltip
                    formatter={(v: number) => [`${v.toFixed(2)} MWh/SP`]}
                    contentStyle={{ border: '1px solid #bcc7d5', borderRadius: 3, fontSize: 12 }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line
                    type="monotone"
                    dataKey="avg_weekday_mwh"
                    name="Working days (Mon–Fri)"
                    stroke="#006b6b"
                    strokeWidth={2}
                    dot={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="avg_weekend_mwh"
                    name="Non-working days (Sat–Sun)"
                    stroke="#2b59c3"
                    strokeWidth={2}
                    strokeDasharray="5 3"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
