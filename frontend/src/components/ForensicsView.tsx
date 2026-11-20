import { useEffect, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import type { ForensicsResponse, ForensicVtp } from '../types';
import { fmtGbp, fmtMwh, riskTone } from '../utils/format';

interface Props {
  data: ForensicsResponse;
  initialVtpId?: string;
}

function scoreColor(score: number): string {
  if (score >= 65) return '#c84b31';
  if (score >= 45) return '#c47a0e';
  return '#006b6b';
}

function badgeForScore(score: number): string {
  const t = riskTone(score);
  if (t === 'high') return 'badge-vermilion';
  if (t === 'mid') return 'badge-amber';
  return 'badge-teal';
}

export function ForensicsView({ data, initialVtpId }: Props) {
  const [selectedId, setSelectedId] = useState<string>(
    initialVtpId || data.vtps[0]?.party_id || '',
  );

  useEffect(() => {
    if (initialVtpId && data.vtps.some((v) => v.party_id === initialVtpId)) {
      setSelectedId(initialVtpId);
    } else if (!data.vtps.some((v) => v.party_id === selectedId) && data.vtps[0]) {
      setSelectedId(data.vtps[0].party_id);
    }
  }, [initialVtpId, data.vtps, selectedId]);

  const selected: ForensicVtp | undefined =
    data.vtps.find((v) => v.party_id === selectedId) ?? data.vtps[0];

  const scatterPoints = data.vtps.map((v) => ({
    x: v.ev_focus_score,
    y: v.baselining_risk_score,
    z: Math.max(40, Math.sqrt(Math.abs(v.comp_gbp)) * 1.4),
    party_id: v.party_id,
    company_name: v.company_name,
    comp_gbp: v.comp_gbp,
    archetype: v.archetype,
  }));

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">EV charger footprint &amp; baselining forensics lab</h2>
          <p className="page-lead">
            Tests whether P415 VTPs are primarily targeting domestic EV chargers and exploiting
            BL01 historical baselining using six independent settlement-data signals.
          </p>
        </div>
        <span className="badge badge-neutral">
          GB Octopus demand share: {data.benchmarks.gb_octopus_demand_share_pct}% | EV-tariff
          suppliers: {data.benchmarks.gb_ev_supplier_demand_share_pct}%
        </span>
      </div>

      {/* Market-Level Empirical Verdict */}
      <section className="verdict-banner">
        <h2>{data.market_verdict.headline}</h2>
        <p>
          Across {data.granular_days} granular days ({data.start_date} to {data.end_date}),{' '}
          <strong>{fmtGbp(data.market_verdict.ev_focused_comp_gbp)}</strong> (
          {data.market_verdict.ev_focused_share_pct}%) of {fmtGbp(data.market_verdict.total_comp_gbp)}{' '}
          total compensation originates from VTPs with high domestic EV footprints, and{' '}
          <strong>{fmtGbp(data.market_verdict.ev_baselining_high_risk_gbp)}</strong> (
          {data.market_verdict.ev_baselining_high_risk_share_pct}%) simultaneously scores ≥ 65 on
          multi-signal baselining distortion (one-sided turn-down, low-price insensitivity,
          continuous duty cycle, and frozen BL01 lookback stability).
        </p>
      </section>

      {/* Quadrant Scatter + Ranked VTP Table */}
      <div className="grid-asymmetric">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">
                2D Forensic Quadrant: EV charger focus vs baselining risk
              </h3>
              <p className="panel-subtitle">
                Bubble area scales with total compensation (£). Top-right quadrant flags domestic
                EV aggregators showing strong baselining distortion. Click any bubble to inspect.
              </p>
            </div>
          </div>
          <div className="panel-body">
            <div style={{ width: '100%', height: 340 }}>
              <ResponsiveContainer>
                <ScatterChart margin={{ top: 18, right: 24, bottom: 24, left: 6 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                  <ReferenceArea
                    x1={65}
                    x2={100}
                    y1={65}
                    y2={100}
                    fill="#c84b31"
                    fillOpacity={0.07}
                  />
                  <ReferenceLine x={65} stroke="#bcc7d5" strokeDasharray="4 4" />
                  <ReferenceLine y={65} stroke="#bcc7d5" strokeDasharray="4 4" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    domain={[0, 100]}
                    name="EV focus score"
                    tick={{ fontSize: 11, fill: '#6c7e91' }}
                    label={{
                      value: 'EV charger footprint score (0–100)',
                      position: 'insideBottom',
                      offset: -12,
                      fontSize: 12,
                      fill: '#485c70',
                    }}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    domain={[0, 100]}
                    name="Baselining risk score"
                    tick={{ fontSize: 11, fill: '#6c7e91' }}
                    label={{
                      value: 'Baselining risk (0–100)',
                      angle: -90,
                      position: 'insideLeft',
                      style: { textAnchor: 'middle' },
                      offset: 8,
                      fontSize: 12,
                      fill: '#485c70',
                    }}
                  />
                  <ZAxis type="number" dataKey="z" range={[70, 950]} />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    content={({ payload }) => {
                      if (!payload || !payload.length) return null;
                      const p = payload[0].payload as (typeof scatterPoints)[number];
                      return (
                        <div
                          style={{
                            background: '#fff',
                            border: '1px solid #bcc7d5',
                            padding: '8px 10px',
                            borderRadius: 3,
                            fontSize: 12.5,
                          }}
                        >
                          <div style={{ fontWeight: 700 }}>
                            {p.company_name} ({p.party_id})
                          </div>
                          <div>{p.archetype}</div>
                          <div className="mono" style={{ marginTop: 4 }}>
                            EV focus: {p.x} | Risk: {p.y} | {fmtGbp(p.comp_gbp)}
                          </div>
                        </div>
                      );
                    }}
                  />
                  <Scatter
                    data={scatterPoints}
                    onClick={(pt) => {
                      if (pt && pt.party_id) setSelectedId(pt.party_id);
                    }}
                  >
                    {scatterPoints.map((pt) => (
                      <Cell
                        key={pt.party_id}
                        fill={scoreColor(pt.y)}
                        fillOpacity={pt.party_id === selected?.party_id ? 0.95 : 0.65}
                        stroke={pt.party_id === selected?.party_id ? '#0f2438' : '#ffffff'}
                        strokeWidth={pt.party_id === selected?.party_id ? 2.5 : 1}
                        cursor="pointer"
                      />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">All active VTPs — forensic ranking</h3>
              <p className="panel-subtitle">Click a row to load its 6-signal dossier below</p>
            </div>
          </div>
          <div className="table-scroll" style={{ maxHeight: 390 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>VTP</th>
                  <th>Archetype</th>
                  <th className="num">EV</th>
                  <th className="num">Risk</th>
                  <th className="num">Comp</th>
                </tr>
              </thead>
              <tbody>
                {data.vtps.map((v) => (
                  <tr
                    key={v.party_id}
                    className={`clickable ${selected?.party_id === v.party_id ? 'selected' : ''}`}
                    onClick={() => setSelectedId(v.party_id)}
                  >
                    <td>
                      <div style={{ fontWeight: 600 }}>{v.company_name}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)' }}>
                        {v.party_id}
                      </div>
                    </td>
                    <td style={{ fontSize: 12 }}>{v.archetype}</td>
                    <td className="num">
                      <span
                        className={`badge ${
                          v.ev_focus_score >= 65 ? 'badge-indigo' : 'badge-neutral'
                        }`}
                      >
                        {v.ev_focus_score.toFixed(0)}
                      </span>
                    </td>
                    <td className="num">
                      <span className={`badge ${badgeForScore(v.baselining_risk_score)}`}>
                        {v.baselining_risk_score.toFixed(0)}
                      </span>
                    </td>
                    <td className="num" style={{ fontWeight: 600 }}>
                      {fmtGbp(v.comp_gbp, true)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* Selected VTP Full Forensic Dossier */}
      {selected && (
        <div>
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  Forensic dossier: {selected.company_name}{' '}
                  <span className="mono" style={{ color: 'var(--ink-muted)', fontWeight: 500 }}>
                    ({selected.party_id})
                  </span>
                </h3>
                <p className="panel-subtitle">
                  {selected.archetype} — {selected.bmu_count} Secondary BMUs,{' '}
                  {selected.market_share_pct.toFixed(1)}% of GB compensation (
                  {fmtGbp(selected.comp_gbp)} | {fmtMwh(selected.net_qcv_mwh)})
                </p>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {selected.roles.map((r) => (
                  <span
                    key={r}
                    className={`badge ${r === 'AV' || r === 'VT' ? 'badge-teal' : 'badge-neutral'}`}
                  >
                    {r}
                  </span>
                ))}
                <span className={`badge ${badgeForScore(selected.baselining_risk_score)}`}>
                  Baselining risk: {selected.baselining_risk_score.toFixed(0)}/100
                </span>
              </div>
            </div>

            <div className="panel-body">
              {/* Empirical Evidence Bullets */}
              <div
                style={{
                  background: 'var(--bg-canvas)',
                  border: '1px solid var(--border)',
                  borderRadius: 3,
                  padding: '12px 16px',
                  marginBottom: 18,
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
                  Key empirical findings from settlement data
                </div>
                <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--ink-secondary)', fontSize: 13 }}>
                  {selected.evidence.map((line, i) => (
                    <li key={i} style={{ marginBottom: 3 }}>
                      {line}
                    </li>
                  ))}
                </ul>
              </div>

              {/* 6-Signal Breakdown + Low-Price Farming Scatter */}
              <div className="grid-2">
                <div>
                  <h4 className="panel-title" style={{ marginBottom: 10 }}>
                    Six-signal forensic breakdown
                  </h4>

                  {[
                    {
                      name: '1. EV-tariff supplier over-index',
                      score: selected.signals.ev_affinity_score,
                      detail: `Octopus Energy: ${selected.signals.octopus_share_pct}% (${selected.signals.octopus_lift}x GB share). All EV-tariff suppliers: ${selected.signals.ev_supplier_share_pct}% (${selected.signals.ev_lift}x GB share).`,
                    },
                    {
                      name: '2. National domestic footprint (14 GSPs & 2__ BMUs)',
                      score: selected.signals.domestic_footprint_score,
                      detail: `Active in ${selected.signals.gsp_count}/14 GB GSP groups (entropy ${selected.signals.gsp_entropy}); ${selected.signals.base_bmu_share_pct}% on Base Supplier (2__) domestic/SME BMUs.`,
                    },
                    {
                      name: '3. Energy conservation violation (missing rebound)',
                      score: selected.signals.conservation_score,
                      detail: `${selected.signals.one_sided_ratio_pct}% one-sided positive turn-down (+${selected.pos_qcv_mwh.toLocaleString('en-GB')} MWh vs ${selected.neg_qcv_mwh.toLocaleString('en-GB')} MWh turn-up).`,
                    },
                    {
                      name: '4. Wholesale price insensitivity (low-price farming)',
                      score: selected.signals.low_price_farming_score,
                      detail: `${selected.signals.pct_below_ssc}% of volume triggered when SBP < SSC; ${selected.signals.pct_below_60}% when SBP < £60/MWh. Daily vol-price r = ${selected.signals.daily_price_corr ?? 'n/a'}.`,
                    },
                    {
                      name: '5. Continuous duty cycle & 00:00–05:30 EV cliff',
                      score: selected.signals.duty_cycle_score,
                      detail: `Active ${selected.signals.active_hours_per_day} hrs/day avg; daytime/evening volume is ${selected.signals.day_to_night_ratio}x overnight EV window.${selected.signals.pre_event_turnup_flag ? ' Pre-evening turn-up detected.' : ''}`,
                    },
                    {
                      name: '6. Multi-day persistence (frozen BL01 baseline)',
                      score: selected.signals.persistence_score,
                      detail: `Active ${selected.signals.active_days}/${selected.signals.total_days} days; daily volume CoV = ${selected.signals.daily_cov} (lower = clockwork flat output).`,
                    },
                  ].map((sig) => (
                    <div key={sig.name} className="signal-row">
                      <div className="signal-head">
                        <span className="signal-name">{sig.name}</span>
                        <span className="mono" style={{ fontWeight: 600, color: scoreColor(sig.score) }}>
                          {sig.score.toFixed(0)}/100
                        </span>
                      </div>
                      <div className="signal-bar-track">
                        <div
                          className="signal-bar-fill"
                          style={{
                            width: `${Math.min(100, sig.score)}%`,
                            backgroundColor: scoreColor(sig.score),
                          }}
                        />
                      </div>
                      <div className="signal-detail">{sig.detail}</div>
                    </div>
                  ))}
                </div>

                {/* Smoking Gun Chart: Daily Volume vs Daily Avg System Buy Price */}
                <div>
                  <h4 className="panel-title" style={{ marginBottom: 4 }}>
                    Low-price farming test: daily volume vs daily average SBP
                  </h4>
                  <p className="panel-subtitle" style={{ marginBottom: 10 }}>
                    Genuine scarcity flexibility slopes sharply upward from left to right. A flat
                    horizontal cloud across £45–£210/MWh days proves price-insensitive harvesting.
                  </p>
                  <div style={{ width: '100%', height: 270 }}>
                    <ResponsiveContainer>
                      <ScatterChart margin={{ top: 12, right: 16, bottom: 22, left: 6 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                        <XAxis
                          type="number"
                          dataKey="avg_sbp"
                          name="Daily avg SBP"
                          tickFormatter={(v: number) => `£${v}`}
                          tick={{ fontSize: 11, fill: '#6c7e91' }}
                          label={{
                            value: 'Daily average System Buy Price (£/MWh)',
                            position: 'insideBottom',
                            offset: -12,
                            fontSize: 11.5,
                            fill: '#485c70',
                          }}
                        />
                        <YAxis
                          type="number"
                          dataKey="pos_qcv_mwh"
                          name="Daily turn-down"
                          unit=" MWh"
                          tick={{ fontSize: 11, fill: '#6c7e91' }}
                          width={74}
                        />
                        <ReferenceLine
                          x={selected.daily_series[0]?.avg_ssc ?? 106}
                          stroke="#c84b31"
                          strokeDasharray="4 4"
                          label={{
                            value: 'SSC',
                            position: 'insideTopRight',
                            fill: '#c84b31',
                            fontSize: 11,
                          }}
                        />
                        <Tooltip
                          content={({ payload }) => {
                            if (!payload || !payload.length) return null;
                            const d = payload[0].payload as ForensicVtp['daily_series'][number];
                            return (
                              <div
                                style={{
                                  background: '#fff',
                                  border: '1px solid #bcc7d5',
                                  padding: '7px 10px',
                                  borderRadius: 3,
                                  fontSize: 12,
                                }}
                              >
                                <div style={{ fontWeight: 700 }}>
                                  {d.date} ({d.dow})
                                </div>
                                <div className="mono">
                                  Turn-down: {d.pos_qcv_mwh.toFixed(1)} MWh | Turn-up:{' '}
                                  {d.neg_qcv_mwh.toFixed(1)} MWh
                                </div>
                                <div className="mono">
                                  Avg SBP: £{d.avg_sbp.toFixed(1)} (min £{d.min_sbp.toFixed(1)})
                                </div>
                                <div className="mono">Comp: {fmtGbp(d.comp_gbp)}</div>
                              </div>
                            );
                          }}
                        />
                        <Scatter
                          data={selected.daily_series}
                          fill="#006b6b"
                          fillOpacity={0.85}
                        />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Sub-BMU Suffix Breakdown */}
                  {selected.sub_bmus.length > 0 && (
                    <div style={{ marginTop: 14 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 6 }}>
                        Secondary BMU portfolio tranches (suffix *001 / *002 / *003)
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {selected.sub_bmus.map((sb) => (
                          <span key={sb.suffix} className="badge badge-neutral">
                            *{sb.suffix}: {sb.total_qcv_mwh.toLocaleString('en-GB', { maximumFractionDigits: 0 })} MWh ({sb.active_days}d)
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* Bottom Split: Intraday Profile + 14-GSP Geographic Footprint + Top Suppliers */}
          <div className="grid-2">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">
                    {selected.company_name} — 48-SP profile (working vs non-working days)
                  </h3>
                  <p className="panel-subtitle">
                    Shaded 00:00–05:30 band shows domestic EV off-peak window alignment
                  </p>
                </div>
              </div>
              <div className="panel-body">
                <div style={{ width: '100%', height: 240 }}>
                  <ResponsiveContainer>
                    <LineChart data={selected.sp_profile} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                      <ReferenceArea x1="00:00" x2="05:00" fill="#2b59c3" fillOpacity={0.08} />
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
                        name="Working days"
                        stroke="#006b6b"
                        strokeWidth={2}
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="avg_weekend_mwh"
                        name="Weekends"
                        stroke="#2b59c3"
                        strokeWidth={2}
                        strokeDasharray="4 3"
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="avg_neg_mwh"
                        name="Turn-up (-MWh)"
                        stroke="#c84b31"
                        strokeWidth={1.6}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">
                    Geographic GSP footprint ({selected.signals.gsp_count}/14 GB regions)
                  </h3>
                  <p className="panel-subtitle">
                    Broad Southern/Eastern/Midlands weighting mirrors UK residential EV ownership
                  </p>
                </div>
              </div>
              <div className="panel-body">
                <div style={{ width: '100%', height: 240 }}>
                  <ResponsiveContainer>
                    <BarChart
                      data={selected.gsp_breakdown}
                      margin={{ top: 8, right: 12, left: 0, bottom: 4 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                      <XAxis dataKey="gsp_group" tick={{ fontSize: 11, fill: '#0f2438' }} />
                      <YAxis
                        tick={{ fontSize: 11, fill: '#6c7e91' }}
                        tickFormatter={(v: number) => `${v}%`}
                        width={42}
                      />
                      <Tooltip
                        formatter={(v: number, _n: string, item: { payload?: { gsp_name: string; abs_qcv_mwh: number } }) => [
                          `${v}% (${item.payload?.abs_qcv_mwh.toLocaleString('en-GB')} MWh)`,
                          item.payload?.gsp_name ?? '',
                        ]}
                        contentStyle={{ border: '1px solid #bcc7d5', borderRadius: 3, fontSize: 12 }}
                      />
                      <Bar dataKey="share_pct" fill="#2b59c3" radius={[2, 2, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
