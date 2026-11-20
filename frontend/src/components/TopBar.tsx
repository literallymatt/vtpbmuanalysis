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

function addDays(iso: string, delta: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
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
  const minD = status?.granular_min_date;
  const maxD = status?.granular_max_date;

  const last14Start = maxD ? addDays(maxD, -13) : null;
  const last7Start = maxD ? addDays(maxD, -6) : null;

  const isFull = minD && maxD && startDate === minD && endDate === maxD;
  const isLast14 = last14Start && maxD && startDate === last14Start && endDate === maxD;
  const isLast7 = last7Start && maxD && startDate === last7Start && endDate === maxD;

  const runSummary = status?.run_breakdown
    .map((r) => `${r.run_type} ${r.days}d`)
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
            min={minD ?? undefined}
            max={endDate}
            onChange={(e) => onStartChange(e.target.value)}
            aria-label="Start settlement date"
          />
          <span>to</span>
          <input
            type="date"
            value={endDate}
            min={startDate}
            max={maxD ?? undefined}
            onChange={(e) => onEndChange(e.target.value)}
            aria-label="End settlement date"
          />
        </div>

        {minD && maxD && (
          <div className="preset-group" role="group" aria-label="Quick date presets">
            <button
              type="button"
              className={`preset-btn ${isFull ? 'active' : ''}`}
              onClick={() => {
                onStartChange(minD);
                onEndChange(maxD);
              }}
            >
              All {status?.granular_days}d
            </button>
            {last14Start && last14Start >= minD && (
              <button
                type="button"
                className={`preset-btn ${isLast14 ? 'active' : ''}`}
                onClick={() => {
                  onStartChange(last14Start);
                  onEndChange(maxD);
                }}
              >
                Last 14d
              </button>
            )}
            {last7Start && last7Start >= minD && (
              <button
                type="button"
                className={`preset-btn ${isLast7 ? 'active' : ''}`}
                onClick={() => {
                  onStartChange(last7Start);
                  onEndChange(maxD);
                }}
              >
                Last 7d
              </button>
            )}
          </div>
        )}

        {runSummary && (
          <span className="badge badge-neutral" title="Settlement runs loaded in local SQLite store">
            {runSummary}
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
          <span>Reload</span>
        </button>
        <button type="button" className="btn btn-sm btn-primary" onClick={onOpenSync}>
          <DownloadCloud size={13} />
          <span>Fetch Elexon dates</span>
        </button>
      </div>
    </header>
  );
}
