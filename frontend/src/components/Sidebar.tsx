import {
  Activity,
  Clock,
  ArrowLeftRight,
  ShieldAlert,
  Table2,
} from 'lucide-react';
import type { StatusResponse, TabId } from '../types';

interface Props {
  activeTab: TabId;
  onSelectTab: (tab: TabId) => void;
  status: StatusResponse | null;
}

const ANALYSIS_NAV: { id: TabId; label: string; icon: typeof Activity }[] = [
  { id: 'overview', label: 'Settlement overview', icon: Activity },
  { id: 'timing', label: 'When VTPs trade', icon: Clock },
  { id: 'compensation', label: 'Supplier compensation', icon: ArrowLeftRight },
  { id: 'forensics', label: 'EV baselining lab', icon: ShieldAlert },
];

const DATA_NAV: { id: TabId; label: string; icon: typeof Activity }[] = [
  { id: 'explorer', label: 'BMU & party explorer', icon: Table2 },
];

export function Sidebar({ activeTab, onSelectTab, status }: Props) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-mark">
          <span className="brand-dot" aria-hidden="true" />
          <h1 className="sidebar-brand-title">GB VTP Forensics</h1>
        </div>
        <p className="sidebar-brand-sub">
          Elexon SAA-I014 settlement ledger and P415 market analytics
        </p>
      </div>

      <nav className="sidebar-nav" aria-label="Primary navigation">
        <div className="nav-section-label">Analysis</div>
        {ANALYSIS_NAV.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={`nav-item ${activeTab === id ? 'active' : ''}`}
            onClick={() => onSelectTab(id)}
          >
            <Icon size={16} strokeWidth={2} />
            <span>{label}</span>
          </button>
        ))}

        <div className="nav-section-label">Data &amp; Registry</div>
        {DATA_NAV.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className={`nav-item ${activeTab === id ? 'active' : ''}`}
            onClick={() => onSelectTab(id)}
          >
            <Icon size={16} strokeWidth={2} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-stat-row">
          <span>Granular BMU days</span>
          <span className="sidebar-stat-val">{status?.granular_days ?? '—'}</span>
        </div>
        <div className="sidebar-stat-row">
          <span>Macro history days</span>
          <span className="sidebar-stat-val">{status?.macro_days ?? '—'}</span>
        </div>
        <div className="sidebar-stat-row">
          <span>BSC signatories</span>
          <span className="sidebar-stat-val">{status?.parties_count ?? '—'}</span>
        </div>
        <div className="sidebar-stat-row">
          <span>Registered VTPs</span>
          <span className="sidebar-stat-val">
            {status?.registered_vtps_count ?? '—'}
          </span>
        </div>
        <div className="sidebar-stat-row">
          <span>BMU × SP rows</span>
          <span className="sidebar-stat-val">
            {status ? status.bmu_sp_rows.toLocaleString('en-GB') : '—'}
          </span>
        </div>
      </div>
    </aside>
  );
}
