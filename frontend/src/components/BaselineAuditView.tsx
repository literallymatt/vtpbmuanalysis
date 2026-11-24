import { Fragment, useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Download,
  DownloadCloud,
  FileText,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
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
import { api } from '../api';
import type { BaselineAuditResponse, BaselineAuditVtp } from '../types';
import { fmtGbp, fmtMwh, shortDate } from '../utils/format';
import { InfoTip } from './InfoTip';

interface Props {
  data: BaselineAuditResponse;
  selectedPartyId: string;
  selectedBmuId: string;
  isRefreshing: boolean;
  onSelectVtp: (partyId: string) => void;
  onSelectBmu: (partyId: string, bmuId: string) => void;
  onOpenSync: () => void;
}

const CHART_TOOLTIP_STYLE = {
  background: '#0c1b2a',
  color: '#edf3f8',
  border: '1px solid #223b56',
  borderRadius: 6,
  fontSize: 12,
  boxShadow: '0 8px 24px rgba(12, 27, 42, 0.24)',
};

function fmtSigned(val: number | null | undefined, decimals = 2, suffix = ''): string {
  if (val === null || val === undefined || Number.isNaN(val)) return '—';
  const sign = val > 0 ? '+' : '';
  return `${sign}${val.toLocaleString('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}${suffix ? ` ${suffix}` : ''}`;
}

function fmtNum(val: number | null | undefined, decimals = 2, suffix = ''): string {
  if (val === null || val === undefined || Number.isNaN(val)) return '—';
  return `${val.toLocaleString('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}${suffix}`;
}

function methodologyTone(cls: string): 'vermilion' | 'amber' | 'indigo' | 'teal' | 'neutral' {
  const s = (cls || '').toLowerCase();
  if (s.includes('frozen') || s.includes('sparse') || s.includes('inflated') || s.includes('sign-invert')) {
    return 'vermilion';
  }
  if (s.includes('quantis') || s.includes('self') || s.includes('hybrid')) return 'amber';
  if (s.includes('bl01') || s.includes('p376')) return 'indigo';
  if (s.includes('clean') || s.includes('balanced') || s.includes('standard')) return 'teal';
  return 'neutral';
}

function badgeClassForMethod(cls: string): string {
  const tone = methodologyTone(cls);
  return `badge badge-${tone}`;
}

function heroBadgeClassForMethod(cls: string): string {
  const tone = methodologyTone(cls);
  return tone === 'neutral' ? 'hero-badge' : `hero-badge ${tone}`;
}

function shortMethodTag(cls: string): string {
  const s = (cls || '').toLowerCase();
  if (s.includes('bl01') && s.includes('frozen')) return 'BL01 Frozen';
  if (s.includes('bl01')) return 'BL01';
  if (s.includes('quantis')) return 'Self-Nom 2dp';
  if (s.includes('sparse')) return 'Sparse SEV';
  if (s.includes('self')) return 'Self-Nom';
  if (s.includes('hybrid')) return 'Hybrid';
  if (s.includes('sign-invert')) return 'Sign-Inv';
  if (s.includes('insufficient')) return 'No SEV';
  return cls.slice(0, 14);
}

export function BaselineAuditView({
  data,
  selectedPartyId,
  selectedBmuId,
  isRefreshing,
  onSelectVtp,
  onSelectBmu,
  onOpenSync,
}: Props) {
  const [guideOpen, setGuideOpen] = useState(false);
  const [expandedVtps, setExpandedVtps] = useState<Record<string, boolean>>({});
  const [expandAllSbmus, setExpandAllSbmus] = useState(false);

  const detail = data.selected_detail;
  const activePartyId = detail?.party_id ?? selectedPartyId ?? data.vtps[0]?.party_id ?? '';
  const activeBmuId = detail?.sec_bmu_id ?? selectedBmuId ?? '';

  const selectedVtp: BaselineAuditVtp | undefined = useMemo(
    () => data.vtps.find((v) => v.party_id === activePartyId) ?? data.vtps[0],
    [data.vtps, activePartyId],
  );

  // Keep the top pill switcher concise by showing VTPs with actual baseline data
  // (plus the currently selected VTP if clicked from the full table below)
  const switcherVtps = useMemo(() => {
    const withBaselines = data.vtps.filter(
      (v) =>
        v.methodology_class !== 'Insufficient Baseline Data' || v.party_id === activePartyId,
    );
    return withBaselines.length > 0 ? withBaselines : data.vtps;
  }, [data.vtps, activePartyId]);

  // Market-weighted asymmetric selection gap across audited VTPs
  const marketSelectionStats = useMemo(() => {
    if (!data.vtps.length) {
      return { activePos: 0, inactivePos: 0, gapPp: 0, totalSbmus: 0 };
    }
    const totalWeight = data.vtps.reduce((acc, v) => acc + Math.max(0, v.settled_turndown_mwh), 0);
    let activePos = 0;
    let inactivePos = 0;
    let totalSbmus = 0;
    for (const v of data.vtps) {
      totalSbmus += v.sbmu_count;
      const w = totalWeight > 0 ? Math.max(0, v.settled_turndown_mwh) / totalWeight : 1 / data.vtps.length;
      activePos += v.active_positive_pct * w;
      inactivePos += v.inactive_positive_pct * w;
    }
    return {
      activePos,
      inactivePos,
      gapPp: activePos - inactivePos,
      totalSbmus,
    };
  }, [data.vtps]);

  const csvUrl = api.baselineAuditCsvUrl(data.start_date, data.end_date);
  const briefingUrl = api.baselineAuditBriefingUrl(
    data.start_date,
    data.end_date,
    activePartyId || undefined,
    activeBmuId || undefined,
  );

  const toggleExpandVtp = (partyId: string) => {
    setExpandedVtps((prev) => ({ ...prev, [partyId]: !prev[partyId] }));
  };

  const handleToggleExpandAll = () => {
    const next = !expandAllSbmus;
    setExpandAllSbmus(next);
    const map: Record<string, boolean> = {};
    for (const v of data.vtps) {
      map[v.party_id] = next;
    }
    setExpandedVtps(map);
  };

  const hasData = data.baseline_days > 0 && data.vtps.length > 0 && detail !== null;
  const ms = data.market_summary;
  const counterEconomicPct =
    ms.total_settled_turndown_mwh > 0
      ? (ms.counter_economic_turndown_mwh / ms.total_settled_turndown_mwh) * 100
      : 0;
  const otherVtpsCount = Math.max(0, data.vtps.length - ms.bl01_vtps_count - ms.self_nom_vtps_count);

  const spTimes = useMemo(
    () => new Set((detail?.sp_overlay ?? []).map((pt) => pt.time)),
    [detail?.sp_overlay],
  );
  const hasOffPeakBand = spTimes.has('00:00') && spTimes.has('05:30');

  return (
    <div>
      {/* 1. Page Header with 1-click Policy Brief & CSV Export */}
      <div className="page-header">
        <div>
          <h2 className="page-title">
            Baseline accuracy &amp; BL01 (P376) audit
            <InfoTip
              title="Direct SBMU baseline verification (SAA-I014 bm-unit-level)"
              text="Compares actual metered demand (qm) directly against Elexon's settled Submitted Expected Volume (sev) and Wholesale Market Instruction (wmi) across every Secondary BMU (V__*). Evaluates non-active forecast error, un-notified rebound leakage, asymmetric notification selection, and P376 BL01 lookback reconstruction."
            />
          </h2>
          <p className="page-lead">
            Empirical audit of Secondary BMU (<span className="mono">V__*</span>) baselines as demand
            forecasts, examining how P376 BL01 lookback rules and self-nominated{' '}
            <span className="mono">sev</span> methodologies interact with P415 wholesale settlement
            under BSC Issue 127 &amp; P510.
          </p>
        </div>

        <div className="header-actions">
          <a
            className={`btn btn-sm btn-primary${!hasData ? ' disabled' : ''}`}
            href={hasData ? briefingUrl : undefined}
            download
            aria-disabled={!hasData}
            onClick={(e) => {
              if (!hasData) e.preventDefault();
            }}
          >
            <FileText size={13.5} />
            <span>Download policy brief (.md)</span>
          </a>
          <a
            className={`btn btn-sm${!hasData ? ' disabled' : ''}`}
            href={hasData ? csvUrl : undefined}
            download
            aria-disabled={!hasData}
            onClick={(e) => {
              if (!hasData) e.preventDefault();
            }}
          >
            <Download size={13.5} />
            <span>Export audit CSV</span>
          </a>
        </div>
      </div>

      {/* Graceful Empty State when baseline_days === 0 */}
      {!hasData && (
        <section className="panel">
          <div className="empty-audit-state">
            <span className="badge badge-amber">No Secondary BMU baseline records loaded</span>
            <h3>Fetch Secondary BMU baseline data to run the BL01 &amp; SEV audit</h3>
            <p>
              No <span className="mono">sbmu_baseline_sp</span> records were found between{' '}
              <span className="mono">{data.start_date}</span> and{' '}
              <span className="mono">{data.end_date}</span>. To audit actual metered demand (
              <span className="mono">qm</span>) against settlement baselines (
              <span className="mono">sev</span>) and wholesale notifications (
              <span className="mono">wmi</span>), fetch Elexon’s{' '}
              <span className="mono">bm-unit-level</span> SAA-I014 reports with the baseline option
              enabled.
            </p>
            <div className="header-actions" style={{ marginTop: 4 }}>
              <button type="button" className="btn btn-teal" onClick={onOpenSync}>
                <DownloadCloud size={14} />
                <span>Fetch Elexon baselines</span>
              </button>
              <span className="mono" style={{ fontSize: 12, color: 'var(--ink-muted)' }}>
                CLI: uv run python -m backend.ingest --baselines
              </span>
            </div>
          </div>
        </section>
      )}

      {hasData && detail && (
        <>
          {/* Collapsible Methodology & Sign-Convention Guide */}
          <div className="guide-box">
            <button
              type="button"
              className="guide-toggle"
              onClick={() => setGuideOpen((o) => !o)}
              aria-expanded={guideOpen}
            >
              <span>Audit methodology &amp; SAA-I014 sign convention (Ofgem / Issue 127 &amp; P510)</span>
              {guideOpen ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </button>
            {guideOpen && (
              <div className="guide-grid">
                <div>
                  <strong>SAA-I014 Sign Convention &amp; Implied Deviation</strong>
                  In Elexon <span className="mono">bm-unit-level</span> files, demand is recorded as
                  negative MWh (e.g. <span className="mono">qm = −6.72</span>,{' '}
                  <span className="mono">sev = −7.88</span>). Implied deviation is{' '}
                  <span className="mono">qm − sev</span>: positive values indicate actual demand fell
                  below baseline (turn-down); negative values indicate actual demand exceeded baseline
                  (rebound or load surge). Intraday MW charts plot positive demand magnitudes (
                  <span className="mono">−qm × 2</span> and <span className="mono">−sev × 2</span>).
                </div>
                <div>
                  <strong>Active (wmi &gt; 0) vs Non-Active (wmi = 0) Baselines</strong>
                  Non-active settlement periods (<span className="mono">wmi = 0</span>) provide a clean
                  out-of-sample test of how well <span className="mono">sev</span> forecasts metered
                  load when no wholesale activation is notified. High non-active MAE/bias indicates
                  baseline forecast error, while large negative deviations during{' '}
                  <span className="mono">wmi = 0</span> quantify unsettled rebound.
                </div>
                <div>
                  <strong>BL01 (P376) vs Self-Nominated SEV Classification</strong>
                  We independently reconstruct the P376 BL01 rolling 10-working-day / middle-2-of-4
                  weekend baseline (both raw and excluding heavily-activated Event Days) and test fit (
                  <span className="mono">R²</span>), drift, 2-decimal-place quantisation, and{' '}
                  <span className="mono">sev</span> coverage to distinguish BL01-consistent units from
                  self-nominated counterfactuals.
                </div>
              </div>
            )}
          </div>

          {/* 2. Objective Policy Verdict Banner + 5-Cell Flush Audit Strip */}
          <section className="verdict-banner">
            <h2>
              {ms.headline}
              <InfoTip
                title="Regulatory audit summary"
                text="Summarises market-wide baseline accuracy, un-notified rebound leakage, counter-economic turn-down below Supplier Sourcing Cost (SSC), and methodology classification across all Secondary BMUs with baseline records in the selected date range."
              />
            </h2>
            <p>
              Across <strong>{data.baseline_days} baseline days</strong> (
              <span className="mono">{data.start_date}</span> to{' '}
              <span className="mono">{data.end_date}</span>), audited Secondary BMUs settled{' '}
              <strong>{fmtMwh(ms.total_settled_turndown_mwh, 0)}</strong> of wholesale turn-down while
              recording <strong>{fmtMwh(ms.total_unsettled_rebound_mwh, 0)}</strong> (
              {ms.rebound_leakage_pct.toFixed(1)}%) of un-notified rebound where actual demand exceeded
              baseline without wholesale settlement (<span className="mono">wmi = 0</span>), representing{' '}
              <strong>{fmtGbp(ms.implied_unsettled_comp_gbp, true)}</strong> in implied unsettled
              compensation offset.
            </p>
          </section>

          <section className="ledger-strip" aria-label="Market-wide baseline audit headline metrics">
            <div className="ledger-cell">
              <div className="ledger-label">
                Non-active forecast MAE &amp; bias
                <InfoTip
                  title="Out-of-sample baseline forecast accuracy (wmi = 0)"
                  text="Mean Absolute Error (MAE) and signed mean bias of (qm − sev) across settlement periods with no wholesale activation (wmi = 0). A clean demand forecast should exhibit low MAE and near-zero bias; persistent bias or high MAE shows the settlement baseline poorly predicts actual load."
                />
              </div>
              <div className="ledger-value">{fmtNum(ms.non_active_mae_mwh, 2, ' MWh')}</div>
              <div className="ledger-sub">
                Mean bias {fmtSigned(ms.non_active_bias_mwh, 2, 'MWh/SP')} when{' '}
                <span className="mono">wmi = 0</span>
              </div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                Un-notified rebound MWh &amp; £
                <InfoTip
                  title="Unsettled rebound leakage"
                  text="Total MWh by which actual metered demand exceeded the settlement baseline (qm < sev, i.e. load surge / recharge) during settlement periods where no wholesale instruction was notified (wmi = 0), valued at the concurrent Supplier Sourcing Cost (SSC)."
                />
              </div>
              <div
                className={`ledger-value ${ms.rebound_leakage_pct >= 25 ? 'vermilion' : 'amber'}`}
              >
                {fmtMwh(ms.total_unsettled_rebound_mwh, 0)}
              </div>
              <div className="ledger-sub">
                {ms.rebound_leakage_pct.toFixed(1)}% of turn-down ·{' '}
                {fmtGbp(ms.implied_unsettled_comp_gbp, true)} implied SSC
              </div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                Asymmetric selection gap
                <InfoTip
                  title="Free-option notification asymmetry"
                  text="Volume-weighted percentage-point difference between the share of Active SPs (wmi > 0) with positive turn-down deviation (qm > sev) versus Inactive SPs (wmi = 0). A large positive gap reflects asymmetric notification: favourable deviations are notified for settlement while adverse deviations remain unsettled."
                />
              </div>
              <div
                className={`ledger-value ${marketSelectionStats.gapPp >= 25 ? 'vermilion' : 'teal'}`}
              >
                {fmtSigned(marketSelectionStats.gapPp, 1, 'pp')}
              </div>
              <div className="ledger-sub">
                {marketSelectionStats.activePos.toFixed(1)}% pos. active vs{' '}
                {marketSelectionStats.inactivePos.toFixed(1)}% inactive
              </div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                BL01 vs Self-nominated split
                <InfoTip
                  title="Inferred baseline methodology split"
                  text="Count of audited VTPs whose settled sev matches P376 BL01 historical rolling-day averages (high BL01 R²) versus those exhibiting self-nominated counterfactual signatures (low BL01 R², 2 d.p. quantisation, or sparse SEV submission only during active periods)."
                />
              </div>
              <div className="ledger-value indigo">
                {ms.bl01_vtps_count} BL01 · {ms.self_nom_vtps_count} Self
              </div>
              <div className="ledger-sub">
                {data.vtps.length} VTPs ({otherVtpsCount} other) across{' '}
                {marketSelectionStats.totalSbmus} <span className="mono">V__*</span> SBMUs
              </div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                Counter-economic turn-down
                <InfoTip
                  title="Turn-down settled below Supplier Sourcing Cost (SBP < SSC)"
                  text="Settled positive turn-down volume notified during settlement periods where the wholesale System Buy Price (SBP) was below the Supplier Sourcing Cost (SSC ≈ £106/MWh). Under P415 mutualisation, VTPs do not face the SSC directly, weakening price discipline during abundant or low-price periods."
                />
              </div>
              <div className={`ledger-value ${counterEconomicPct >= 40 ? 'vermilion' : 'amber'}`}>
                {fmtMwh(ms.counter_economic_turndown_mwh, 0)}
              </div>
              <div className="ledger-sub">
                {counterEconomicPct.toFixed(1)}% of settled turn-down while SBP &lt; SSC
              </div>
            </div>
          </section>

          {/* 3. Interactive VTP Pill Switcher + Individual Secondary BMU Dropdown */}
          <div className="audit-controls-row">
            <div className="vtp-switcher" role="tablist" aria-label="Select VTP for baseline audit">
              <span className="vtp-switcher-label">Audit VTP:</span>
              {switcherVtps.map((v) => (
                <button
                  key={v.party_id}
                  type="button"
                  role="tab"
                  aria-selected={activePartyId === v.party_id}
                  className={`vtp-pill ${activePartyId === v.party_id ? 'active' : ''}`}
                  onClick={() => onSelectVtp(v.party_id)}
                >
                  <span>{v.company_name}</span>
                  <span className="vtp-pill-share">{shortMethodTag(v.methodology_class)}</span>
                </button>
              ))}
            </div>

            {selectedVtp && (
              <div className="sbmu-select-wrap">
                <label htmlFor="audit-sbmu-select">Secondary BMU:</label>
                <select
                  id="audit-sbmu-select"
                  className="select mono"
                  value={activeBmuId}
                  onChange={(e) => onSelectBmu(selectedVtp.party_id, e.target.value)}
                >
                  <option value="">
                    All SBMUs for {selectedVtp.company_name} ({selectedVtp.sbmus.length})
                  </option>
                  {selectedVtp.sbmus.map((b) => (
                    <option key={b.sec_bmu_id} value={b.sec_bmu_id}>
                      {b.sec_bmu_id} ({b.gsp_group || 'GB'}) —{' '}
                      {b.settled_turndown_mwh.toLocaleString('en-GB', {
                        maximumFractionDigits: 0,
                      })}{' '}
                      MWh
                    </option>
                  ))}
                </select>
                {isRefreshing && <span className="badge badge-neutral">Updating…</span>}
              </div>
            )}
          </div>

          {/* Dark Slate Hero Band for Selected VTP / SBMU */}
          <section className="dossier-hero">
            <div className="dossier-hero-top">
              <div>
                <h3 className="dossier-hero-name">
                  {detail.company_name}{' '}
                  <span className="mono" style={{ fontSize: 15, color: '#8ba0b7', fontWeight: 500 }}>
                    {detail.sec_bmu_id ? `${detail.sec_bmu_id} · ${detail.party_id}` : detail.party_id}
                  </span>
                </h3>
                <p className="dossier-hero-sub">
                  {detail.sec_bmu_id
                    ? `Individual Secondary BMU drill-down · Settled turn-down ${fmtMwh(detail.metrics.settled_turndown_mwh, 1)} · Unsettled rebound ${fmtMwh(detail.metrics.unsettled_rebound_mwh, 1)} (${detail.metrics.rebound_leakage_pct.toFixed(1)}%)`
                    : `Portfolio aggregate across ${selectedVtp?.sbmu_count ?? detail.metrics.sbmu_count ?? 0} Secondary BMUs (${selectedVtp?.active_days ?? detail.metrics.active_days ?? 0} active days) · Settled turn-down ${fmtMwh(detail.metrics.settled_turndown_mwh, 1)} · Unsettled rebound ${fmtMwh(detail.metrics.unsettled_rebound_mwh, 1)} (${detail.metrics.rebound_leakage_pct.toFixed(1)}%)`}
                </p>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                <span className={heroBadgeClassForMethod(detail.methodology_class)}>
                  {detail.methodology_class}
                </span>
                {selectedVtp?.roles.map((r) => (
                  <span
                    key={r}
                    className={`hero-badge ${r === 'AV' || r === 'VT' ? 'teal' : ''}`}
                  >
                    {r}
                  </span>
                ))}
                <span className="hero-badge">
                  BL01 R² {fmtNum(detail.metrics.bl01_r2, 2)}
                </span>
                <span className="hero-badge">
                  SEV cov {fmtNum(detail.metrics.sev_coverage_pct, 0, '%')}
                </span>
              </div>
            </div>

            {detail.methodology_reasons.length > 0 && (
              <ul className="dossier-hero-findings">
                {detail.methodology_reasons.map((reason, idx) => (
                  <li key={idx}>{reason}</li>
                ))}
              </ul>
            )}
          </section>

          {/* Scoped 4-Cell Diagnostic Ledger for Selected VTP / SBMU */}
          <section className="ledger-strip" aria-label="Selected VTP or SBMU baseline diagnostics">
            <div className="ledger-cell">
              <div className="ledger-label">
                Non-active MAE / RMSE
                <InfoTip
                  title="Selected unit non-active forecast error"
                  text="Mean Absolute Error and Root Mean Square Error of (qm − sev) across periods with wmi = 0 for the selected VTP or Secondary BMU. MAPE reports percentage error relative to actual metered demand."
                />
              </div>
              <div className="ledger-value">
                {fmtNum(detail.metrics.non_active_mae_mwh, 3, ' MWh')}
              </div>
              <div className="ledger-sub">
                RMSE {fmtNum(detail.metrics.non_active_rmse_mwh, 3, ' MWh')} · MAPE{' '}
                {fmtNum(detail.metrics.non_active_mape_pct, 1, '%')}
              </div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                Over-forecast rate &amp; bias
                <InfoTip
                  title="Baseline over-forecast frequency (wmi = 0)"
                  text="Share of non-active periods where baseline demand exceeded actual demand (sev more negative than qm, i.e. qm − sev > 0). An unbiased forecast sits near 50%; persistent departure indicates structural upward or downward baseline bias."
                />
              </div>
              <div
                className={`ledger-value ${
                  detail.metrics.over_forecast_rate_pct >= 62 ||
                  detail.metrics.over_forecast_rate_pct <= 38
                    ? 'amber'
                    : 'teal'
                }`}
              >
                {fmtNum(detail.metrics.over_forecast_rate_pct, 1, '%')}
              </div>
              <div className="ledger-sub">
                Mean non-active bias {fmtSigned(detail.metrics.non_active_bias_mwh, 3, 'MWh')}
              </div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                BL01 fit (R²) &amp; lookback drift
                <InfoTip
                  title="P376 BL01 reconstruction fit and drift"
                  text="Coefficient of determination (R²) between Elexon's settled sev and our reconstructed BL01 10-working-day / weekend rolling baseline. Drift measures average divergence (settled sev minus rolling BL01), exposing frozen lookback windows when Event Days are repeatedly excluded."
                />
              </div>
              <div className="ledger-value indigo">{fmtNum(detail.metrics.bl01_r2, 3)}</div>
              <div className="ledger-sub">
                BL01 MAE {fmtNum(detail.metrics.bl01_mae_mwh, 3, ' MWh')} · Drift{' '}
                {fmtSigned(detail.metrics.bl01_drift_mwh, 3, 'MWh')}
              </div>
            </div>

            <div className="ledger-cell">
              <div className="ledger-label">
                SEV quantisation &amp; coverage
                <InfoTip
                  title="Self-nominated SEV structural indicators"
                  text="2 d.p. quantisation reports the share of non-zero sev values rounded exactly to 0.01 MWh (typical of manually or algorithmically nominated schedules rather than multi-day metered averages). SEV coverage measures the share of SPs carrying a non-zero baseline."
                />
              </div>
              <div
                className={`ledger-value ${
                  detail.metrics.quantised_2dp_pct >= 70 || detail.metrics.sev_coverage_pct < 75
                    ? 'vermilion'
                    : ''
                }`}
              >
                {fmtNum(detail.metrics.quantised_2dp_pct, 1, '%')} 2 d.p.
              </div>
              <div className="ledger-sub">
                SEV coverage {fmtNum(detail.metrics.sev_coverage_pct, 1, '%')} · Unsettled comp{' '}
                {fmtGbp(detail.metrics.implied_unsettled_comp_gbp, true)}
              </div>
            </div>
          </section>

          {/* 4. Centerpiece Chart: Actual Metered Demand (qm) vs Settlement Baseline (sev) SP 1-48 */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  Actual metered demand (qm) vs settlement baseline (sev) across SP 1–48 (MW)
                  <InfoTip
                    title="Intraday baseline vs actual demand overlay"
                    text="Plots average half-hourly demand magnitude across all audited days: dashed dark line is settlement baseline demand (−sev × 2 MW); solid indigo line is actual metered demand (−qm × 2 MW). Teal bars show settled turn-down (wmi > 0); vermilion bars show un-notified rebound where actual demand exceeded baseline while wmi = 0 (concentrated in the shaded 00:00–05:30 off-peak window)."
                  />
                </h3>
                <p className="panel-subtitle">
                  {detail.sec_bmu_id ?? detail.company_name} — demand magnitudes plotted as positive
                  MW (<span className="mono">−qm × 2</span> vs <span className="mono">−sev × 2</span>
                  ), exposing settled daytime turn-down against un-notified overnight recharge rebound.
                </p>
              </div>
              <div className="header-actions">
                <span className="badge badge-teal">
                  Settled turn-down {fmtMwh(detail.metrics.settled_turndown_mwh, 0)}
                </span>
                <span className="badge badge-vermilion">
                  Unsettled rebound {fmtMwh(detail.metrics.unsettled_rebound_mwh, 0)}
                </span>
              </div>
            </div>
            <div className="panel-body">
              <div style={{ width: '100%', height: 345 }}>
                <ResponsiveContainer>
                  <ComposedChart
                    data={detail.sp_overlay}
                    margin={{ top: 16, right: 18, left: 4, bottom: 6 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                    {hasOffPeakBand && (
                      <ReferenceArea
                        x1="00:00"
                        x2="05:30"
                        fill="#2c5cc5"
                        fillOpacity={0.075}
                        label={{
                          value: '00:00–05:30 off-peak window',
                          position: 'insideTopLeft',
                          fill: '#2c5cc5',
                          fontSize: 10.5,
                          fontWeight: 600,
                        }}
                      />
                    )}
                    <XAxis
                      dataKey="time"
                      tick={{ fontSize: 11, fill: '#6c7f94' }}
                      interval={3}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: '#6c7f94' }}
                      tickFormatter={(v: number) => `${v.toFixed(1)}`}
                      width={52}
                      label={{
                        value: 'Average MW',
                        angle: -90,
                        position: 'insideLeft',
                        style: { textAnchor: 'middle' },
                        offset: 6,
                        fontSize: 11.5,
                        fill: '#43566b',
                      }}
                    />
                    <Tooltip
                      content={({ payload }) => {
                        if (!payload || !payload.length) return null;
                        const pt = payload[0].payload as (typeof detail.sp_overlay)[number];
                        return (
                          <div style={{ ...CHART_TOOLTIP_STYLE, padding: '10px 12px', minWidth: 225 }}>
                            <div style={{ fontWeight: 700, color: '#7eece5', marginBottom: 4 }}>
                              SP {pt.sp} ({pt.time})
                            </div>
                            <div className="mono" style={{ fontSize: 11.5, lineHeight: 1.6 }}>
                              <div>Baseline demand (sev): {pt.baseline_demand_mw.toFixed(2)} MW</div>
                              <div>Actual demand (qm): {pt.actual_demand_mw.toFixed(2)} MW</div>
                              <div style={{ color: '#7eece5' }}>
                                Settled turn-down (wmi&gt;0): {pt.settled_turndown_mw.toFixed(2)} MW
                              </div>
                              <div style={{ color: '#ffaba0' }}>
                                Unsettled rebound (wmi=0): {pt.unsettled_rebound_mw.toFixed(2)} MW
                              </div>
                              <div style={{ color: '#9bb0c6', marginTop: 4 }}>
                                Activation rate: {pt.activation_rate_pct.toFixed(1)}% · SBP £
                                {pt.avg_sbp.toFixed(1)} (SSC £{pt.avg_ssc.toFixed(1)})
                              </div>
                            </div>
                          </div>
                        );
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar
                      dataKey="settled_turndown_mw"
                      name="Settled turn-down (wmi > 0)"
                      fill="#0b7a75"
                      fillOpacity={0.38}
                      radius={[2, 2, 0, 0]}
                      isAnimationActive={false}
                    />
                    <Bar
                      dataKey="unsettled_rebound_mw"
                      name="Unsettled rebound (wmi = 0)"
                      fill="#d1432a"
                      fillOpacity={0.42}
                      radius={[2, 2, 0, 0]}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="baseline_demand_mw"
                      name="Settlement baseline (sev)"
                      stroke="#0c1b2a"
                      strokeWidth={2.2}
                      strokeDasharray="5 3"
                      dot={false}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="actual_demand_mw"
                      name="Actual metered demand (qm)"
                      stroke="#2c5cc5"
                      strokeWidth={2.4}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-footnote">
                <span>
                  Note: Where baseline (<span className="mono">sev</span>) sits above actual load (
                  <span className="mono">qm</span>) during active SPs, turn-down is settled. Where
                  actual load spikes above baseline during <span className="mono">wmi = 0</span>,
                  recharge rebound is absorbed outside wholesale settlement.
                </span>
                <span className="mono">48 settlement periods · {data.baseline_days}d avg</span>
              </div>
            </div>
          </section>

          {/* 5. Split 2-Column Charts: Cherry-Picking Histogram & IDA Pre-Event Ramp Check */}
          <div className="grid-2">
            <section className="panel">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">
                    Asymmetric free-option selection (qm − sev distribution)
                    <InfoTip
                      title="Active vs inactive implied deviation histogram"
                      text="Compares the empirical distribution of implied deviation (qm − sev) across Active periods (wmi > 0, teal) versus Inactive periods (wmi = 0, vermilion). Positive bins indicate actual load below baseline (turn-down); negative bins indicate load above baseline (rebound). Truncating notification to positive outcomes creates asymmetric option value."
                    />
                  </h3>
                  <p className="panel-subtitle">
                    Share of SPs by <span className="mono">qm − sev</span> bin: Active (
                    <span className="mono">wmi &gt; 0</span>) vs Inactive (
                    <span className="mono">wmi = 0</span>)
                  </p>
                </div>
              </div>
              <div className="panel-body">
                {detail.cherry_pick_hist.length > 0 ? (
                  <div style={{ width: '100%', height: 275 }}>
                    <ResponsiveContainer>
                      <BarChart
                        data={detail.cherry_pick_hist}
                        margin={{ top: 10, right: 12, left: 0, bottom: 20 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                        <XAxis
                          dataKey="bin_label"
                          tick={{ fontSize: 10.5, fill: '#6c7f94' }}
                          interval={0}
                          angle={-22}
                          textAnchor="end"
                          height={44}
                        />
                        <YAxis
                          tick={{ fontSize: 11, fill: '#6c7f94' }}
                          tickFormatter={(v: number) => `${v}%`}
                          width={44}
                        />
                        <Tooltip
                          content={({ payload }) => {
                            if (!payload || !payload.length) return null;
                            const b = payload[0].payload as (typeof detail.cherry_pick_hist)[number];
                            return (
                              <div style={{ ...CHART_TOOLTIP_STYLE, padding: '10px 12px', minWidth: 210 }}>
                                <div style={{ fontWeight: 700, color: '#7eece5', marginBottom: 4 }}>
                                  Deviation bin: {b.bin_label} MWh
                                </div>
                                <div className="mono" style={{ fontSize: 11.5, lineHeight: 1.6 }}>
                                  <div style={{ color: '#7eece5' }}>
                                    Active (wmi &gt; 0): {b.active_pct.toFixed(1)}% (
                                    {b.active_count.toLocaleString('en-GB')} SPs)
                                  </div>
                                  <div style={{ color: '#ffaba0' }}>
                                    Inactive (wmi = 0): {b.inactive_pct.toFixed(1)}% (
                                    {b.inactive_count.toLocaleString('en-GB')} SPs)
                                  </div>
                                  <div style={{ color: '#9bb0c6', marginTop: 3 }}>
                                    {b.bin_center >= 0
                                      ? 'Positive = actual load below baseline'
                                      : 'Negative = actual load above baseline (rebound)'}
                                  </div>
                                </div>
                              </div>
                            );
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Bar
                          dataKey="active_pct"
                          name="Active (wmi > 0)"
                          fill="#0b7a75"
                          radius={[3, 3, 0, 0]}
                          isAnimationActive={false}
                        />
                        <Bar
                          dataKey="inactive_pct"
                          name="Inactive (wmi = 0)"
                          fill="#d1432a"
                          fillOpacity={0.82}
                          radius={[3, 3, 0, 0]}
                          isAnimationActive={false}
                        />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="loading-state" style={{ padding: '48px 12px' }}>
                    Insufficient active/inactive observations to construct deviation histogram.
                  </div>
                )}
                <div className="chart-footnote">
                  <span>
                    Active: <strong>{detail.metrics.active_positive_pct.toFixed(1)}%</strong>{' '}
                    positive (mean {fmtSigned(detail.metrics.active_mean_dev_mwh, 3, 'MWh')})
                  </span>
                  <span>
                    Inactive: <strong>{detail.metrics.inactive_positive_pct.toFixed(1)}%</strong>{' '}
                    positive (mean {fmtSigned(detail.metrics.inactive_mean_dev_mwh, 3, 'MWh')})
                  </span>
                </div>
              </div>
            </section>

            <section className="panel">
              <div className="panel-header">
                <div>
                  <h3 className="panel-title">
                    BL01 In-Day Adjustment (IDA) pre-event ramp check
                    <InfoTip
                      title="Pre-activation demand vs baseline (T−6 to T−1 SPs)"
                      text="Examines the 6 half-hours (3 hours) immediately preceding transitions from wmi = 0 to wmi > 0. Under P376 BL01, an additive In-Day Adjustment compares metered demand in the pre-event window against the unadjusted baseline; systematic positive excess load prior to activation lifts the subsequent event baseline."
                    />
                  </h3>
                  <p className="panel-subtitle">
                    Offsets <span className="mono">−6</span> to <span className="mono">−1</span> SPs
                    prior to <span className="mono">wmi: 0 → &gt;0</span> activation start
                  </p>
                </div>
                <span
                  className={`badge ${
                    detail.ida_pre_ramp.pre_ramp_excess_mw > 0.2 ? 'badge-amber' : 'badge-neutral'
                  }`}
                >
                  {detail.ida_pre_ramp.transitions_count} starts ·{' '}
                  {fmtSigned(detail.ida_pre_ramp.pre_ramp_excess_mw, 2, 'MW')}
                </span>
              </div>
              <div className="panel-body">
                {detail.ida_pre_ramp.transitions_count > 0 &&
                detail.ida_pre_ramp.pre_event_window_sp_offsets.length > 0 ? (
                  <div style={{ width: '100%', height: 275 }}>
                    <ResponsiveContainer>
                      <ComposedChart
                        data={detail.ida_pre_ramp.pre_event_window_sp_offsets}
                        margin={{ top: 10, right: 14, left: 2, bottom: 8 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                        <XAxis
                          dataKey="label"
                          tick={{ fontSize: 11, fill: '#6c7f94' }}
                        />
                        <YAxis
                          tick={{ fontSize: 11, fill: '#6c7f94' }}
                          tickFormatter={(v: number) => `${v.toFixed(1)}`}
                          width={46}
                          label={{
                            value: 'MW',
                            angle: -90,
                            position: 'insideLeft',
                            style: { textAnchor: 'middle' },
                            offset: 6,
                            fontSize: 11.5,
                            fill: '#43566b',
                          }}
                        />
                        <ReferenceLine y={0} stroke="#c6d0dd" />
                        <Tooltip
                          content={({ payload }) => {
                            if (!payload || !payload.length) return null;
                            const pt = payload[0]
                              .payload as (typeof detail.ida_pre_ramp.pre_event_window_sp_offsets)[number];
                            return (
                              <div style={{ ...CHART_TOOLTIP_STYLE, padding: '10px 12px', minWidth: 215 }}>
                                <div style={{ fontWeight: 700, color: '#7eece5', marginBottom: 4 }}>
                                  Pre-event offset: {pt.label} ({pt.offset_sp} SP)
                                </div>
                                <div className="mono" style={{ fontSize: 11.5, lineHeight: 1.6 }}>
                                  <div>Actual demand: {pt.avg_actual_mw.toFixed(2)} MW</div>
                                  <div>Baseline (sev): {pt.avg_baseline_mw.toFixed(2)} MW</div>
                                  <div
                                    style={{
                                      color: pt.excess_load_mw > 0 ? '#ffd48a' : '#7eece5',
                                    }}
                                  >
                                    Excess load (actual − sev):{' '}
                                    {fmtSigned(pt.excess_load_mw, 2, 'MW')}
                                  </div>
                                </div>
                              </div>
                            );
                          }}
                        />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        <Bar
                          dataKey="excess_load_mw"
                          name="Excess load (actual − sev)"
                          radius={[3, 3, 0, 0]}
                          isAnimationActive={false}
                        >
                          {detail.ida_pre_ramp.pre_event_window_sp_offsets.map((pt) => (
                            <Cell
                              key={pt.offset_sp}
                              fill={pt.excess_load_mw >= 0 ? '#c97a12' : '#0b7a75'}
                              fillOpacity={0.55}
                            />
                          ))}
                        </Bar>
                        <Line
                          type="monotone"
                          dataKey="avg_actual_mw"
                          name="Avg actual load (MW)"
                          stroke="#2c5cc5"
                          strokeWidth={2.3}
                          dot={{ r: 3 }}
                          isAnimationActive={false}
                        />
                        <Line
                          type="monotone"
                          dataKey="avg_baseline_mw"
                          name="Avg baseline sev (MW)"
                          stroke="#0c1b2a"
                          strokeWidth={2}
                          strokeDasharray="4 3"
                          dot={{ r: 2.5 }}
                          isAnimationActive={false}
                        />
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                ) : (
                  <div className="loading-state" style={{ padding: '48px 16px' }}>
                    No discrete <span className="mono">wmi: 0 → &gt;0</span> activation starts
                    observed for this selection (either continuously active across all periods or
                    inactive during the window).
                  </div>
                )}
                <div className="chart-footnote">
                  <span>
                    Positive amber bars indicate actual demand exceeded baseline immediately prior to
                    activation start.
                  </span>
                  <span className="mono">
                    Mean pre-ramp: {fmtSigned(detail.ida_pre_ramp.pre_ramp_excess_mw, 2, 'MW')}
                  </span>
                </div>
              </div>
            </section>
          </div>

          {/* 6. BL01 (P376) Reconstruction vs Settled sev Daily Chart */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  BL01 (P376) reconstruction vs settled baseline (sev) — daily trajectory
                  <InfoTip
                    title="Testing Event-Day lookback freeze and BL01 divergence"
                    text="Compares daily total actual metered demand (qm) and Elexon's settled baseline (sev) against two independent P376 BL01 reconstructions: rolling 10-working-day / middle-2-of-4-weekend mean using all prior days (BL01 raw, teal) versus excluding heavily-activated Event Days (BL01 excl. event days, amber). Persistent divergence between settled sev and rolling actual load reveals Event-Day freeze or self-nominated counterfactuals."
                  />
                </h3>
                <p className="panel-subtitle">
                  Daily metered demand vs settled <span className="mono">sev</span> and reconstructed
                  BL01 lookback curves across the {data.baseline_days}-day audit window.
                </p>
              </div>
              <div className="header-actions">
                <span className="badge badge-indigo">
                  BL01 R² {fmtNum(detail.metrics.bl01_r2, 3)}
                </span>
                <span className="badge badge-neutral">
                  MAE {fmtNum(detail.metrics.bl01_mae_mwh, 2, ' MWh')}
                </span>
                <span className="badge badge-amber">
                  Drift {fmtSigned(detail.metrics.bl01_drift_mwh, 2, 'MWh')}
                </span>
              </div>
            </div>
            <div className="panel-body">
              <div style={{ width: '100%', height: 305 }}>
                <ResponsiveContainer>
                  <LineChart
                    data={detail.bl01_daily_series}
                    margin={{ top: 12, right: 18, left: 6, bottom: 6 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                    <XAxis
                      dataKey="date"
                      tickFormatter={shortDate}
                      tick={{ fontSize: 11, fill: '#6c7f94' }}
                      minTickGap={18}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: '#6c7f94' }}
                      width={56}
                      label={{
                        value: 'Daily MWh',
                        angle: -90,
                        position: 'insideLeft',
                        style: { textAnchor: 'middle' },
                        offset: 4,
                        fontSize: 11.5,
                        fill: '#43566b',
                      }}
                    />
                    <Tooltip
                      content={({ payload }) => {
                        if (!payload || !payload.length) return null;
                        const d = payload[0].payload as (typeof detail.bl01_daily_series)[number];
                        return (
                          <div style={{ ...CHART_TOOLTIP_STYLE, padding: '10px 12px', minWidth: 235 }}>
                            <div style={{ fontWeight: 700, color: '#7eece5', marginBottom: 4 }}>
                              {d.date} ({d.dow}) · {d.active_sps}/48 active SPs
                            </div>
                            <div className="mono" style={{ fontSize: 11.5, lineHeight: 1.6 }}>
                              <div>Actual demand (qm): {d.actual_demand_mwh.toFixed(1)} MWh</div>
                              <div>Settled baseline (sev): {d.settled_sev_mwh.toFixed(1)} MWh</div>
                              <div style={{ color: '#7eece5' }}>
                                BL01 raw (10d rolling):{' '}
                                {d.bl01_raw_mwh !== null ? `${d.bl01_raw_mwh.toFixed(1)} MWh` : 'Warmup'}
                              </div>
                              <div style={{ color: '#ffd48a' }}>
                                BL01 excl. event days:{' '}
                                {d.bl01_excl_mwh !== null
                                  ? `${d.bl01_excl_mwh.toFixed(1)} MWh`
                                  : 'Warmup'}
                              </div>
                              <div style={{ color: '#9bb0c6', marginTop: 4 }}>
                                Settled turn-down: {d.settled_turndown_mwh.toFixed(1)} MWh ·
                                Unsettled rebound: {d.unsettled_rebound_mwh.toFixed(1)} MWh
                              </div>
                            </div>
                          </div>
                        );
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line
                      type="monotone"
                      dataKey="actual_demand_mwh"
                      name="Actual demand (qm)"
                      stroke="#2c5cc5"
                      strokeWidth={2.2}
                      dot={{ r: 2 }}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="settled_sev_mwh"
                      name="Settled baseline (sev)"
                      stroke="#0c1b2a"
                      strokeWidth={2.4}
                      dot={{ r: 2 }}
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="bl01_raw_mwh"
                      name="BL01 raw (rolling 10WD/2of4WE)"
                      stroke="#0b7a75"
                      strokeWidth={2}
                      strokeDasharray="5 3"
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="bl01_excl_mwh"
                      name="BL01 excl. event days (P376)"
                      stroke="#c97a12"
                      strokeWidth={2}
                      strokeDasharray="3 3"
                      dot={false}
                      connectNulls
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-footnote">
                <span>
                  Early dates in the window serve as the lookback warmup for BL01 rolling averages;
                  once populated, divergence between <span className="mono">settled sev</span> and{' '}
                  <span className="mono">BL01 raw</span> exposes Event-Day freeze or non-BL01
                  self-nomination.
                </span>
                <span className="mono">{detail.bl01_daily_series.length} settlement days</span>
              </div>
            </div>
          </section>

          {/* 7A. Perverse Dispatch by Price Regime Chart */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  Dispatch vs wholesale price regime (System Buy Price buckets)
                  <InfoTip
                    title="Price-discipline test across SBP regimes"
                    text="Buckets all settlement periods by Elexon System Buy Price (SBP) relative to the Supplier Sourcing Cost (SSC ≈ £106/MWh). Economically efficient demand turn-down should concentrate in scarcity hours (> £106/MWh), with load turn-up or charging during negative and low-price hours (< £50/MWh). Large settled turn-down below £106/MWh indicates distorted price incentives under SSC mutualisation."
                  />
                </h3>
                <p className="panel-subtitle">
                  Compares settled turn-down, settled turn-up, and un-notified rebound across five SBP
                  price regimes for {detail.sec_bmu_id ?? detail.company_name}.
                </p>
              </div>
            </div>
            <div className="panel-body">
              <div style={{ width: '100%', height: 285 }}>
                <ResponsiveContainer>
                  <BarChart
                    data={detail.price_regimes}
                    margin={{ top: 10, right: 18, left: 6, bottom: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" />
                    <XAxis
                      dataKey="regime"
                      tick={{ fontSize: 11.5, fill: '#43566b' }}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: '#6c7f94' }}
                      width={56}
                      label={{
                        value: 'Volume (MWh)',
                        angle: -90,
                        position: 'insideLeft',
                        style: { textAnchor: 'middle' },
                        offset: 4,
                        fontSize: 11.5,
                        fill: '#43566b',
                      }}
                    />
                    <Tooltip
                      content={({ payload }) => {
                        if (!payload || !payload.length) return null;
                        const r = payload[0].payload as (typeof detail.price_regimes)[number];
                        return (
                          <div style={{ ...CHART_TOOLTIP_STYLE, padding: '10px 12px', minWidth: 230 }}>
                            <div style={{ fontWeight: 700, color: '#7eece5', marginBottom: 4 }}>
                              {r.regime}
                            </div>
                            <div className="mono" style={{ fontSize: 11.5, lineHeight: 1.6 }}>
                              <div style={{ color: '#7eece5' }}>
                                Settled turn-down: {r.settled_turndown_mwh.toFixed(1)} MWh
                              </div>
                              <div style={{ color: '#b5ccf9' }}>
                                Settled turn-up: {r.settled_turnup_mwh.toFixed(1)} MWh
                              </div>
                              <div style={{ color: '#ffaba0' }}>
                                Unsettled rebound: {r.unsettled_rebound_mwh.toFixed(1)} MWh
                              </div>
                              <div style={{ color: '#9bb0c6', marginTop: 4 }}>
                                {r.sps_count.toLocaleString('en-GB')} SPs · Avg SBP £
                                {r.avg_sbp.toFixed(1)}/MWh · Active {r.activation_rate_pct.toFixed(1)}%
                              </div>
                            </div>
                          </div>
                        );
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar
                      dataKey="settled_turndown_mwh"
                      name="Settled turn-down"
                      fill="#0b7a75"
                      radius={[3, 3, 0, 0]}
                      isAnimationActive={false}
                    />
                    <Bar
                      dataKey="settled_turnup_mwh"
                      name="Settled turn-up"
                      fill="#2c5cc5"
                      radius={[3, 3, 0, 0]}
                      isAnimationActive={false}
                    />
                    <Bar
                      dataKey="unsettled_rebound_mwh"
                      name="Unsettled rebound (wmi = 0)"
                      fill="#d1432a"
                      radius={[3, 3, 0, 0]}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          {/* 7B. VTP & SBMU Methodology Classification Table */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  VTP &amp; Secondary BMU baseline methodology classification
                  <InfoTip
                    title="How to navigate the classification ledger"
                    text="Click any VTP row to load its portfolio baseline audit above. Expand a VTP (or click 'Expand all SBMUs') and click any individual V__* Secondary BMU row to inspect that unit's exact SP overlay, cherry-picking histogram, BL01 reconstruction, and price-regime dispatch."
                  />
                </h3>
                <p className="panel-subtitle">
                  Click any VTP or expanded <span className="mono">V__*</span> Secondary BMU row to
                  drill into its diagnostics above.
                </p>
              </div>
              <button type="button" className="btn btn-sm" onClick={handleToggleExpandAll}>
                {expandAllSbmus ? 'Collapse SBMUs' : 'Expand all SBMUs'}
              </button>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>
                      VTP / Secondary BMU
                      <InfoTip
                        title="Secondary BMU party & unit identifier"
                        text="Registered BSC Virtual Trading Party (or Virtual Lead Party) and its underlying V__* Secondary BMUs from Elexon SAA-I014 bm-unit-level records."
                      />
                    </th>
                    <th>
                      Methodology class
                      <InfoTip
                        title="Inferred baseline methodology"
                        text="Objective rule-based classification derived from BL01 R², BL01 lookback drift, 2-decimal-place SEV quantisation rate, and SEV coverage across non-active periods."
                      />
                    </th>
                    <th className="num">
                      SBMUs / GSP
                      <InfoTip
                        title="Unit count or Grid Supply Point group"
                        text="Number of audited Secondary BMUs for a VTP row, or the GB regional GSP group (_A through _P) for an individual Secondary BMU row."
                      />
                    </th>
                    <th className="num">
                      Settled turn-down
                      <InfoTip
                        title="Settled wholesale turn-down (MWh)"
                        text="Sum of settled positive turn-down energy during settlement periods where a Wholesale Market Instruction was notified (wmi > 0)."
                      />
                    </th>
                    <th className="num">
                      Unsettled rebound
                      <InfoTip
                        title="Un-notified rebound (MWh)"
                        text="Sum of excess metered demand above baseline (qm < sev) during periods with no wholesale notification (wmi = 0)."
                      />
                    </th>
                    <th className="num">
                      Leakage %
                      <InfoTip
                        title="Rebound leakage ratio"
                        text="Unsettled rebound MWh expressed as a percentage of settled turn-down MWh. High values indicate load shifting where turn-down is settled but recharge rebound is left outside wholesale settlement."
                      />
                    </th>
                    <th className="num">
                      Non-active MAE
                      <InfoTip
                        title="Non-active forecast Mean Absolute Error (MWh)"
                        text="Mean absolute difference |qm − sev| across settlement periods with wmi = 0."
                      />
                    </th>
                    <th className="num">
                      BL01 R²
                      <InfoTip
                        title="BL01 reconstruction R²"
                        text="Goodness of fit (R²) between Elexon's settled sev and our reconstructed P376 BL01 rolling baseline. Values near 1.0 align with BL01; low or negative values indicate self-nominated SEV."
                      />
                    </th>
                    <th className="num">
                      2 d.p. SEV
                      <InfoTip
                        title="2-decimal-place quantisation rate (%)"
                        text="Percentage of non-zero sev submissions rounded to exact 0.01 MWh increments — a structural marker of scheduled or self-nominated baselines rather than raw metered averages."
                      />
                    </th>
                    <th className="num">
                      SEV cov.
                      <InfoTip
                        title="Baseline submission coverage (%)"
                        text="Percentage of settlement periods containing a non-zero sev record. Low coverage occurs when self-nominated SEVs are submitted only in active windows."
                      />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data.vtps.map((v) => {
                    const isExpanded = Boolean(expandedVtps[v.party_id]);
                    const isVtpSelected = activePartyId === v.party_id && !activeBmuId;
                    return (
                      <Fragment key={v.party_id}>
                        <tr
                          className={`clickable ${isVtpSelected ? 'selected' : ''}`}
                          onClick={() => onSelectVtp(v.party_id)}
                        >
                          <td>
                            <div style={{ display: 'flex', alignItems: 'center' }}>
                              {v.sbmus.length > 0 && (
                                <button
                                  type="button"
                                  className="expand-btn"
                                  aria-label={
                                    isExpanded
                                      ? `Collapse SBMUs for ${v.company_name}`
                                      : `Expand SBMUs for ${v.company_name}`
                                  }
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    toggleExpandVtp(v.party_id);
                                  }}
                                >
                                  {isExpanded ? (
                                    <ChevronDown size={13} />
                                  ) : (
                                    <ChevronRight size={13} />
                                  )}
                                </button>
                              )}
                              <div>
                                <div style={{ fontWeight: 600 }}>{v.company_name}</div>
                                <div
                                  className="mono"
                                  style={{ fontSize: 11, color: 'var(--ink-muted)' }}
                                >
                                  {v.party_id} · {v.active_days}d active
                                </div>
                              </div>
                            </div>
                          </td>
                          <td>
                            <span className={badgeClassForMethod(v.methodology_class)}>
                              {v.methodology_class}
                            </span>
                          </td>
                          <td className="num">{v.sbmu_count}</td>
                          <td className="num" style={{ fontWeight: 600 }}>
                            {fmtMwh(v.settled_turndown_mwh, 1)}
                          </td>
                          <td
                            className="num"
                            style={{
                              color:
                                v.unsettled_rebound_mwh > 0 ? 'var(--vermilion)' : 'var(--ink)',
                              fontWeight: v.unsettled_rebound_mwh > 0 ? 600 : 400,
                            }}
                          >
                            {fmtMwh(v.unsettled_rebound_mwh, 1)}
                          </td>
                          <td className="num">{v.rebound_leakage_pct.toFixed(1)}%</td>
                          <td className="num">{fmtNum(v.non_active_mae_mwh, 3)}</td>
                          <td className="num">{fmtNum(v.bl01_r2, 2)}</td>
                          <td className="num">{v.quantised_2dp_pct.toFixed(0)}%</td>
                          <td className="num">{v.sev_coverage_pct.toFixed(0)}%</td>
                        </tr>

                        {isExpanded &&
                          v.sbmus.map((b) => {
                            const isBmuSelected =
                              activePartyId === v.party_id && activeBmuId === b.sec_bmu_id;
                            const bmuLeakage =
                              b.settled_turndown_mwh > 0
                                ? (b.unsettled_rebound_mwh / b.settled_turndown_mwh) * 100
                                : 0;
                            return (
                              <tr
                                key={b.sec_bmu_id}
                                className={`clickable sbmu-subrow ${isBmuSelected ? 'selected' : ''}`}
                                onClick={() => onSelectBmu(v.party_id, b.sec_bmu_id)}
                              >
                                <td>
                                  <span className="mono" style={{ fontWeight: 600, fontSize: 12 }}>
                                    {b.sec_bmu_id}
                                  </span>
                                </td>
                                <td>
                                  <span className={badgeClassForMethod(b.methodology_class)}>
                                    {b.methodology_class}
                                  </span>
                                </td>
                                <td className="num">{b.gsp_group || '—'}</td>
                                <td className="num">{fmtMwh(b.settled_turndown_mwh, 1)}</td>
                                <td className="num" style={{ color: 'var(--vermilion)' }}>
                                  {fmtMwh(b.unsettled_rebound_mwh, 1)}
                                </td>
                                <td className="num">{bmuLeakage.toFixed(1)}%</td>
                                <td className="num">{fmtNum(b.non_active_mae_mwh, 3)}</td>
                                <td className="num">{fmtNum(b.bl01_r2, 2)}</td>
                                <td className="num">{b.quantised_2dp_pct.toFixed(0)}%</td>
                                <td className="num">{b.sev_coverage_pct.toFixed(0)}%</td>
                              </tr>
                            );
                          })}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* 8. Policy Implications Footer Panel (P376 / BL01, Issue 127 & P510) */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3 className="panel-title">
                  Policy implications — P376 (BL01), BSC Issue 127 &amp; P510
                  <InfoTip
                    title="Structural reform levers highlighted by this audit"
                    text="Synthesises the empirical findings from Elexon SAA-I014 Secondary BMU data into actionable rule-design observations for Ofgem and Elexon working groups."
                  />
                </h3>
                <p className="panel-subtitle">
                  Structural incentive distortions evidenced directly in public SAA-I014 baseline and
                  metering settlement records
                </p>
              </div>
            </div>
            <div className="panel-body">
              <div className="guide-grid no-border">
                <div>
                  <strong>1. P376 (BL01) Event-Day Freeze &amp; IDA Calibration</strong>
                  Historical 10-working-day lookbacks that exclude Event Days can lock in obsolete
                  high-demand profiles when assets activate daily, causing settled baselines to drift
                  above underlying demand. Meanwhile, additive In-Day Adjustments reward elevated
                  pre-event demand in the <span className="mono">T−6</span> to{' '}
                  <span className="mono">T−1</span> window unless bounded or replaced by symmetric
                  counterfactual validation.
                </div>
                <div>
                  <strong>2. BSC Issue 127 — Mandatory Register &amp; Symmetric Rebound</strong>
                  Without a public register disclosing which Secondary BMUs use BL01 versus
                  self-nominated <span className="mono">sev</span>—and without symmetric two-way
                  settlement of post-event load rebound—VTPs hold a structural free option: positive
                  baseline deviations (<span className="mono">qm &gt; sev</span>) are notified for
                  wholesale value, while negative recharge deviations (<span className="mono">qm &lt; sev</span>
                  ) remain unsettled.
                </div>
                <div>
                  <strong>3. P510 — Supplier Compensation &amp; Price Discipline</strong>
                  Mutualising Supplier Sourcing Cost (SSC) across all suppliers insulates VTPs from
                  the underlying retail procurement cost of shifted energy. As the price-regime chart
                  demonstrates, positive turn-down continues to be notified even when System Buy Price
                  is below SSC or negative, converting baseline forecast error into deadweight
                  consumer transfers unless compensation reflects real wholesale scarcity.
                </div>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
