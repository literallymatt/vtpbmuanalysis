import { Calendar, DownloadCloud, RefreshCw } from 'lucide-react';
import type { StatusResponse } from '../types';

interface Props {
  startDate: string;
  endDate: string;
  onStartChange: (v: string) => void;
  onEndChange: (v: string) => void;
  onOpenSync: () => void;
  onRefresh: () => void;
  status: StatusResponse | null;
}

export function TopBar({
  startDate,
  endDate,
  onStartChange,
  onEndChange,
  onOpenSync,
  onRefresh,
  status,
}: Props) {
  const isSyncing = status?.sync.status === 'running';
  const runSummary = status?.run_breakdown
    .map((r) => `${r.run_type} (${r.days}d)`)
    .join(', ');

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="date-control">
          <Calendar size={14} />
          <span>From</span>
          <input
            type="date"
            value={startDate}
            min={status?.granular_min_date ?? undefined}
            max={endDate}
            onChange={(e) => onStartChange(e.target.value)}
            aria-label="Start settlement date"
          />
          <span>to</span>
          <input
            type="date"
            value={endDate}
            min={startDate}
            max={status?.granular_max_date ?? undefined}
            onChange={(e) => onEndChange(e.target.value)}
            aria-label="End settlement date"
          />
        </div>
        {runSummary && (
          <span className="badge badge-neutral" title="Settlement runs loaded in local store">
            Runs: {runSummary}
          </span>
        )}
        {isSyncing && status && (
          <span className="badge badge-amber">
            Syncing {status.sync.completed_days}/{status.sync.total_days} ({status.sync.current_date})
          </span>
        )}
      </div>

      <div className="topbar-left">
        <button type="button" className="btn btn-sm" onClick={onRefresh}>
          <RefreshCw size={13} />
          <span>Reload view</span>
        </button>
        <button type="button" className="btn btn-sm btn-primary" onClick={onOpenSync}>
          <DownloadCloud size={13} />
          <span>Fetch Elexon dates</span>
        </button>
      </div>
    </header>
  );
}
