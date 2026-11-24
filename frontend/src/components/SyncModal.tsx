import { useState } from 'react';
import { X } from 'lucide-react';
import { api } from '../api';
import type { SyncProgress } from '../types';

interface Props {
  open: boolean;
  onClose: () => void;
  onStarted: () => void;
  progress: SyncProgress | null;
}

export function SyncModal({ open, onClose, onStarted, progress }: Props) {
  const [start, setStart] = useState('2026-10-25');
  const [end, setEnd] = useState('2026-11-12');
  const [includeBmuSp, setIncludeBmuSp] = useState(true);
  const [includeBaselines, setIncludeBaselines] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (!open) return null;

  async function handleFetchDates() {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await api.syncDates({
        start_date: start,
        end_date: end,
        include_bmu_sp: includeBmuSp,
        include_baselines: includeBaselines,
      });
      setMsg('Ingestion started in background. Progress appears in the top bar.');
      onStarted();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshRef() {
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const res = await api.syncReference();
      setMsg(
        `Refreshed ${res.signatories} BSC signatories and ${res.bmus} BM units from Elexon.`,
      );
      onStarted();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Fetch live Elexon settlement data">
      <div className="modal">
        <div className="modal-head">
          <h3 className="panel-title">Fetch live Elexon SAA-I014 data</h3>
          <button type="button" className="btn btn-sm" onClick={onClose} aria-label="Close">
            <X size={14} />
          </button>
        </div>

        <div className="modal-body">
          <p className="panel-subtitle" style={{ marginBottom: 14 }}>
            Pulls public settlement reports directly from{' '}
            <span className="mono">data.elexon.co.uk/saa/api/v1/i014</span> using the most
            reconciled available run type (RF, R3, R2, R1, SF, or II).
          </p>

          <div className="grid-2" style={{ gap: 12 }}>
            <div className="field-group">
              <label htmlFor="sync-start">Start settlement date</label>
              <input
                id="sync-start"
                type="date"
                className="input"
                style={{ width: '100%' }}
                value={start}
                onChange={(e) => setStart(e.target.value)}
              />
            </div>
            <div className="field-group">
              <label htmlFor="sync-end">End settlement date</label>
              <input
                id="sync-end"
                type="date"
                className="input"
                style={{ width: '100%' }}
                value={end}
                onChange={(e) => setEnd(e.target.value)}
              />
            </div>
          </div>

          <div className="field-group">
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={includeBmuSp}
                onChange={(e) => setIncludeBmuSp(e.target.checked)}
              />
              <span>
                Include granular Primary/Secondary BMU × SP records (~5 MB/day)
              </span>
            </label>
          </div>

          <div className="field-group">
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={includeBaselines}
                onChange={(e) => setIncludeBaselines(e.target.checked)}
              />
              <span>
                Include Secondary BMU baselines &amp; metered demand (<span className="mono">sev</span>/
                <span className="mono">qm</span>/<span className="mono">wmi</span>, streams{' '}
                <span className="mono">bm-unit-level</span>)
              </span>
            </label>
          </div>

          {progress && progress.status !== 'idle' && (
            <div
              style={{
                padding: '10px 12px',
                background: 'var(--bg-canvas)',
                border: '1px solid var(--border)',
                borderRadius: 3,
                fontSize: 12.5,
                marginBottom: 10,
              }}
            >
              <div>
                <strong>Last job:</strong> {progress.status} ({progress.completed_days}/
                {progress.total_days} days)
              </div>
              {progress.message && (
                <div style={{ color: 'var(--ink-secondary)', marginTop: 2 }}>
                  {progress.message}
                </div>
              )}
            </div>
          )}

          {msg && (
            <div style={{ color: 'var(--teal)', fontSize: 12.5, marginTop: 8 }}>{msg}</div>
          )}
          {err && (
            <div style={{ color: 'var(--vermilion)', fontSize: 12.5, marginTop: 8 }}>{err}</div>
          )}
        </div>

        <div className="modal-foot">
          <button
            type="button"
            className="btn"
            disabled={busy}
            onClick={handleRefreshRef}
          >
            Refresh BSC parties & BMUs
          </button>
          <button
            type="button"
            className="btn btn-teal"
            disabled={busy}
            onClick={handleFetchDates}
          >
            {busy ? 'Starting...' : 'Fetch date range'}
          </button>
        </div>
      </div>
    </div>
  );
}
