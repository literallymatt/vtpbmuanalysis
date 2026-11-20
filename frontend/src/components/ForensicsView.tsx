import { useEffect, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
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
import { InfoTip } from './InfoTip';

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
  const [guideOpen, setGuideOpen] = useState<boolean>(false);

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
          <h2 className="page-title">
            EV charger footprint &amp; baselining forensics lab
            <InfoTip
              title="Why this lab exists"
              text="Elexon settlement data does not directly label whether a Secondary BMU contains EV chargers or whether its baseline is inflated. Instead, this lab combines six independent indirect signatures from SAA-I014 settlement data to score each VTP on (1) likelihood of aggregating domestic EV chargers and (2) likelihood of baselining distortion."
              align="left"
              direction="bottom"
            />
          </h2>
          <p className="page-lead">
            Tests whether P415 VTPs are primarily targeting domestic EV chargers and exploiting
            baselining using six independent settlement-data signals. Hover or click any{' '}
            <strong>(i)</strong> icon for plain-English definitions.
          </p>
        </div>
        <span className="badge badge-neutral">
          GB Octopus demand share: {data.benchmarks.gb_octopus_demand_share_pct}% | EV-tariff
          suppliers: {data.benchmarks.gb_ev_supplier_demand_share_pct}%
          <InfoTip
            title="How GB demand share is measured"
            text="Elexon recovers supplier compensation via a mutualised levy (scvp) charged strictly in proportion to each supplier's total metered consumption. Dividing a supplier's scvp by total GB scvp gives its exact electricity demand share — our benchmark for checking whether a VTP disproportionately hits EV-heavy domestic suppliers."
            align="right"
            direction="bottom"
          />
        </span>
      </div>

      {/* Collapsible Plain-English Quick Guide */}
      <div className="guide-box">
        <button
          type="button"
          className="guide-toggle"
          onClick={() => setGuideOpen((o) => !o)}
          aria-expanded={guideOpen}
        >
          <span>How to read this lab — plain-English guide to scores, quadrants, and baselines</span>
          {guideOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </button>
        {guideOpen && (
          <div className="guide-grid">
            <div>
              <strong>1. EV Focus Score (0–100, X-axis)</strong>
              Measures whether a VTP’s assets look like nationwide domestic EV chargers rather than
              commercial sites or grid batteries. High scores (≥ 65) combine heavy concentration on
              EV-tariff suppliers (Octopus, E.ON Next, British Gas), presence across all 14 GB
              regions (GSP groups), hitting domestic 2__ supplier BMUs, and holding Elexon’s Asset
              Metering (AV / CoP11) role.
            </div>
            <div>
              <strong>2. Baselining Risk Score (0–100, Y-axis)</strong>
              Measures four physical and economic red flags: (a) claiming turn-down without
              notifying the matching recharge rebound, (b) continuing to claim turn-down on cheap
              or negative-price windy days, (c) claiming 14–19 hours/day of continuous EV turn-down
              outside the 00:00–05:30 cheap tariff window, and (d) clockwork-flat daily volumes.
            </div>
            <div>
              <strong>3. BL01/P376 vs Self-Nominated Baselines (SEV)</strong>
              Elexon does not publish a public register of which VTP uses BL01 versus a custom
              self-nominated Submitted Expected Volume (SEV) — registering methodologies is an open
              proposal in BSC Issue 127 (Oct 2026). Both paths can inflate baselines: BL01 via
              excluding event days so old high-demand days stay frozen, and self-nominated SEV via
              optimistic forward counterfactuals.
            </div>
          </div>
        )}
      </div>

      {/* Market-Level Empirical Verdict */}
      <section className="verdict-banner">
        <h2>
          {data.market_verdict.headline}
          <InfoTip
            title="How this headline is calculated"
            text="Every active VTP is scored 0–100 on EV Focus and 0–100 on Baselining Risk. We sum total BMU-attributed compensation (£) for VTPs scoring ≥ 65 on EV Focus, and separately for VTPs scoring ≥ 65 on BOTH EV Focus and Baselining Risk, then divide by total GB VTP compensation in the selected date window."
            align="left"
          />
        </h2>
        <p>
          Across {data.granular_days} granular days ({data.start_date} to {data.end_date}),{' '}
          <strong>{fmtGbp(data.market_verdict.ev_focused_comp_gbp)}</strong> (
          {data.market_verdict.ev_focused_share_pct}%) of {fmtGbp(data.market_verdict.total_comp_gbp)}{' '}
          total compensation originates from VTPs with high domestic EV footprints, and{' '}
          <strong>{fmtGbp(data.market_verdict.ev_baselining_high_risk_gbp)}</strong> (
          {data.market_verdict.ev_baselining_high_risk_share_pct}%) simultaneously scores ≥ 65 on
          multi-signal baselining distortion.
        </p>
      </section>

      {/* Quadrant Scatter + Ranked VTP Table */}
      <div className="grid-asymmetric">
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">
                2D Forensic Quadrant: EV charger focus vs baselining risk
                <InfoTip
                  title="Reading the 4 quadrants"
                  text="Each bubble is one VTP; bubble area scales with total £ supplier compensation. Top-right (red shade): domestic EV fleets with strong baselining distortion. Bottom-right: EV-heavy VTPs with cleaner dispatch. Top-left: commercial/I&C VTPs showing baselining anomalies. Bottom-left: commercial or BESS flexibility with balanced, price-responsive dispatch."
                  align="left"
                />
              </h3>
              <p className="panel-subtitle">
                Bubble area scales with total compensation (£). Top-right shaded zone flags
                domestic EV aggregators with strong baselining distortion. Click any bubble to
                inspect its dossier below.
              </p>
            </div>
          </div>
          <div className="panel-body">
            <div style={{ width: '100%', height: 340, position: 'relative' }}>
              <ResponsiveContainer>
                <ScatterChart margin={{ top: 18, right: 24, bottom: 24, left: 6 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                  <ReferenceArea
                    x1={65}
                    x2={100}
                    y1={65}
                    y2={100}
                    fill="#c84b31"
                    fillOpacity={0.08}
                    label={{
                      value: 'EV + High baselining risk',
                      position: 'insideTopRight',
                      fill: '#c84b31',
                      fontSize: 10.5,
                      fontWeight: 600,
                    }}
                  />
                  <ReferenceArea
                    x1={0}
                    x2={65}
                    y1={0}
                    y2={65}
                    fill="#006b6b"
                    fillOpacity={0.025}
                    label={{
                      value: 'Commercial / BESS lower risk',
                      position: 'insideBottomLeft',
                      fill: '#6c7e91',
                      fontSize: 10.5,
                    }}
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
                            background: '#0f2438',
                            color: '#edf3f8',
                            border: '1px solid #244361',
                            padding: '9px 11px',
                            borderRadius: 4,
                            fontSize: 12,
                            maxWidth: 260,
                          }}
                        >
                          <div style={{ fontWeight: 700, color: '#8ee0e0' }}>
                            {p.company_name} ({p.party_id})
                          </div>
                          <div style={{ marginTop: 2 }}>{p.archetype}</div>
                          <div className="mono" style={{ marginTop: 5, fontSize: 11.5 }}>
                            EV focus: {p.x}/100 | Risk: {p.y}/100
                          </div>
                          <div className="mono" style={{ fontSize: 11.5 }}>
                            Compensation: {fmtGbp(p.comp_gbp)}
                          </div>
                          <div style={{ marginTop: 4, fontSize: 11, color: '#9eb2c6' }}>
                            Click bubble to inspect full 6-signal dossier
                          </div>
                        </div>
                      );
                    }}
                  />
                  <Scatter
                    data={scatterPoints}
                    isAnimationActive={false}
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
              <p className="panel-subtitle">Click any row to load its full 6-signal dossier below</p>
            </div>
          </div>
          <div className="table-scroll" style={{ maxHeight: 390 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>VTP</th>
                  <th>
                    Archetype
                    <InfoTip
                      title="Behavioural archetype"
                      text="Rule-based label summarising the VTP's EV footprint, trading hours, and baselining risk score (e.g., Continuous EV Baseline Harvester vs Evening EV Shifter vs Commercial / Fleet Flexibility)."
                      align="left"
                      direction="bottom"
                    />
                  </th>
                  <th className="num">
                    EV
                    <InfoTip
                      title="EV Focus Score (0–100)"
                      text="Weighted blend of EV-tariff supplier lift (55%), national 14-GSP & 2__ Base BMU domestic footprint (35%), and Elexon Asset Metering VLP (AV) registration (10%)."
                      align="right"
                      direction="bottom"
                    />
                  </th>
                  <th className="num">
                    Risk
                    <InfoTip
                      title="Baselining Risk Score (0–100)"
                      text="Weighted blend of missing turn-up rebound (30%), low-price farming below SSC (30%), continuous daytime duty cycle vs overnight EV cliff (20%), and multi-day flat CoV persistence (20%)."
                      align="right"
                      direction="bottom"
                    />
                  </th>
                  <th className="num">
                    Comp
                    <InfoTip
                      title="BMU-attributed compensation (£)"
                      text="Total supplier compensation triggered by this VTP's Secondary BMUs over the selected window: sum(qcviji2 × ssc)."
                      align="right"
                      direction="bottom"
                    />
                  </th>
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
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {selected.roles.map((r) => (
                  <span
                    key={r}
                    className={`badge ${r === 'AV' || r === 'VT' ? 'badge-teal' : 'badge-neutral'}`}
                    title={
                      r === 'VT'
                        ? 'Virtual Trading Party (P415 wholesale market access)'
                        : r === 'AV'
                          ? 'Asset Metering VLP (CoP11 behind-the-meter sub-metering, e.g. EV chargers)'
                          : r === 'VP'
                            ? 'Virtual Lead Party (Balancing Mechanism)'
                            : r
                    }
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
                    <InfoTip
                      title="How the 6 signals combine"
                      text="Signals 1–2 measure EV Charger Footprint (X-axis). Signals 3–6 measure Baselining Distortion Risk (Y-axis). Hover each signal's (i) icon to see its exact formula and what separates genuine flexibility from baseline inflation."
                      align="left"
                    />
                  </h4>

                  {[
                    {
                      name: '1. EV-tariff supplier over-index',
                      score: selected.signals.ev_affinity_score,
                      tipTitle: 'Signal 1: EV-tariff supplier lift (EV Footprint, 55% weight)',
                      tipText:
                        'Measures what % of this VTP’s compensation lands on major UK EV-tariff suppliers (Octopus, E.ON Next, British Gas, OVO, ScottishPower) divided by their true GB electricity demand share (derived from scvp). Octopus holds ~13% of GB power demand but ~50%+ of smart EV chargers, so a 3–4× Octopus lift strongly identifies residential EV fleets.',
                      detail: `Octopus Energy: ${selected.signals.octopus_share_pct}% (${selected.signals.octopus_lift}x GB share). All EV-tariff suppliers: ${selected.signals.ev_supplier_share_pct}% (${selected.signals.ev_lift}x GB share).`,
                    },
                    {
                      name: '2. National domestic footprint (14 GSPs & 2__ BMUs)',
                      score: selected.signals.domestic_footprint_score,
                      tipTitle: 'Signal 2: Geographic & domestic dispersion (EV Footprint, 35% weight)',
                      tipText:
                        'Checks how many of GB’s 14 regional GSP groups (_A to _P) are active, their Shannon entropy (0 = single site, 1 = perfectly uniform nationwide spread), and the % of volume hitting 2__ Base Supplier BMUs (domestic/SME portfolios). Grid batteries or factories cluster in 1–3 GSPs; consumer EV fleets span all 14.',
                      detail: `Active in ${selected.signals.gsp_count}/14 GB GSP groups (entropy ${selected.signals.gsp_entropy}); ${selected.signals.base_bmu_share_pct}% on Base Supplier (2__) domestic/SME BMUs.`,
                    },
                    {
                      name: '3. Energy conservation violation (missing rebound)',
                      score: selected.signals.conservation_score,
                      tipTitle: 'Signal 3: One-sided turn-down asymmetry (Baselining Risk, 30% weight)',
                      tipText:
                        'EV chargers shift load rather than generate electricity: every MWh curtailed during the day must be recharged later to fill the car. If 98–100% of notified volume is positive turn-down (+QCV) and ~0% is negative turn-up (-QCV), the VTP is only submitting wholesale notifications during turn-down windows and omitting overnight recharge rebound.',
                      detail: `${selected.signals.one_sided_ratio_pct}% one-sided positive turn-down (+${selected.pos_qcv_mwh.toLocaleString('en-GB')} MWh vs ${selected.neg_qcv_mwh.toLocaleString('en-GB')} MWh turn-up).`,
                    },
                    {
                      name: '4. Wholesale price insensitivity (low-price farming)',
                      score: selected.signals.low_price_farming_score,
                      tipTitle: 'Signal 4: Low-price farming & SBP correlation (Baselining Risk, 30% weight)',
                      tipText:
                        'Genuine wholesale scarcity flexibility should curtail demand when System Buy Price (SBP) is high (above the ~£106/MWh Supplier Sourcing Cost) and charge EVs when power is cheap or negative. High volume triggered when SBP < SSC or < £60/MWh, alongside a weak daily volume-vs-price correlation (r), indicates harvesting phantom turn-down at any positive price.',
                      detail: `${selected.signals.pct_below_ssc}% of volume triggered when SBP < SSC; ${selected.signals.pct_below_60}% when SBP < £60/MWh. Daily vol-price r = ${selected.signals.daily_price_corr ?? 'n/a'}.`,
                    },
                    {
                      name: '5. Continuous duty cycle & 00:00–05:30 EV cliff',
                      score: selected.signals.duty_cycle_score,
                      tipTitle: 'Signal 5: Duty cycle & EV tariff boundary (Baselining Risk, 20% weight)',
                      tipText:
                        'Counts average hours/day where the VTP claims ≥ 15% of its daily peak volume, plus the ratio of daytime/evening volume (05:30–23:00) to the 00:00–05:30 off-peak EV tariff window. A domestic EV only charges 2–4 hrs/day; claiming 14–19 hrs/day of continuous turn-down while going silent at 00:00–05:30 points to a baseline assuming daytime charging that no longer happens.',
                      detail: `Active ${selected.signals.active_hours_per_day} hrs/day avg; daytime/evening volume is ${selected.signals.day_to_night_ratio}x overnight EV window.${selected.signals.pre_event_turnup_flag ? ' Pre-evening turn-up detected.' : ''}`,
                    },
                    {
                      name: '6. Multi-day persistence (frozen baseline)',
                      score: selected.signals.persistence_score,
                      tipTitle: 'Signal 6: Daily CoV & persistence (Baselining Risk, 20% weight)',
                      tipText:
                        'Tracks how many days are active and the daily Coefficient of Variation (CoV = standard deviation ÷ mean). Weather- and scarcity-driven flexibility varies heavily day-to-day (high CoV). Near-constant output every single day (CoV < 0.20) suggests either a BL01 baseline frozen on old non-event days or a static self-nominated counterfactual.',
                      detail: `Active ${selected.signals.active_days}/${selected.signals.total_days} days; daily volume CoV = ${selected.signals.daily_cov} (lower = clockwork flat output).`,
                    },
                  ].map((sig) => (
                    <div key={sig.name} className="signal-row">
                      <div className="signal-head">
                        <span className="signal-name">
                          {sig.name}
                          <InfoTip title={sig.tipTitle} text={sig.tipText} align="left" />
                        </span>
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
                    <InfoTip
                      title="How to read this scatter plot"
                      text="Each dot is one settlement day in the selected window. X-axis = that day's average System Buy Price (£/MWh); Y-axis = total turn-down MWh claimed by this VTP. Dots to the left of the red dashed SSC line (~£106/MWh) are cheap/windy days. Genuine price-responsive flexibility slopes steeply upward from bottom-left to top-right; a flat horizontal cloud means the VTP claims roughly the same volume whether power costs £49 or £204/MWh."
                      align="right"
                    />
                  </h4>
                  <p className="panel-subtitle" style={{ marginBottom: 10 }}>
                    Each dot is one day. Genuine scarcity flexibility slopes upward left-to-right; a
                    flat horizontal band across cheap (left of SSC) and expensive days shows
                    price-insensitive baseline harvesting.
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
                            const cheap = d.avg_sbp < d.avg_ssc;
                            return (
                              <div
                                style={{
                                  background: '#0f2438',
                                  color: '#edf3f8',
                                  border: '1px solid #244361',
                                  padding: '8px 10px',
                                  borderRadius: 4,
                                  fontSize: 12,
                                }}
                              >
                                <div style={{ fontWeight: 700, color: '#8ee0e0' }}>
                                  {d.date} ({d.dow}) {cheap ? '— Cheap day (< SSC)' : '— High-price day'}
                                </div>
                                <div className="mono" style={{ marginTop: 3 }}>
                                  Turn-down: {d.pos_qcv_mwh.toFixed(1)} MWh | Turn-up:{' '}
                                  {d.neg_qcv_mwh.toFixed(1)} MWh
                                </div>
                                <div className="mono">
                                  Avg SBP: £{d.avg_sbp.toFixed(1)} (min £{d.min_sbp.toFixed(1)}/MWh)
                                </div>
                                <div className="mono">Compensation: {fmtGbp(d.comp_gbp)}</div>
                              </div>
                            );
                          }}
                        />
                        <Scatter
                          data={selected.daily_series}
                          fill="#006b6b"
                          fillOpacity={0.85}
                          isAnimationActive={false}
                        />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Sub-BMU Suffix Breakdown */}
                  {selected.sub_bmus.length > 0 && (
                    <div style={{ marginTop: 14 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 6 }}>
                        Secondary BMU portfolio tranches (suffix *001 / *002 / *003)
                        <InfoTip
                          title="Why VTPs have *001, *002, *003 SBMUs"
                          text="VTPs register one Secondary BMU per GSP group (e.g. V__AAXLE001..V__PAXLE001), and often add a second or third tranche (*002, *003) to separate Asset-Metered (CoP11) vs Boundary-Metered meters, distinct OEM fleets, or testing cohorts."
                          align="right"
                        />
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

          {/* Bottom Split: Intraday Profile + 14-GSP Geographic Footprint */}
          <div className="grid-2">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">
                    {selected.company_name} — 48-SP profile (working vs non-working days)
                    <InfoTip
                      title="Why compare weekdays vs weekends?"
                      text="Under Elexon's BL01 historical baseline, working days (Mon–Fri) use a 10-day lookback while weekends use a separate middle-2-of-4 non-working-day lookback. Comparing both curves alongside the shaded 00:00–05:30 EV off-peak band reveals whether turn-down stops abruptly when overnight EV charging begins, and whether the red turn-up line ever rebounds."
                      align="left"
                    />
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
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="avg_weekend_mwh"
                        name="Weekends"
                        stroke="#2b59c3"
                        strokeWidth={2}
                        strokeDasharray="4 3"
                        dot={false}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="avg_neg_mwh"
                        name="Turn-up (-MWh)"
                        stroke="#c84b31"
                        strokeWidth={1.6}
                        dot={false}
                        isAnimationActive={false}
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
                    <InfoTip
                      title="What GSP distribution reveals"
                      text="Great Britain is divided into 14 Grid Supply Point (GSP) distribution regions (_A Eastern through _P North Scotland). Residential EV charger portfolios naturally spread across all 14 regions with heaviest share in affluent commuter belts (_H Southern, _J South Eastern, _A Eastern, _E Midlands). Single-site batteries or factories spike in only 1–3 GSPs."
                      align="right"
                    />
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
                      <Bar
                        dataKey="share_pct"
                        fill="#2b59c3"
                        radius={[2, 2, 0, 0]}
                        isAnimationActive={false}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </section>
          </div>

          {/* Baseline Methodology Forensic Note: BL01/P376 vs Self-Nominated SEV */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  Can Elexon data tell BL01 (P376) apart from self-nominated baselines?
                  <InfoTip
                    title="Governance context: BSC Issue 127"
                    text="Elexon opened BSC Issue 127 on 30 October 2026 specifically because VTPs do not currently have to register or publicly declare whether they use BL01 or a custom self-nominated Submitted Expected Volume (SEV) methodology."
                    align="left"
                  />
                </h3>
                <p className="panel-subtitle">
                  No public Elexon register flags which VTP uses BL01 vs custom self-nominated SEV,
                  but SAA-I014’s bm-unit-level dataset (sevij, qmij, fpnij, wmi2j) exposes three
                  diagnostic fingerprints.
                </p>
              </div>
              <span className="badge badge-amber">BSC Issue 127 (Oct 2026)</span>
            </div>
            <div className="panel-body">
              <div className="guide-grid" style={{ padding: 0 }}>
                <div>
                  <strong>1. What Elexon publishes (and doesn’t)</strong>
                  The compact <span className="mono">primary-secondary-bm-unit-level</span> feed
                  only reports settled deviation volumes (<span className="mono">qcviji2</span>),
                  not the baseline itself. The larger <span className="mono">bm-unit-level</span>{' '}
                  feed (~380 MB/day) publishes both actual metered load (<span className="mono">qmij</span>)
                  and the Settlement Expected Volume (<span className="mono">sevij</span>), but
                  does not tag whether <span className="mono">sevij</span> came from SVAA’s BL01
                  formula or a VTP’s self-nominated SEV.
                </div>
                <div>
                  <strong>2. Self-nominated SEV fingerprints in bm-unit-level</strong>
                  Inspecting live <span className="mono">bm-unit-level</span> data (2026-10-01 SF)
                  shows clear self-nomination tells: <strong>Joulen (POWONTEC)</strong> posts
                  cleanly rounded 2-decimal <span className="mono">sevij</span> values (e.g.{' '}
                  <span className="mono">-1.15</span>, <span className="mono">-1.00</span>,{' '}
                  <span className="mono">-0.90 MWh</span>) rather than 4-decimal smart-meter
                  averages, and <strong>Zenobe (ZENOBER1)</strong> only populates{' '}
                  <span className="mono">sevij</span> sparsely during active events.
                </div>
                <div>
                  <strong>3. BL01 &amp; un-notified overnight rebound proof</strong>
                  By contrast, <strong>Axle Energy</strong>, <strong>Reflexi</strong>,{' '}
                  <strong>Powerverse</strong>, and <strong>Capture</strong> carry 4-decimal{' '}
                  <span className="mono">sevij</span> across all 48 SPs — consistent with BL01 or
                  meter-derived models. Crucially, comparing <span className="mono">qmij</span>{' '}
                  against <span className="mono">sevij</span> in SP 1–2 (00:00–01:00) catches
                  Reflexi pulling <strong>-9.84 to -10.70 MWh</strong> vs a{' '}
                  <strong>-7.18 to -7.81 MWh</strong> baseline (real overnight EV charging rebound)
                  with <span className="mono">wmi2j = 0</span> so zero negative compensation is
                  booked.
                </div>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
