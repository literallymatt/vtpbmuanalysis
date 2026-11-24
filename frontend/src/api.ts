import type {
  BaselineAuditResponse,
  CompensationResponse,
  ExplorerResponse,
  ForensicsResponse,
  OverviewResponse,
  PartiesResponse,
  StatusResponse,
  SyncProgress,
  TimingResponse,
} from './types';

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') {
      sp.set(k, String(v));
    }
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : '';
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`API ${res.status}: ${txt}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getStatus: () => getJson<StatusResponse>('/api/status'),

  getOverview: (startDate?: string, endDate?: string) =>
    getJson<OverviewResponse>(
      `/api/overview${buildQuery({ start_date: startDate, end_date: endDate })}`,
    ),

  getTiming: (startDate?: string, endDate?: string, secPartyId?: string) =>
    getJson<TimingResponse>(
      `/api/timing${buildQuery({
        start_date: startDate,
        end_date: endDate,
        sec_party_id: secPartyId,
      })}`,
    ),

  getCompensation: (
    startDate?: string,
    endDate?: string,
    secPartyId?: string,
    priPartyId?: string,
  ) =>
    getJson<CompensationResponse>(
      `/api/compensation${buildQuery({
        start_date: startDate,
        end_date: endDate,
        sec_party_id: secPartyId,
        pri_party_id: priPartyId,
      })}`,
    ),

  getForensics: (startDate?: string, endDate?: string) =>
    getJson<ForensicsResponse>(
      `/api/forensics${buildQuery({ start_date: startDate, end_date: endDate })}`,
    ),

  getBaselineAudit: (
    startDate?: string,
    endDate?: string,
    secPartyId?: string,
    secBmuId?: string,
  ) =>
    getJson<BaselineAuditResponse>(
      `/api/baseline-audit${buildQuery({
        start_date: startDate,
        end_date: endDate,
        sec_party_id: secPartyId,
        sec_bmu_id: secBmuId,
      })}`,
    ),

  baselineAuditCsvUrl: (startDate?: string, endDate?: string) =>
    `/api/baseline-audit/export.csv${buildQuery({
      start_date: startDate,
      end_date: endDate,
    })}`,

  baselineAuditBriefingUrl: (
    startDate?: string,
    endDate?: string,
    secPartyId?: string,
    secBmuId?: string,
  ) =>
    `/api/baseline-audit/briefing.md${buildQuery({
      start_date: startDate,
      end_date: endDate,
      sec_party_id: secPartyId,
      sec_bmu_id: secBmuId,
    })}`,

  getExplorer: (params: {
    start_date?: string;
    end_date?: string;
    group_by?: 'bmu_pair' | 'raw';
    sec_party_id?: string;
    pri_party_id?: string;
    gsp_group?: string;
    sp?: number;
    search?: string;
    limit?: number;
    offset?: number;
  }) => getJson<ExplorerResponse>(`/api/explorer${buildQuery(params)}`),

  explorerCsvUrl: (params: {
    start_date?: string;
    end_date?: string;
    group_by?: 'bmu_pair' | 'raw';
    sec_party_id?: string;
    pri_party_id?: string;
    gsp_group?: string;
    sp?: number;
    search?: string;
  }) => `/api/explorer/export.csv${buildQuery(params)}`,

  getParties: (role?: string, search?: string) =>
    getJson<PartiesResponse>(`/api/parties${buildQuery({ role, search })}`),

  syncDates: async (payload: {
    start_date: string;
    end_date: string;
    include_bmu_sp: boolean;
    include_baselines?: boolean;
    force?: boolean;
  }) => {
    const res = await fetch('/api/sync/dates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    return res.json();
  },

  syncReference: async () => {
    const res = await fetch('/api/sync/reference', { method: 'POST' });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  },

  getSyncProgress: () => getJson<SyncProgress>('/api/sync/progress'),
};
