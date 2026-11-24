import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import { BaselineAuditView } from './components/BaselineAuditView';
import { CompensationView } from './components/CompensationView';
import { ExplorerView } from './components/ExplorerView';
import { ForensicsView } from './components/ForensicsView';
import { OverviewView } from './components/OverviewView';
import { Sidebar } from './components/Sidebar';
import { SyncModal } from './components/SyncModal';
import { TimingView } from './components/TimingView';
import { TopBar } from './components/TopBar';
import type {
  BaselineAuditResponse,
  CompensationResponse,
  ForensicsResponse,
  OverviewResponse,
  StatusResponse,
  TabId,
  TimingResponse,
} from './types';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [startDate, setStartDate] = useState<string>('2026-10-01');
  const [endDate, setEndDate] = useState<string>('2026-10-30');
  const [datesInitialized, setDatesInitialized] = useState(false);

  const [timingVtp, setTimingVtp] = useState<string>('');
  const [compVtp, setCompVtp] = useState<string>('');
  const [compSupplier, setCompSupplier] = useState<string>('');
  const [forensicsVtp, setForensicsVtp] = useState<string>('');
  const [auditVtp, setAuditVtp] = useState<string>('');
  const [auditBmu, setAuditBmu] = useState<string>('');

  const [overview, setOverview] = useState<OverviewResponse | null>(null);
  const [timing, setTiming] = useState<TimingResponse | null>(null);
  const [compensation, setCompensation] = useState<CompensationResponse | null>(null);
  const [forensics, setForensics] = useState<ForensicsResponse | null>(null);
  const [baselineAudit, setBaselineAudit] = useState<BaselineAuditResponse | null>(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncOpen, setSyncOpen] = useState(false);
  const [reloadTick, setReloadTick] = useState(0);

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.getStatus();
      setStatus(s);
      if (!datesInitialized && s.granular_min_date && s.granular_max_date) {
        setStartDate(s.granular_min_date);
        setEndDate(s.granular_max_date);
        setDatesInitialized(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [datesInitialized]);

  useEffect(() => {
    loadStatus();
  }, [loadStatus, reloadTick]);

  // Poll sync progress while a background ingestion job is running
  useEffect(() => {
    if (status?.sync.status !== 'running') return;
    const id = window.setInterval(() => {
      loadStatus();
    }, 2500);
    return () => window.clearInterval(id);
  }, [status?.sync.status, loadStatus]);

  useEffect(() => {
    if (activeTab === 'explorer') return;
    let cancelled = false;
    async function loadView() {
      setLoading(true);
      setError(null);
      try {
        if (activeTab === 'overview') {
          const d = await api.getOverview(startDate, endDate);
          if (!cancelled) setOverview(d);
        } else if (activeTab === 'timing') {
          const d = await api.getTiming(startDate, endDate, timingVtp || undefined);
          if (!cancelled) setTiming(d);
        } else if (activeTab === 'compensation') {
          const d = await api.getCompensation(
            startDate,
            endDate,
            compVtp || undefined,
            compSupplier || undefined,
          );
          if (!cancelled) setCompensation(d);
        } else if (activeTab === 'baseline_audit') {
          const d = await api.getBaselineAudit(
            startDate,
            endDate,
            auditVtp || undefined,
            auditBmu || undefined,
          );
          if (!cancelled) setBaselineAudit(d);
        } else if (activeTab === 'forensics') {
          const d = await api.getForensics(startDate, endDate);
          if (!cancelled) setForensics(d);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    loadView();
    return () => {
      cancelled = true;
    };
  }, [
    activeTab,
    startDate,
    endDate,
    timingVtp,
    compVtp,
    compSupplier,
    auditVtp,
    auditBmu,
    reloadTick,
  ]);

  function handleNavigate(tab: TabId, vtpId?: string) {
    if (tab === 'forensics' && vtpId) setForensicsVtp(vtpId);
    if (tab === 'timing' && vtpId) setTimingVtp(vtpId);
    if (tab === 'baseline_audit' && vtpId) {
      setAuditVtp(vtpId);
      setAuditBmu('');
    }
    setActiveTab(tab);
  }

  const showInitialLoader =
    loading && !error && !(activeTab === 'baseline_audit' && baselineAudit !== null);

  return (
    <div className="app-shell">
      <Sidebar activeTab={activeTab} onSelectTab={setActiveTab} status={status} />

      <div className="main-col">
        <TopBar
          startDate={startDate}
          endDate={endDate}
          onStartChange={setStartDate}
          onEndChange={setEndDate}
          onOpenSync={() => setSyncOpen(true)}
          onRefresh={() => setReloadTick((t) => t + 1)}
          status={status}
        />

        <main className="content-wrap">
          {error && <div className="error-state">Failed to load data: {error}</div>}
          {showInitialLoader && (
            <div className="loading-state">Loading Elexon SAA-I014 analytics...</div>
          )}

          {!loading && !error && activeTab === 'overview' && overview && (
            <OverviewView data={overview} onNavigate={handleNavigate} />
          )}

          {!loading && !error && activeTab === 'timing' && timing && (
            <TimingView
              data={timing}
              selectedVtp={timingVtp}
              onSelectVtp={setTimingVtp}
            />
          )}

          {!loading && !error && activeTab === 'compensation' && compensation && (
            <CompensationView
              data={compensation}
              filterVtp={compVtp}
              filterSupplier={compSupplier}
              onFilterVtp={setCompVtp}
              onFilterSupplier={setCompSupplier}
              onInspectVtp={(id) => handleNavigate('forensics', id)}
            />
          )}

          {!error && activeTab === 'baseline_audit' && baselineAudit && (
            <BaselineAuditView
              data={baselineAudit}
              selectedPartyId={auditVtp}
              selectedBmuId={auditBmu}
              isRefreshing={loading}
              onSelectVtp={(partyId) => {
                setAuditVtp(partyId);
                setAuditBmu('');
              }}
              onSelectBmu={(partyId, bmuId) => {
                setAuditVtp(partyId);
                setAuditBmu(bmuId);
              }}
              onOpenSync={() => setSyncOpen(true)}
            />
          )}

          {!loading && !error && activeTab === 'forensics' && forensics && (
            <ForensicsView data={forensics} initialVtpId={forensicsVtp} />
          )}

          {activeTab === 'explorer' && (
            <ExplorerView startDate={startDate} endDate={endDate} />
          )}
        </main>
      </div>

      <SyncModal
        open={syncOpen}
        onClose={() => setSyncOpen(false)}
        onStarted={() => {
          loadStatus();
          setReloadTick((t) => t + 1);
        }}
        progress={status?.sync ?? null}
      />
    </div>
  );
}
