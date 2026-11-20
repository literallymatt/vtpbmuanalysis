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
  if (score >= 65) return '#d1432a';
  if (score >= 45) return '#c97a12';
  return '#0b7a75';
}

function badgeForScore(score: number): string {
  const t = riskTone(score);
  if (t === 'high') return 'badge-vermilion';
  if (t === 'mid') return 'badge-amber';
  return 'badge-teal';
}

function heroTone(score: number): string {
  const t = riskTone(score);
  if (t === 'high') return 'vermilion';
  if (t === 'mid') return 'amber';
  return 'teal';
}

const CHART_TOOLTIP_STYLE = {
  background: '#0c1b2a',
  color: '#edf3f8',
  border: '1px solid #223b56',
  borderRadius: 6,
  fontSize: 12,
  boxShadow: '0 8px 24px rgba(12, 27, 42, 0.24)',
};

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
              text="Elexon settlement data does not directly label whether a Secondary BMU contains EV chargers or whether its baseline is inflated. Instead, this lab combines six independent indirect signatures plus supplier tariff-clock tests from SAA-I014 settlement data to score each VTP."
            />
          </h2>
          <p className="page-lead">
            Tests whether P415 VTPs are targeting domestic EV chargers and profiting from baselines
            during expensive tariff hours when EVs would not normally charge. Hover or click any{' '}
            <strong>(i)</strong> icon for plain-English definitions.
          </p>
        </div>
        <span className="badge badge-neutral">
          Octopus demand share: {data.benchmarks.gb_octopus_demand_share_pct}%, EV suppliers:{' '}
          {data.benchmarks.gb_ev_supplier_demand_share_pct}%
          <InfoTip
            title="How GB demand share is measured"
            text="Elexon recovers supplier compensation via a mutualised levy (scvp) charged strictly in proportion to each supplier's total metered consumption. Dividing a supplier's scvp by total GB scvp gives its exact electricity demand share — our benchmark for testing whether a VTP disproportionately hits EV-heavy domestic suppliers."
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
              <strong>EV Focus Score (0–100, X-axis)</strong>
              Measures whether a VTP’s assets look like nationwide domestic EV chargers rather than
              commercial sites or grid batteries. High scores (≥ 65) combine heavy concentration on
              EV-tariff suppliers (Octopus, E.ON Next, British Gas), presence across all 14 GB
              regions (GSP groups), hitting domestic 2__ supplier BMUs, and holding Elexon’s Asset
              Metering (AV / CoP11) role.
            </div>
            <div>
              <strong>Baselining Risk Score (0–100, Y-axis)</strong>
              Measures four physical and economic red flags: (a) claiming turn-down without
              notifying the matching recharge rebound, (b) continuing to claim turn-down on cheap
              or negative-price windy days, (c) claiming 14–19 hours/day of continuous EV turn-down
              outside the 00:00–05:30 cheap tariff window, and (d) clockwork-flat daily volumes.
            </div>
            <div>
              <strong>BL01/P376 vs Self-Nominated Baselines (SEV)</strong>
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
            text="Every active VTP is scored 0–100 on EV Focus and 0–100 on Baselining Risk. We sum total BMU-attributed compensation (£) for VTPs scoring ≥ 65 on EV Focus, and separately for VTPs scoring ≥ 65 on BOTH EV Focus and Baselining Risk, then divide by total GB VTP compensation in the selected window."
          />
        </h2>
        <p>
          Across {data.granular_days} granular days ({data.start_date} to {data.end_date}),{' '}
          <strong>{fmtGbp(data.market_verdict.ev_focused_comp_gbp)}</strong> (
          {data.market_verdict.ev_focused_share_pct}%) of {fmtGbp(data.market_verdict.total_comp_gbp)}{' '}
          total compensation originates from EV-focused domestic aggregators, and{' '}
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
                />
              </h3>
              <p className="panel-subtitle">
                Bubble area scales with total compensation (£). Click any bubble to inspect its
                dossier below.
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
                    fill="#d1432a"
                    fillOpacity={0.07}
                    label={{
                      value: 'EV + High baselining risk',
                      position: 'insideTopRight',
                      fill: '#d1432a',
                      fontSize: 10.5,
                      fontWeight: 600,
                    }}
                  />
                  <ReferenceArea
                    x1={0}
                    x2={65}
                    y1={0}
                    y2={65}
                    fill="#0b7a75"
                    fillOpacity={0.025}
                    label={{
                      value: 'Commercial / BESS lower risk',
                      position: 'insideBottomLeft',
                      fill: '#6c7f94',
                      fontSize: 10.5,
                    }}
                  />
                  <ReferenceLine x={65} stroke="#c6d0dd" strokeDasharray="4 4" />
                  <ReferenceLine y={65} stroke="#c6d0dd" strokeDasharray="4 4" />
                  <XAxis
                    type="number"
                    dataKey="x"
                    domain={[0, 100]}
                    name="EV focus score"
                    tick={{ fontSize: 11, fill: '#6c7f94' }}
                    label={{
                      value: 'EV charger footprint score (0–100)',
                      position: 'insideBottom',
                      offset: -12,
                      fontSize: 12,
                      fill: '#43566b',
                    }}
                  />
                  <YAxis
                    type="number"
                    dataKey="y"
                    domain={[0, 100]}
                    name="Baselining risk score"
                    tick={{ fontSize: 11, fill: '#6c7f94' }}
                    label={{
                      value: 'Baselining risk (0–100)',
                      angle: -90,
                      position: 'insideLeft',
                      style: { textAnchor: 'middle' },
                      offset: 8,
                      fontSize: 12,
                      fill: '#43566b',
                    }}
                  />
                  <ZAxis type="number" dataKey="z" range={[70, 950]} />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    content={({ payload }) => {
                      if (!payload || !payload.length) return null;
                      const p = payload[0].payload as (typeof scatterPoints)[number];
                      return (
                        <div style={{ ...CHART_TOOLTIP_STYLE, padding: '10px 12px', maxWidth: 260 }}>
                          <div style={{ fontWeight: 700, color: '#7eece5' }}>
                            {p.company_name} ({p.party_id})
                          </div>
                          <div style={{ marginTop: 2 }}>{p.archetype}</div>
                          <div className="mono" style={{ marginTop: 5, fontSize: 11.5 }}>
                            EV focus: {p.x}/100, Risk: {p.y}/100
                          </div>
                          <div className="mono" style={{ fontSize: 11.5 }}>
                            Compensation: {fmtGbp(p.comp_gbp)}
                          </div>
                          <div style={{ marginTop: 4, fontSize: 11, color: '#9bb0c6' }}>
                            Click bubble to inspect full dossier
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
                        stroke={pt.party_id === selected?.party_id ? '#0c1b2a' : '#ffffff'}
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
              <p className="panel-subtitle">Select a VTP to inspect its full dossier</p>
            </div>
          </div>
          <div className="table-scroll" style={{ maxHeight: 392 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>VTP</th>
                  <th>
                    Archetype
                    <InfoTip
                      title="Behavioural archetype"
                      text="Rule-based label summarising the VTP's EV footprint, trading hours, and baselining risk score (e.g., Continuous EV Baseline Harvester vs Evening EV Shifter vs Overnight EV Specialist)."
                    />
                  </th>
                  <th className="num">
                    EV
                    <InfoTip
                      title="EV Focus Score (0–100)"
                      text="Weighted blend of EV-tariff supplier lift (55%), national 14-GSP & 2__ Base BMU domestic footprint (35%), and Elexon Asset Metering VLP (AV) registration (10%)."
                    />
                  </th>
                  <th className="num">
                    Risk
                    <InfoTip
                      title="Baselining Risk Score (0–100)"
                      text="Weighted blend of missing turn-up rebound (30%), low-price farming below SSC (30%), continuous daytime duty cycle vs overnight EV cliff (20%), and multi-day flat CoV persistence (20%)."
                    />
                  </th>
                  <th className="num">
                    Comp
                    <InfoTip
                      title="BMU-attributed compensation (£)"
                      text="Total supplier compensation triggered by this VTP's Secondary BMUs over the selected window: sum(qcviji2 × ssc)."
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

      {/* Quick 1-Click VTP Switcher right above the Forensic Dossier */}
      {selected && (
        <div>
          <div className="vtp-switcher" role="tablist" aria-label="Switch active VTP dossier">
            <span className="vtp-switcher-label">Inspect VTP:</span>
            {data.vtps.slice(0, 9).map((v) => (
              <button
                key={`pill-${v.party_id}`}
                type="button"
                role="tab"
                aria-selected={selected.party_id === v.party_id}
                className={`vtp-pill ${selected.party_id === v.party_id ? 'active' : ''}`}
                onClick={() => setSelectedId(v.party_id)}
              >
                <span>{v.company_name}</span>
                <span className="vtp-pill-share">
                  {v.party_id === 'CAPTURE' ? 'Control' : `${v.market_share_pct.toFixed(1)}%`}
                </span>
              </button>
            ))}
          </div>

          {/* Focal Moment: Dark Slate Dossier Hero Band (zero nested boxes) */}
          <section className="dossier-hero">
            <div className="dossier-hero-top">
              <div>
                <h3 className="dossier-hero-name">
                  {selected.company_name}{' '}
                  <span className="mono" style={{ fontSize: 15, color: '#8ba0b7', fontWeight: 500 }}>
                    {selected.party_id}
                  </span>
                </h3>
                <p className="dossier-hero-sub">
                  {selected.archetype}, {selected.bmu_count} Secondary BMUs,{' '}
                  {selected.market_share_pct.toFixed(1)}% of GB compensation ({fmtGbp(selected.comp_gbp)}{' '}
                  on {fmtMwh(selected.net_qcv_mwh)})
                </p>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {selected.roles.map((r) => (
                  <span
                    key={r}
                    className={`hero-badge ${r === 'AV' || r === 'VT' ? 'teal' : ''}`}
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
                <span className={`hero-badge ${heroTone(selected.baselining_risk_score)}`}>
                  Baselining risk {selected.baselining_risk_score.toFixed(0)}/100
                </span>
              </div>
            </div>

            <ul className="dossier-hero-findings">
              {selected.evidence.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          </section>

          {/* Standalone Tariff-Window & Profitability Strip */}
          <section className="ledger-strip" aria-label="Tariff-window counterfactual metrics">
            <div className="ledger-cell">
              <div className="ledger-label">
                Claimed in expensive tariff hours
                <InfoTip
                  title="Peak-tariff share (%)"
                  text="Share of this VTP's positive turn-down on the 5 major EV-tariff suppliers that occurs OUTSIDE each supplier's published cheap overnight window (i.e. during 25–28p/kWh hours when EV-tariff cars would not normally be charging). Compare ~97% (Axle, Reflexi, Joulen) against 0.1% (Capture Energy, which shifts charging inside the 00:00–02:30 cheap window)."
                />
              </div>
              <div
                className={`ledger-value ${
                  selected.tariff_analysis.peak_tariff_share_pct >= 85 ? 'vermilion' : 'teal'
                }`}
              >
                {selected.tariff_analysis.peak_tariff_share_pct.toFixed(1)}%
              </div>
              <div className="ledger-sub">
                Only {selected.tariff_analysis.offpeak_tariff_share_pct.toFixed(1)}% inside cheap
                overnight EV windows
              </div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                Weekday midday (09:00–16:00)
                <InfoTip
                  title="Working-day daytime turn-down share"
                  text="% of total turn-down volume claimed between 09:00 and 16:00 Mon–Fri (SP 19–32). At midday on weekdays, EV-tariff rates are 3.5–4× overnight rates AND commuter cars are typically away from home — making large continuous midday 'avoided EV charging' strongly indicative of inflated daytime baselines."
                />
              </div>
              <div
                className={`ledger-value ${
                  selected.tariff_analysis.weekday_midday_share_pct >= 15 ? 'vermilion' : ''
                }`}
              >
                {selected.tariff_analysis.weekday_midday_share_pct.toFixed(1)}%
              </div>
              <div className="ledger-sub">Mon–Fri 09:00–16:00 (26p/kWh &amp; work hours)</div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                Equivalent full-load hours
                <InfoTip
                  title="Equivalent Full-Load Hours (EFLH = Daily MWh ÷ Peak MW)"
                  text="Measures how many hours per day the fleet would need to run at its full daily peak MW to deliver the claimed daily turn-down MWh. A typical UK EV drives ~20–25 miles/day (~7 kWh = ~1–1.5 hrs on a 7 kW charger). Claiming 11–13 full-load hours every single day is physically inconsistent with genuine paused EV charging."
                />
              </div>
              <div
                className={`ledger-value ${
                  selected.tariff_analysis.eflh_hours_per_day >= 8 ? 'vermilion' : ''
                }`}
              >
                {selected.tariff_analysis.eflh_hours_per_day.toFixed(1)} h/d
              </div>
              <div className="ledger-sub">Typical UK EV daily charge: ~1–2 h/d at 7 kW</div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                Est. VTP wholesale value (MIDP)
                <InfoTip
                  title="Estimated gross wholesale revenue & below-SSC deadweight"
                  text="Calculated as sum(qcv × mpj) using Elexon's Market Index Price (MIDP) as a proxy for wholesale value earned on positive turn-down. Below-SSC revenue is earned in SPs where MIDP < £106.47/MWh SSC: the VTP still profits (paying £0 SSC under mutualisation), while GB billpayers suffer a net deadweight loss of sum(qcv × (SSC − MIDP))."
                />
              </div>
              <div className="ledger-value teal">
                {fmtGbp(selected.tariff_analysis.estimated_vtp_revenue_gbp, true)}
              </div>
              <div className="ledger-sub">
                {fmtGbp(selected.tariff_analysis.below_ssc_vtp_revenue_gbp, true)} when MIDP &lt;
                SSC ({fmtGbp(selected.tariff_analysis.deadweight_subsidy_gbp, true)} deadweight)
              </div>
            </div>
          </section>

          {/* Standalone Supplier Tariff-Clock Boundary Proof Chart */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  Supplier tariff-clock boundary proof (22:00–08:30, % of each supplier’s peak)
                  <InfoTip
                    title="Why we normalize each supplier to 0–100% of its own peak"
                    text="Because Octopus has far more EVs than EDF or British Gas, plotting raw MWh hides smaller suppliers. Normalizing each supplier's curve to 0–100% of its own daily peak lets you compare the exact minute turn-down drops at night and surges in the morning. Stepping at different half-hours matching each supplier's tariff clock proves the meters follow EV tariff clocks while claiming turn-down across expensive hours."
                  />
                </h3>
                <p className="panel-subtitle">
                  Each supplier’s curve drops when its own cheap EV rate begins (EDF 23:00, Octopus
                  23:30, E.ON 00:00) and surges the exact half-hour its cheap rate ends (British
                  Gas 05:00, Octopus 05:30, E.ON 06:00).
                </p>
              </div>

              {selected.tariff_analysis.has_tariff_clock_fingerprint ? (
                <span className="badge badge-vermilion">
                  Supplier tariff-clock fingerprint detected
                  <InfoTip
                    title="What this fingerprint proves"
                    text="This VTP's volume jumps up at the exact half-hour each individual supplier's cheap EV rate ENDS (05:00 British Gas, 05:30 Octopus, 06:00 E.ON Next) and drops at the exact half-hour each supplier's cheap rate STARTS (23:00 EDF, 23:30 Octopus, 00:00 E.ON). That proves the underlying meters are on those EV tariffs — and that routine off-peak scheduling is generating all-day turn-down claims against a daytime baseline."
                  />
                </span>
              ) : selected.tariff_analysis.offpeak_tariff_share_pct >= 80 ? (
                <span className="badge badge-teal">
                  Off-peak control: trades inside cheap EV window
                  <InfoTip
                    title="Why Capture Energy is a useful control benchmark"
                    text="Like Axle, Capture Energy has 82.7% Octopus Energy customers — yet 99.9% of Capture's turn-down happens INSIDE the 00:00–02:30 cheap EV window (pausing cars that are genuinely charging overnight) rather than claiming 18 hours of daytime turn-down."
                  />
                </span>
              ) : (
                <span className="badge badge-neutral">Uniform / non-tariff-clock schedule</span>
              )}
            </div>

            <div className="panel-body">
              {selected.tariff_analysis.has_tariff_clock_fingerprint && (
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 8,
                    marginBottom: 14,
                    fontSize: 12,
                  }}
                >
                  <span className="badge badge-neutral">
                    05:00 British Gas {selected.tariff_analysis.clock_steps.bg_0500_pct}% vs Octopus{' '}
                    {selected.tariff_analysis.clock_steps.oct_0500_pct}%
                  </span>
                  <span className="badge badge-neutral">
                    05:30 Octopus {selected.tariff_analysis.clock_steps.oct_0530_pct}% vs E.ON{' '}
                    {selected.tariff_analysis.clock_steps.eon_0530_pct}%
                  </span>
                  <span className="badge badge-neutral">
                    23:30 Octopus {selected.tariff_analysis.clock_steps.oct_2330_pct}% vs E.ON{' '}
                    {selected.tariff_analysis.clock_steps.eon_2330_pct}%
                  </span>
                  <span className="badge badge-neutral">
                    00:00 E.ON drops to {selected.tariff_analysis.clock_steps.eon_0000_pct}%
                  </span>
                </div>
              )}

              <div style={{ width: '100%', height: 265 }}>
                <ResponsiveContainer>
                  <LineChart
                    data={selected.tariff_analysis.boundary_curves}
                    margin={{ top: 18, right: 16, left: 0, bottom: 4 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                    <XAxis dataKey="time" tick={{ fontSize: 11, fill: '#6c7f94' }} interval={1} />
                    <YAxis
                      domain={[0, 100]}
                      tickFormatter={(v: number) => `${v}%`}
                      tick={{ fontSize: 11, fill: '#6c7f94' }}
                      width={44}
                    />
                    <ReferenceLine
                      x="23:00"
                      stroke="#c97a12"
                      strokeDasharray="3 3"
                      label={{ value: 'EDF 23:00', position: 'top', dy: -2, fontSize: 10, fill: '#c97a12', fontWeight: 600 }}
                    />
                    <ReferenceLine
                      x="23:30"
                      stroke="#2c5cc5"
                      strokeDasharray="3 3"
                      label={{ value: 'Oct 23:30', position: 'insideTopLeft', dx: 4, dy: 4, fontSize: 10, fill: '#2c5cc5', fontWeight: 600 }}
                    />
                    <ReferenceLine
                      x="00:00"
                      stroke="#d1432a"
                      strokeDasharray="3 3"
                      label={{ value: 'E.ON 00:00', position: 'insideTopLeft', dx: 4, dy: 20, fontSize: 10, fill: '#d1432a', fontWeight: 600 }}
                    />
                    <ReferenceLine
                      x="05:00"
                      stroke="#0b7a75"
                      strokeDasharray="3 3"
                      label={{ value: 'BG 05:00', position: 'top', dy: -2, fontSize: 10, fill: '#0b7a75', fontWeight: 600 }}
                    />
                    <ReferenceLine
                      x="05:30"
                      stroke="#2c5cc5"
                      strokeDasharray="3 3"
                      label={{ value: 'Oct 05:30', position: 'insideTopLeft', dx: 4, dy: 4, fontSize: 10, fill: '#2c5cc5', fontWeight: 600 }}
                    />
                    <ReferenceLine
                      x="06:00"
                      stroke="#d1432a"
                      strokeDasharray="3 3"
                      label={{ value: 'E.ON 06:00', position: 'insideTopLeft', dx: 4, dy: 20, fontSize: 10, fill: '#d1432a', fontWeight: 600 }}
                    />
                    <Tooltip
                      formatter={(val: number, name: string) => [`${val}% of peak SP`, name]}
                      labelFormatter={(label: string) => `Settlement period start: ${label}`}
                      contentStyle={CHART_TOOLTIP_STYLE}
                      itemStyle={{ color: '#edf3f8' }}
                      labelStyle={{ color: '#7eece5', fontWeight: 600, marginBottom: 4 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line
                      type="monotone"
                      dataKey="MERCURY"
                      name="Octopus (IOG/Go 23:30–05:30)"
                      stroke="#2c5cc5"
                      strokeWidth={2.2}
                      dot={{ r: 2 }}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="NITTWO01"
                      name="E.ON Next (Drive 00:00–06:00)"
                      stroke="#d1432a"
                      strokeWidth={2.2}
                      dot={{ r: 2 }}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="BRITGAS"
                      name="British Gas (ED 00:00–05:00)"
                      stroke="#0b7a75"
                      strokeWidth={2.2}
                      dot={{ r: 2 }}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="LENCO"
                      name="EDF (GoElectric 23:00–06:00)"
                      stroke="#c97a12"
                      strokeWidth={1.8}
                      strokeDasharray="4 2"
                      dot={{ r: 2 }}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          {/* Standalone Side-by-Side: Six-Signal Breakdown & Low-Price Farming Scatter */}
          <div className="grid-2">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">
                    Six-signal forensic breakdown
                    <InfoTip
                      title="How the 6 signals combine"
                      text="Signals 1–2 measure EV Charger Footprint (X-axis). Signals 3–6 measure Baselining Distortion Risk (Y-axis). Hover or click each signal's (i) icon for its exact formula and benchmark."
                    />
                  </h3>
                  <p className="panel-subtitle">
                    Decomposed forensic scores for {selected.company_name}
                  </p>
                </div>
              </div>
              <div className="panel-body">
                {[
                  {
                    name: 'EV-tariff supplier over-index',
                    score: selected.signals.ev_affinity_score,
                    tipTitle: 'Signal 1: EV-tariff supplier lift (EV Footprint, 55% weight)',
                    tipText:
                      'Measures what % of this VTP’s compensation lands on major UK EV-tariff suppliers (Octopus, E.ON Next, British Gas, OVO, ScottishPower) divided by their true GB electricity demand share (derived from scvp). Octopus holds ~13% of GB power demand but ~50%+ of smart EV chargers, so a 3–4× Octopus lift strongly identifies residential EV fleets.',
                    detail: `Octopus Energy: ${selected.signals.octopus_share_pct}% (${selected.signals.octopus_lift}x GB share). All EV-tariff suppliers: ${selected.signals.ev_supplier_share_pct}% (${selected.signals.ev_lift}x GB share).`,
                  },
                  {
                    name: 'National domestic footprint (14 GSPs & 2__ BMUs)',
                    score: selected.signals.domestic_footprint_score,
                    tipTitle: 'Signal 2: Geographic & domestic dispersion (EV Footprint, 35% weight)',
                    tipText:
                      'Checks how many of GB’s 14 regional GSP groups (_A to _P) are active, their Shannon entropy (0 = single site, 1 = perfectly uniform nationwide spread), and the % of volume hitting 2__ Base Supplier BMUs (domestic/SME portfolios). Grid batteries or factories cluster in 1–3 GSPs; consumer EV fleets span all 14.',
                    detail: `Active in ${selected.signals.gsp_count}/14 GB GSP groups (entropy ${selected.signals.gsp_entropy}); ${selected.signals.base_bmu_share_pct}% on Base Supplier (2__) domestic/SME BMUs.`,
                  },
                  {
                    name: 'Energy conservation violation (missing rebound)',
                    score: selected.signals.conservation_score,
                    tipTitle: 'Signal 3: One-sided turn-down asymmetry (Baselining Risk, 30% weight)',
                    tipText:
                      'EV chargers shift load rather than generate electricity: every MWh curtailed during the day must be recharged later to fill the car. If 98–100% of notified volume is positive turn-down (+QCV) and ~0% is negative turn-up (-QCV), the VTP is only submitting wholesale notifications during turn-down windows and omitting overnight recharge rebound.',
                    detail: `${selected.signals.one_sided_ratio_pct}% one-sided positive turn-down (+${selected.pos_qcv_mwh.toLocaleString('en-GB')} MWh vs ${selected.neg_qcv_mwh.toLocaleString('en-GB')} MWh turn-up).`,
                  },
                  {
                    name: 'Wholesale price insensitivity (low-price farming)',
                    score: selected.signals.low_price_farming_score,
                    tipTitle: 'Signal 4: Low-price farming & SBP correlation (Baselining Risk, 30% weight)',
                    tipText:
                      'Genuine wholesale scarcity flexibility should curtail demand when System Buy Price (SBP) is high (above the ~£106/MWh Supplier Sourcing Cost) and charge EVs when power is cheap or negative. High volume triggered when SBP < SSC or < £60/MWh, alongside a weak daily volume-vs-price correlation (r), indicates harvesting phantom turn-down at any positive price.',
                    detail: `${selected.signals.pct_below_ssc}% triggered when SBP < SSC; ${selected.signals.pct_below_60}% when SBP < £60/MWh. Daily vol-price r = ${selected.signals.daily_price_corr ?? 'n/a'}.`,
                  },
                  {
                    name: 'Continuous duty cycle & 00:00–05:30 EV cliff',
                    score: selected.signals.duty_cycle_score,
                    tipTitle: 'Signal 5: Duty cycle & EV tariff boundary (Baselining Risk, 20% weight)',
                    tipText:
                      'Counts average hours/day where the VTP claims ≥ 15% of its daily peak volume, plus the ratio of daytime/evening volume (05:30–23:00) to the 00:00–05:30 off-peak EV tariff window. A domestic EV only charges 2–4 hrs/day; claiming 14–19 hrs/day of continuous turn-down while going silent at 00:00–05:30 points to a baseline assuming daytime charging that no longer happens.',
                    detail: `Active ${selected.signals.active_hours_per_day} hrs/day avg; daytime/evening volume is ${selected.signals.day_to_night_ratio}x overnight EV window.${selected.signals.pre_event_turnup_flag ? ' Pre-evening turn-up detected.' : ''}`,
                  },
                  {
                    name: 'Multi-day persistence (frozen baseline)',
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
                        <InfoTip title={sig.tipTitle} text={sig.tipText} />
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
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">
                    Low-price farming test: daily volume vs daily average SBP
                    <InfoTip
                      title="How to read this scatter plot"
                      text="Each dot is one settlement day in the selected window. X-axis = that day's average System Buy Price (£/MWh); Y-axis = total turn-down MWh claimed by this VTP. Dots to the left of the red dashed SSC line (~£106/MWh) are cheap/windy days. Genuine price-responsive flexibility slopes steeply upward from bottom-left to top-right; a flat horizontal cloud means the VTP claims roughly the same volume whether power costs £49 or £204/MWh."
                    />
                  </h3>
                  <p className="panel-subtitle">
                    Each dot is one settled day. A flat horizontal band across cheap (left of SSC)
                    and expensive days shows price-insensitive harvesting.
                  </p>
                </div>
              </div>
              <div className="panel-body">
                <div style={{ width: '100%', height: 310 }}>
                  <ResponsiveContainer>
                    <ScatterChart margin={{ top: 12, right: 16, bottom: 24, left: 6 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                      <XAxis
                        type="number"
                        dataKey="avg_sbp"
                        name="Daily avg SBP"
                        tickFormatter={(v: number) => `£${v}`}
                        tick={{ fontSize: 11, fill: '#6c7f94' }}
                        label={{
                          value: 'Daily average System Buy Price (£/MWh)',
                          position: 'insideBottom',
                          offset: -12,
                          fontSize: 11.5,
                          fill: '#43566b',
                        }}
                      />
                      <YAxis
                        type="number"
                        dataKey="pos_qcv_mwh"
                        name="Daily turn-down"
                        unit=" MWh"
                        tick={{ fontSize: 11, fill: '#6c7f94' }}
                        width={74}
                      />
                      <ReferenceLine
                        x={selected.daily_series[0]?.avg_ssc ?? 106}
                        stroke="#d1432a"
                        strokeDasharray="4 4"
                        label={{
                          value: 'SSC',
                          position: 'insideTopRight',
                          fill: '#d1432a',
                          fontSize: 11,
                        }}
                      />
                      <Tooltip
                        content={({ payload }) => {
                          if (!payload || !payload.length) return null;
                          const d = payload[0].payload as ForensicVtp['daily_series'][number];
                          const cheap = d.avg_sbp < d.avg_ssc;
                          return (
                            <div style={{ ...CHART_TOOLTIP_STYLE, padding: '9px 11px' }}>
                              <div style={{ fontWeight: 700, color: '#7eece5' }}>
                                {d.date} ({d.dow}) {cheap ? '— Cheap day (< SSC)' : '— High-price day'}
                              </div>
                              <div className="mono" style={{ marginTop: 4 }}>
                                Turn-down: {d.pos_qcv_mwh.toFixed(1)} MWh, Turn-up:{' '}
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
                        fill="#0b7a75"
                        fillOpacity={0.85}
                        isAnimationActive={false}
                      />
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>

                {selected.sub_bmus.length > 0 && (
                  <div style={{ marginTop: 18, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
                    <div
                      style={{
                        fontSize: 12.5,
                        fontWeight: 600,
                        marginBottom: 8,
                        display: 'flex',
                        alignItems: 'center',
                      }}
                    >
                      Secondary BMU portfolio tranches (suffix *001 / *002 / *003)
                      <InfoTip
                        title="Why VTPs have *001, *002, *003 SBMUs"
                        text="VTPs register one Secondary BMU per GSP group (e.g. V__AAXLE001..V__PAXLE001), and often add a second or third tranche (*002, *003) to separate Asset-Metered (CoP11) vs Boundary-Metered meters, distinct OEM fleets, or testing cohorts."
                      />
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      {selected.sub_bmus.map((sb) => (
                        <span key={sb.suffix} className="badge badge-neutral">
                          *{sb.suffix}:{' '}
                          {sb.total_qcv_mwh.toLocaleString('en-GB', { maximumFractionDigits: 0 })} MWh (
                          {sb.active_days}d)
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </section>
          </div>

          {/* Standalone Side-by-Side: Intraday 48-SP Profile & Geographic GSP Footprint */}
          <div className="grid-2">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">
                    {selected.company_name} — 48-SP profile (working vs non-working days)
                    <InfoTip
                      title="Why compare weekdays vs weekends?"
                      text="Under Elexon's BL01 historical baseline, working days (Mon–Fri) use a 10-day lookback while weekends use a separate middle-2-of-4 non-working-day lookback. Comparing both curves alongside the shaded 00:00–05:30 EV off-peak band reveals whether turn-down stops abruptly when overnight EV charging begins, and whether the red turn-up line ever rebounds."
                    />
                  </h3>
                  <p className="panel-subtitle">
                    Shaded 00:00–05:30 band shows domestic EV off-peak window alignment
                  </p>
                </div>
              </div>
              <div className="panel-body">
                <div style={{ width: '100%', height: 245 }}>
                  <ResponsiveContainer>
                    <LineChart data={selected.sp_profile} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                      <ReferenceArea x1="00:00" x2="05:00" fill="#2c5cc5" fillOpacity={0.08} />
                      <XAxis dataKey="time" tick={{ fontSize: 11, fill: '#6c7f94' }} interval={5} />
                      <YAxis tick={{ fontSize: 11, fill: '#6c7f94' }} unit=" MWh" width={64} />
                      <Tooltip
                        formatter={(v: number) => [`${v.toFixed(2)} MWh/SP`]}
                        contentStyle={CHART_TOOLTIP_STYLE}
                        itemStyle={{ color: '#edf3f8' }}
                        labelStyle={{ color: '#7eece5', fontWeight: 600 }}
                      />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Line
                        type="monotone"
                        dataKey="avg_weekday_mwh"
                        name="Working days"
                        stroke="#0b7a75"
                        strokeWidth={2}
                        dot={false}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="avg_weekend_mwh"
                        name="Weekends"
                        stroke="#2c5cc5"
                        strokeWidth={2}
                        strokeDasharray="4 3"
                        dot={false}
                        isAnimationActive={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="avg_neg_mwh"
                        name="Turn-up (-MWh)"
                        stroke="#d1432a"
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
                    />
                  </h3>
                  <p className="panel-subtitle">
                    Broad Southern/Eastern/Midlands weighting mirrors UK residential EV ownership
                  </p>
                </div>
              </div>
              <div className="panel-body">
                <div style={{ width: '100%', height: 245 }}>
                  <ResponsiveContainer>
                    <BarChart
                      data={selected.gsp_breakdown}
                      margin={{ top: 8, right: 12, left: 0, bottom: 4 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                      <XAxis dataKey="gsp_group" tick={{ fontSize: 11, fill: '#0c1b2a' }} />
                      <YAxis
                        tick={{ fontSize: 11, fill: '#6c7f94' }}
                        tickFormatter={(v: number) => `${v}%`}
                        width={42}
                      />
                      <Tooltip
                        formatter={(
                          v: number,
                          _n: string,
                          item: { payload?: { gsp_name: string; abs_qcv_mwh: number } },
                        ) => [
                          `${v}% (${item.payload?.abs_qcv_mwh.toLocaleString('en-GB')} MWh)`,
                          item.payload?.gsp_name ?? '',
                        ]}
                        contentStyle={CHART_TOOLTIP_STYLE}
                        itemStyle={{ color: '#edf3f8' }}
                        labelStyle={{ color: '#7eece5', fontWeight: 600 }}
                      />
                      <Bar
                        dataKey="share_pct"
                        fill="#2c5cc5"
                        radius={[3, 3, 0, 0]}
                        isAnimationActive={false}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </section>
          </div>

          {/* Cross-VTP Tariff-Window & Profitability Comparison Table */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  Cross-VTP tariff-window &amp; profitability comparison
                  <InfoTip
                    title="Compare continuous peak harvesters against the Capture control benchmark"
                    text="Compare Axle Energy (97.6% peak-tariff, 28.2% weekday midday, 12.8 h/d EFLH, tariff-clock match) and Powerverse (95.1% peak, 11.7 h/d) against Capture Energy (0.1% peak-tariff, 1.9 h/d EFLH — pausing EVs inside Octopus's cheap 00:00–02:30 window). Click any row to load its full dossier above."
                  />
                </h3>
                <p className="panel-subtitle">
                  Estimated wholesale revenue uses Elexon MIDP (<span className="mono">mpj</span>)
                  as a transparent proxy; click any row to inspect its supplier tariff-clock curves.
                </p>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <span className="badge badge-teal">
                  Total est. value {fmtGbp(data.market_verdict.total_estimated_vtp_revenue_gbp, true)}
                </span>
                <span className="badge badge-vermilion">
                  Deadweight {fmtGbp(data.market_verdict.total_deadweight_subsidy_gbp, true)}
                </span>
              </div>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>VTP</th>
                    <th className="num">
                      Peak-tariff %
                      <InfoTip
                        title="Share in expensive EV-tariff hours"
                        text="% of positive turn-down on EV-tariff suppliers occurring OUTSIDE each supplier's published cheap overnight window (Octopus IOG 23:30–05:30, E.ON Next Drive 00:00–06:00, British Gas / ScottishPower 00:00–05:00)."
                      />
                    </th>
                    <th className="num">
                      Wkday 09–16
                      <InfoTip
                        title="Weekday midday share (Mon–Fri 09:00–16:00)"
                        text="% of total turn-down claimed during Mon–Fri office hours (SP 19–32) when commuter EVs are typically away and daytime tariff rates are 3.5–4× overnight rates."
                      />
                    </th>
                    <th className="num">
                      EFLH
                      <InfoTip
                        title="Equivalent Full-Load Hours (h/day)"
                        text="Daily turn-down MWh divided by daily peak MW. A typical UK EV needs ~1–2 h/d of 7 kW charging; 11–13 h/d implies continuous daytime baseline harvesting."
                      />
                    </th>
                    <th className="num">
                      Est. VTP Rev
                      <InfoTip
                        title="Estimated VTP wholesale value (Σ qcv × mpj)"
                        text="Gross wholesale revenue proxy computed by multiplying each half-hour's positive qcv by Elexon's Market Index Price (MIDP). Under P415 mutualisation, the VTP does not pay SSC."
                      />
                    </th>
                    <th className="num">
                      Rev &lt; SSC
                      <InfoTip
                        title="VTP revenue when MIDP < SSC"
                        text="Revenue earned by the VTP during half-hours where wholesale power cost LESS than £106.47/MWh Supplier Sourcing Cost (i.e. turning down demand had negative system value)."
                      />
                    </th>
                    <th className="num">
                      Deadweight
                      <InfoTip
                        title="Net billpayer deadweight subsidy"
                        text="Σ qcv × (SSC − MIDP) across all SPs where MIDP < SSC: the net pounds paid out of the mutualised supplier pot above the wholesale energy value saved."
                      />
                    </th>
                    <th>Tariff clock</th>
                  </tr>
                </thead>
                <tbody>
                  {data.vtps.map((v) => {
                    const ta = v.tariff_analysis;
                    return (
                      <tr
                        key={`ta-${v.party_id}`}
                        className={`clickable ${selected?.party_id === v.party_id ? 'selected' : ''}`}
                        onClick={() => setSelectedId(v.party_id)}
                      >
                        <td>
                          <div style={{ fontWeight: 600 }}>{v.company_name}</div>
                          <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)' }}>
                            {v.party_id}
                          </div>
                        </td>
                        <td className="num">
                          <span
                            className={`badge ${
                              ta.peak_tariff_share_pct >= 85
                                ? 'badge-vermilion'
                                : ta.peak_tariff_share_pct <= 10
                                  ? 'badge-teal'
                                  : 'badge-neutral'
                            }`}
                          >
                            {ta.peak_tariff_share_pct.toFixed(1)}%
                          </span>
                        </td>
                        <td className="num">{ta.weekday_midday_share_pct.toFixed(1)}%</td>
                        <td className="num">{ta.eflh_hours_per_day.toFixed(1)} h/d</td>
                        <td className="num" style={{ fontWeight: 600 }}>
                          {fmtGbp(ta.estimated_vtp_revenue_gbp, true)}
                        </td>
                        <td className="num">{fmtGbp(ta.below_ssc_vtp_revenue_gbp, true)}</td>
                        <td
                          className="num"
                          style={{
                            color: ta.deadweight_subsidy_gbp > 5000 ? 'var(--vermilion)' : undefined,
                            fontWeight: ta.deadweight_subsidy_gbp > 5000 ? 600 : 400,
                          }}
                        >
                          {fmtGbp(ta.deadweight_subsidy_gbp, true)}
                        </td>
                        <td>
                          {ta.has_tariff_clock_fingerprint ? (
                            <span className="badge badge-vermilion">Clock match</span>
                          ) : ta.offpeak_tariff_share_pct >= 80 ? (
                            <span className="badge badge-teal">Off-peak only</span>
                          ) : (
                            <span className="badge badge-neutral">Uniform</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* Baseline Methodology Forensic Note: BL01/P376 vs Self-Nominated SEV */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  Can Elexon data tell BL01 (P376) apart from self-nominated baselines?
                  <InfoTip
                    title="Governance context: BSC Issue 127"
                    text="Elexon opened BSC Issue 127 on 30 October 2026 specifically because VTPs do not currently have to register or publicly declare whether they use BL01 or a custom self-nominated Submitted Expected Volume (SEV) methodology."
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
              <div className="guide-grid no-border">
                <div>
                  <strong>What Elexon publishes (and doesn’t)</strong>
                  The compact <span className="mono">primary-secondary-bm-unit-level</span> feed
                  only reports settled deviation volumes (<span className="mono">qcviji2</span>),
                  not the baseline itself. The larger <span className="mono">bm-unit-level</span>{' '}
                  feed (~380 MB/day) publishes both actual metered load (
                  <span className="mono">qmij</span>) and Settlement Expected Volume (
                  <span className="mono">sevij</span>), but does not tag whether{' '}
                  <span className="mono">sevij</span> came from SVAA’s BL01 formula or a VTP’s
                  self-nominated SEV.
                </div>
                <div>
                  <strong>Self-nominated SEV fingerprints in bm-unit-level</strong>
                  Inspecting live <span className="mono">bm-unit-level</span> data (2026-10-01 SF)
                  shows clear self-nomination tells: <strong>Joulen (POWONTEC)</strong> posts
                  cleanly rounded 2-decimal <span className="mono">sevij</span> values (
                  <span className="mono">-1.15</span>, <span className="mono">-1.00</span>,{' '}
                  <span className="mono">-0.90 MWh</span>) rather than 4-decimal smart-meter
                  averages, and <strong>Zenobe (ZENOBER1)</strong> only populates{' '}
                  <span className="mono">sevij</span> sparsely during active events.
                </div>
                <div>
                  <strong>BL01 &amp; un-notified overnight rebound proof</strong>
                  By contrast, <strong>Axle Energy</strong>, <strong>Reflexi</strong>,{' '}
                  <strong>Powerverse</strong>, and <strong>Capture</strong> carry 4-decimal{' '}
                  <span className="mono">sevij</span> across all 48 SPs — consistent with BL01 or
                  meter-derived models. Comparing <span className="mono">qmij</span> against{' '}
                  <span className="mono">sevij</span> in SP 1–2 (00:00–01:00) catches Reflexi
                  pulling <strong>-9.84 to -10.70 MWh</strong> vs a{' '}
                  <strong>-7.18 to -7.81 MWh</strong> baseline (overnight EV charging rebound) with{' '}
                  <span className="mono">wmi2j = 0</span> so zero negative compensation is booked.
                </div>
              </div>
            </div>
          </section>

          {/* Detailed Methodology, Formulas & Reasoning Reference Panel */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  Methodology, economic reasoning &amp; analytical caveats
                </h3>
                <p className="panel-subtitle">
                  Step-by-step explanation of how these settlement tests establish whether EV
                  optimisers are profiting from unrepresentative daytime baselines.
                </p>
              </div>
            </div>
            <div className="panel-body">
              <div className="guide-grid no-border">
                <div>
                  <strong>The EV-tariff counterfactual paradox</strong>
                  UK EV tariffs create a ~3.5–4× overnight discount: Intelligent Octopus Go (~7p vs
                  ~26p, 23:30–05:30; Octopus Go 00:30–05:30), E.ON Next Drive (~6.7p vs ~25p,
                  00:00–06:00), British Gas Electric Driver (~7.9p vs ~26p, 00:00–05:00), and EDF
                  GoElectric (23:00–06:00). A
                  rational driver on these tariffs schedules EV charging overnight and does{' '}
                  <em>not</em> charge continuously from 05:30 to 23:30. Yet if a VTP’s baseline
                  assumes daytime/evening charging (via frozen BL01 non-event days or a flat
                  self-nominated SEV), routine tariff-driven non-charging looks like “demand
                  turn-down” all day long.
                </div>
                <div>
                  <strong>Why supplier tariff-clock jumps are decisive</strong>
                  When we plot each supplier’s turn-down curve separately on a 0–100% peak scale,
                  Axle Energy and Powerverse jump sharply at <strong>05:00 for British Gas</strong>,{' '}
                  <strong>05:30 for Octopus</strong>, and <strong>06:00 for E.ON Next</strong> — and
                  collapse at <strong>23:00 for EDF</strong>, <strong>23:30 for Octopus</strong>,
                  and <strong>00:00 for E.ON Next</strong>. Those supplier-specific half-hour steps
                  prove two things simultaneously: (a) the meters really are EV-tariff households,
                  and (b) the moment each tariff switches from cheap to expensive (causing chargers
                  to stop automatically), the VTP books massive “flexibility” turn-down against its
                  baseline.
                </div>
                <div>
                  <strong>Why VTPs profit even on cheap windy days</strong>
                  Under P415 mutualisation, the VTP does not pay the £106.47/MWh Supplier Sourcing
                  Cost (<span className="mono">ssc</span>); all GB suppliers pay it via{' '}
                  <span className="mono">scvp</span>. Example: on a windy £49/MWh day, turning down
                  an EV that wasn’t going to charge anyway costs the VTP £0 and earns ~£49/MWh on
                  the wholesale market, while forcing GB billpayers to pay £106.47/MWh in supplier
                  compensation — a £57.47/MWh net deadweight loss. Genuine flexibility only
                  dispatches when wholesale value exceeds the true cost of shifting load.
                </div>
                <div>
                  <strong>Exact formulas &amp; honest caveats</strong>
                  <span className="mono">Est. VTP Rev = Σ(qcv × mpj)</span> (MIDP proxy; actual
                  bilateral/EPEX trade prices may differ slightly).{' '}
                  <span className="mono">Deadweight = Σ(qcv × (ssc − mpj))</span> where{' '}
                  <span className="mono">mpj &lt; ssc</span>.{' '}
                  <span className="mono">EFLH = avg(daily MWh ÷ daily peak MW)</span>. Caveats:
                  (1) Portfolios may mix EV chargers with home batteries/heat pumps (which can
                  legitimately discharge during daytime/evening, though batteries still require
                  matching overnight recharge rebound); (2) a minority of EV owners remain on
                  flat-rate standard variable tariffs; (3) exact individual-MPAN baselines are not
                  published in Elexon data.
                </div>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
