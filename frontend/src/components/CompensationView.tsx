import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { CompensationResponse } from '../types';
import { fmtGbp, fmtMwh, fmtSignedGbp } from '../utils/format';

interface Props {
  data: CompensationResponse;
  filterVtp: string;
  filterSupplier: string;
  onFilterVtp: (v: string) => void;
  onFilterSupplier: (v: string) => void;
  onInspectVtp: (vtpId: string) => void;
}

export function CompensationView({
  data,
  filterVtp,
  filterSupplier,
  onFilterVtp,
  onFilterSupplier,
  onInspectVtp,
}: Props) {
  // Diverging net transfer chart: top 8 winners + top 8 payers sorted by net_transfer_gbp
  const sortedNet = [...data.suppliers].sort(
    (a, b) => b.net_transfer_gbp - a.net_transfer_gbp,
  );
  const divergingRows = [
    ...sortedNet.filter((s) => s.net_transfer_gbp > 0).slice(0, 7),
    ...sortedNet.filter((s) => s.net_transfer_gbp < 0).slice(-8),
  ].map((s) => ({
    ...s,
    shortLabel:
      s.company_name.length > 22 ? `${s.company_name.slice(0, 21)}…` : s.company_name,
  }));

  return (
    <div>
      <div className="page-header">
        <div>
          <h2 className="page-title">Who receives supplier compensation — and who pays</h2>
          <p className="page-lead">
            Under BSC P415, affected suppliers receive Supplier Compensation Cashflow (sccp) funded
            via a market-wide mutualised levy (scvp) across all GB suppliers in proportion to demand.
          </p>
        </div>

        {(filterVtp || filterSupplier) && (
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => {
              onFilterVtp('');
              onFilterSupplier('');
            }}
          >
            Clear flow filters
          </button>
        )}
      </div>

      {/* Diverging Net Mutualisation Wealth Transfer Chart */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <h3 className="panel-title">
              Net mutualisation transfer by supplier (sccp received minus scvp paid)
            </h3>
            <p className="panel-subtitle">
              Suppliers with large smart-EV customer bases receive multiples of their demand share;
              commercial/I&amp;C and non-EV suppliers subsidise the mutualised pot.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <span className="badge badge-teal">Net recipient (+£)</span>
            <span className="badge badge-vermilion">Net contributor (-£)</span>
          </div>
        </div>
        <div className="panel-body">
          <div style={{ width: '100%', height: 340 }}>
            <ResponsiveContainer>
              <BarChart
                data={divergingRows}
                layout="vertical"
                margin={{ top: 6, right: 32, left: 10, bottom: 6 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e6ecf2" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11, fill: '#6c7e91' }}
                  tickFormatter={(v: number) => fmtGbp(v, true)}
                />
                <YAxis
                  type="category"
                  dataKey="shortLabel"
                  tick={{ fontSize: 11.5, fill: '#0f2438' }}
                  width={170}
                />
                <ReferenceLine x={0} stroke="#0f2438" strokeWidth={1} />
                <Tooltip
                  formatter={(v: number) => [fmtSignedGbp(v), 'Net mutualisation transfer']}
                  contentStyle={{ border: '1px solid #bcc7d5', borderRadius: 3, fontSize: 12.5 }}
                />
                <Bar dataKey="net_transfer_gbp" radius={[2, 2, 2, 2]}>
                  {divergingRows.map((entry) => (
                    <Cell
                      key={entry.party_id}
                      fill={entry.net_transfer_gbp >= 0 ? '#006b6b' : '#c84b31'}
                      cursor="pointer"
                      onClick={() => onFilterSupplier(entry.party_id)}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* Supplier Mutualisation Ledger (full-width so all 7 columns fit without clipping) */}
      <div>
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">GB supplier compensation &amp; over-index ledger</h3>
              <p className="panel-subtitle">
                Click any supplier row to filter the VTP attribution flows below. Over-index = Comp
                share ÷ GB demand share.
              </p>
            </div>
          </div>
          <div className="table-scroll" style={{ maxHeight: 500 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Supplier (BSC Party)</th>
                  <th className="num">Received (sccp)</th>
                  <th className="num">Paid (scvp)</th>
                  <th className="num">Net transfer</th>
                  <th className="num">Demand %</th>
                  <th className="num">Comp %</th>
                  <th className="num">Over-index</th>
                </tr>
              </thead>
              <tbody>
                {data.suppliers.map((s) => (
                  <tr
                    key={s.party_id}
                    className={`clickable ${filterSupplier === s.party_id ? 'selected' : ''}`}
                    onClick={() =>
                      onFilterSupplier(filterSupplier === s.party_id ? '' : s.party_id)
                    }
                  >
                    <td>
                      <div style={{ fontWeight: 600 }}>{s.company_name}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)' }}>
                        {s.party_id}
                      </div>
                    </td>
                    <td className="num">{fmtGbp(s.sccp_gbp)}</td>
                    <td className="num">{fmtGbp(s.scvp_gbp)}</td>
                    <td
                      className="num"
                      style={{
                        fontWeight: 600,
                        color: s.net_transfer_gbp >= 0 ? 'var(--teal)' : 'var(--vermilion)',
                      }}
                    >
                      {fmtSignedGbp(s.net_transfer_gbp)}
                    </td>
                    <td className="num">{s.demand_share_pct.toFixed(1)}%</td>
                    <td className="num">{s.comp_share_pct.toFixed(1)}%</td>
                    <td className="num">
                      {s.over_index_ratio > 0 ? (
                        <span
                          className={`badge ${
                            s.over_index_ratio >= 2.0
                              ? 'badge-vermilion'
                              : s.over_index_ratio >= 1.2
                                ? 'badge-amber'
                                : 'badge-neutral'
                          }`}
                        >
                          {s.over_index_ratio.toFixed(2)}x
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">VTP → Supplier attribution flows</h3>
              <p className="panel-subtitle">
                Exact BMU-pair aggregation ({data.flows.length} active pairs
                {filterVtp ? `, VTP: ${filterVtp}` : ''}
                {filterSupplier ? `, Supplier: ${filterSupplier}` : ''})
              </p>
            </div>
            <select
              className="select"
              style={{ fontSize: 12, padding: '4px 8px' }}
              value={filterVtp}
              onChange={(e) => onFilterVtp(e.target.value)}
              aria-label="Filter flows by VTP"
            >
              <option value="">All VTPs</option>
              {data.vtps.map((v) => (
                <option key={v.party_id} value={v.party_id}>
                  {v.company_name} ({v.party_id})
                </option>
              ))}
            </select>
          </div>
          <div className="table-scroll" style={{ maxHeight: 500 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>VTP</th>
                  <th>Supplier</th>
                  <th className="num">BMU pairs</th>
                  <th className="num">QCV</th>
                  <th className="num">Compensation</th>
                </tr>
              </thead>
              <tbody>
                {data.flows.map((f) => (
                  <tr
                    key={`${f.sec_party_id}-${f.pri_party_id}`}
                    className="clickable"
                    onClick={() => onInspectVtp(f.sec_party_id)}
                  >
                    <td>
                      <div style={{ fontWeight: 600 }}>{f.sec_company_name}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)' }}>
                        {f.sec_party_id}
                      </div>
                    </td>
                    <td>
                      <div>{f.pri_company_name}</div>
                      <div className="mono" style={{ fontSize: 11, color: 'var(--ink-muted)' }}>
                        {f.pri_party_id}
                      </div>
                    </td>
                    <td className="num">{f.bmu_pair_count}</td>
                    <td className="num">{f.qcv_mwh.toLocaleString('en-GB', { maximumFractionDigits: 1 })}</td>
                    <td className="num" style={{ fontWeight: 600 }}>
                      {fmtGbp(f.comp_gbp)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* Distinction: Non-P415 BM-Only VLP Actions */}
      {data.bm_only_vlp_activity.length > 0 && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h3 className="panel-title">
                Distinction: Balancing Mechanism VLP actions (zero P415 compensation)
              </h3>
              <p className="panel-subtitle">
                Secondary BMU pairs with delivered BM volume (qsd ≠ 0) but zero wholesale
                compensation volume (qcv = 0) — typically grid-scale batteries or BM dispatch
                participating outside P415 wholesale trading.
              </p>
            </div>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Secondary VLP</th>
                  <th>Primary supplier / host</th>
                  <th className="num">SBMUs</th>
                  <th className="num">Delivered BM volume (qsd)</th>
                  <th className="num">P415 QCV</th>
                </tr>
              </thead>
              <tbody>
                {data.bm_only_vlp_activity.slice(0, 10).map((b) => (
                  <tr key={`${b.sec_party_id}-${b.pri_party_id}`}>
                    <td>
                      <span style={{ fontWeight: 600 }}>{b.sec_company_name}</span>{' '}
                      <span className="mono" style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>
                        {b.sec_party_id}
                      </span>
                    </td>
                    <td>
                      <span>{b.pri_company_name}</span>{' '}
                      <span className="mono" style={{ fontSize: 11.5, color: 'var(--ink-muted)' }}>
                        {b.pri_party_id}
                      </span>
                    </td>
                    <td className="num">{b.bmu_count}</td>
                    <td className="num">{fmtMwh(b.qsd_mwh)}</td>
                    <td className="num">0.0 MWh</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
