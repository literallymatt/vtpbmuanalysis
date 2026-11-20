import { useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { api } from '../api';
import type { ExplorerResponse, PartiesResponse } from '../types';
import { fmtGbp } from '../utils/format';

interface Props {
  startDate: string;
  endDate: string;
}

const GSP_LIST = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'J', 'K', 'L', 'M', 'N', 'P'];

export function ExplorerView({ startDate, endDate }: Props) {
  const [mode, setMode] = useState<'bmu_pair' | 'raw' | 'parties'>('bmu_pair');
  const [search, setSearch] = useState('');
  const [gsp, setGsp] = useState('');
  const [spFilter, setSpFilter] = useState('');
  const [roleFilter, setRoleFilter] = useState('VT');
  const [offset, setOffset] = useState(0);
  const [explorerData, setExplorerData] = useState<ExplorerResponse | null>(null);
  const [partiesData, setPartiesData] = useState<PartiesResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setOffset(0);
  }, [mode, search, gsp, spFilter, startDate, endDate]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        if (mode === 'parties') {
          const res = await api.getParties(roleFilter || undefined, search || undefined);
          if (!cancelled) setPartiesData(res);
        } else {
          const res = await api.getExplorer({
            start_date: startDate,
            end_date: endDate,
            group_by: mode,
            gsp_group: gsp || undefined,
            sp: spFilter ? Number(spFilter) : undefined,
            search: search || undefined,
            limit: 100,
            offset,
          });
          if (!cancelled) setExplorerData(res);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [mode, startDate, endDate, gsp, spFilter, search, offset, roleFilter]);

  const csvUrl = api.explorerCsvUrl({
    start_date: startDate,
    end_date: endDate,
    group_by: mode === 'raw' ? 'raw' : 'bmu_pair',
    gsp_group: gsp || undefined,
    sp: spFilter ? Number(spFilter) : undefined,
    search: search || undefined,
  });

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">BMU × Settlement Period explorer &amp; BSC party registry</h2>
          <p className="page-lead">
            Inspect raw Primary/Secondary BMU records from SAA-I014 or search the live Elexon BSC
            Signatories directory (Party ID → Company Name and registered market roles).
          </p>
        </div>

        {mode !== 'parties' && (
          <a href={csvUrl} className="btn btn-sm btn-teal" style={{ textDecoration: 'none' }}>
            <Download size={13} />
            <span>Export CSV</span>
          </a>
        )}
      </div>

      <div className="filter-bar">
        <div style={{ display: 'inline-flex', gap: 4 }}>
          <button
            type="button"
            className={`btn btn-sm ${mode === 'bmu_pair' ? 'btn-primary' : ''}`}
            onClick={() => setMode('bmu_pair')}
          >
            BMU pairs (aggregated)
          </button>
          <button
            type="button"
            className={`btn btn-sm ${mode === 'raw' ? 'btn-primary' : ''}`}
            onClick={() => setMode('raw')}
          >
            Raw BMU × SP rows
          </button>
          <button
            type="button"
            className={`btn btn-sm ${mode === 'parties' ? 'btn-primary' : ''}`}
            onClick={() => setMode('parties')}
          >
            BSC signatories directory
          </button>
        </div>

        <input
          type="search"
          className="input"
          placeholder={
            mode === 'parties'
              ? 'Search Party ID or company name...'
              : 'Search BMU ID or Party ID (e.g. V__AAXLE001, MERCURY)...'
          }
          style={{ minWidth: 280 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        {mode !== 'parties' ? (
          <>
            <select
              className="select"
              value={gsp}
              onChange={(e) => setGsp(e.target.value)}
              aria-label="Filter GSP Group"
            >
              <option value="">All GSP groups</option>
              {GSP_LIST.map((g) => (
                <option key={g} value={g}>
                  GSP _{g}
                </option>
              ))}
            </select>
            <input
              type="number"
              className="input"
              min={1}
              max={50}
              placeholder="SP (1–48)"
              style={{ width: 96 }}
              value={spFilter}
              onChange={(e) => setSpFilter(e.target.value)}
            />
          </>
        ) : (
          <select
            className="select"
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            aria-label="Filter BSC role"
          >
            <option value="">All BSC roles (752+)</option>
            <option value="VT">VT — Virtual Trading Party</option>
            <option value="VP">VP — Virtual Lead Party</option>
            <option value="AV">AV — Asset Metering VLP</option>
            <option value="TS">TS — Licensed Supplier</option>
            <option value="TG">TG — Generator</option>
          </select>
        )}
      </div>

      {mode === 'parties' ? (
        <section className="panel">
          <div className="panel-header">
            <h3 className="panel-title">
              Elexon BSC Signatories ({partiesData?.total ?? 0} matching parties)
            </h3>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Party ID</th>
                  <th>Company name</th>
                  <th>Registered BSC roles</th>
                  <th className="num">BMUs</th>
                  <th className="num">VTP comp (stored)</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={6} className="loading-state">
                      Loading directory...
                    </td>
                  </tr>
                )}
                {!loading &&
                  partiesData?.items.slice(0, 200).map((p) => (
                    <tr key={p.party_id}>
                      <td className="mono" style={{ fontWeight: 600 }}>
                        {p.party_id}
                      </td>
                      <td>{p.company_name}</td>
                      <td>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {p.roles.map((r) => (
                            <span
                              key={r}
                              className={`badge ${
                                r === 'VT' || r === 'AV'
                                  ? 'badge-teal'
                                  : r === 'TS'
                                    ? 'badge-indigo'
                                    : 'badge-neutral'
                              }`}
                              title={partiesData.role_descriptions[r] ?? r}
                            >
                              {r}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="num">{p.bmu_count}</td>
                      <td className="num">
                        {Math.abs(p.vtp_comp_gbp) > 0.01 ? fmtGbp(p.vtp_comp_gbp) : '—'}
                      </td>
                      <td style={{ fontSize: 12, color: 'var(--ink-muted)' }}>{p.source}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <section className="panel">
          <div className="panel-header">
            <h3 className="panel-title">
              {mode === 'bmu_pair' ? 'Aggregated Secondary → Primary BMU pairs' : 'Raw BMU × SP records'}{' '}
              ({explorerData?.total.toLocaleString('en-GB') ?? 0} total)
            </h3>
            {explorerData && explorerData.total > explorerData.limit && (
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - 100))}
                >
                  Previous
                </button>
                <span className="mono" style={{ fontSize: 12 }}>
                  {offset + 1}–{Math.min(offset + 100, explorerData.total)} of{' '}
                  {explorerData.total.toLocaleString('en-GB')}
                </span>
                <button
                  type="button"
                  className="btn btn-sm"
                  disabled={offset + 100 >= explorerData.total}
                  onClick={() => setOffset(offset + 100)}
                >
                  Next
                </button>
              </div>
            )}
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                {mode === 'bmu_pair' ? (
                  <tr>
                    <th>Secondary BMU (VTP)</th>
                    <th>Primary BMU (Supplier)</th>
                    <th>GSP</th>
                    <th className="num">Days</th>
                    <th className="num">Active SPs</th>
                    <th className="num">QSD (MWh)</th>
                    <th className="num">QCV (MWh)</th>
                    <th className="num">Compensation</th>
                  </tr>
                ) : (
                  <tr>
                    <th>Date</th>
                    <th>SP</th>
                    <th>Secondary BMU (VTP)</th>
                    <th>Primary BMU (Supplier)</th>
                    <th>GSP</th>
                    <th className="num">QSD (MWh)</th>
                    <th className="num">QCV (MWh)</th>
                    <th className="num">SSC</th>
                    <th className="num">Comp (£)</th>
                  </tr>
                )}
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={9} className="loading-state">
                      Querying SQLite settlement store...
                    </td>
                  </tr>
                )}
                {!loading &&
                  explorerData?.items.map((r, i) =>
                    mode === 'bmu_pair' ? (
                      <tr key={`${r.sec_bmu_id}-${r.pri_bmu_id}-${i}`}>
                        <td>
                          <div className="mono" style={{ fontWeight: 600 }}>
                            {r.sec_bmu_id}
                          </div>
                          <div style={{ fontSize: 11.5, color: 'var(--ink-secondary)' }}>
                            {r.sec_company_name} ({r.sec_party_id})
                          </div>
                        </td>
                        <td>
                          <div className="mono" style={{ fontWeight: 600 }}>
                            {r.pri_bmu_id}
                          </div>
                          <div style={{ fontSize: 11.5, color: 'var(--ink-secondary)' }}>
                            {r.pri_company_name} ({r.pri_party_id})
                          </div>
                        </td>
                        <td>
                          <span className="badge badge-neutral">_{r.gsp_group}</span>
                        </td>
                        <td className="num">{r.active_days}</td>
                        <td className="num">{r.active_sps}</td>
                        <td className="num">{Number(r.qsd_mwh).toFixed(2)}</td>
                        <td className="num">{Number(r.qcv_mwh).toFixed(2)}</td>
                        <td className="num" style={{ fontWeight: 600 }}>
                          {fmtGbp(Number(r.comp_gbp))}
                        </td>
                      </tr>
                    ) : (
                      <tr key={`${r.settlement_date}-${r.sp}-${r.sec_bmu_id}-${r.pri_bmu_id}-${i}`}>
                        <td className="mono">{r.settlement_date}</td>
                        <td className="mono">
                          {String(r.sp).padStart(2, '0')} ({r.time})
                        </td>
                        <td>
                          <span className="mono">{r.sec_bmu_id}</span>{' '}
                          <span style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>
                            {r.sec_party_id}
                          </span>
                        </td>
                        <td>
                          <span className="mono">{r.pri_bmu_id}</span>{' '}
                          <span style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>
                            {r.pri_party_id}
                          </span>
                        </td>
                        <td>_{r.gsp_group}</td>
                        <td className="num">{Number(r.qsd_mwh).toFixed(3)}</td>
                        <td className="num">{Number(r.qcv_mwh).toFixed(3)}</td>
                        <td className="num">£{Number(r.ssc).toFixed(2)}</td>
                        <td className="num" style={{ fontWeight: 600 }}>
                          {fmtGbp(Number(r.comp_gbp))}
                        </td>
                      </tr>
                    ),
                  )}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
