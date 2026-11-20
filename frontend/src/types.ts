export type TabId = 'overview' | 'timing' | 'compensation' | 'forensics' | 'explorer';

export interface SyncProgress {
  status: string;
  total_days: number;
  completed_days: number;
  skipped_days: number;
  failed_days: string[];
  current_date: string;
  message: string;
  started_at: string;
  finished_at: string;
}

export interface StatusResponse {
  granular_days: number;
  granular_min_date: string | null;
  granular_max_date: string | null;
  macro_days: number;
  macro_min_date: string | null;
  macro_max_date: string | null;
  parties_count: number;
  registered_vtps_count: number;
  bmus_count: number;
  bmu_sp_rows: number;
  run_breakdown: { run_type: string; days: number }[];
  sync: SyncProgress;
}

export interface OverviewResponse {
  start_date: string;
  end_date: string;
  granular_days: number;
  summary: {
    total_comp_gbp: number;
    daily_avg_comp_gbp: number;
    annualised_comp_gbp: number;
    net_qcv_mwh: number;
    pos_qcv_mwh: number;
    neg_qcv_mwh: number;
    party_pos_sccp_gbp: number;
    party_net_sccp_gbp: number;
    party_total_scvp_gbp: number;
    max_reconciliation_diff_gbp: number;
    active_vtps: number;
    active_suppliers: number;
    active_sbmus: number;
    avg_ssc: number;
    avg_sbp: number;
    avg_mpj: number;
  };
  top_vtps: {
    party_id: string;
    company_name: string;
    roles: string[];
    bmu_count: number;
    net_qcv_mwh: number;
    pos_qcv_mwh: number;
    neg_qcv_mwh: number;
    comp_gbp: number;
    share_pct: number;
  }[];
  top_winners: {
    party_id: string;
    company_name: string;
    sccp_gbp: number;
    scvp_gbp: number;
    net_gbp: number;
  }[];
  top_payers: {
    party_id: string;
    company_name: string;
    sccp_gbp: number;
    scvp_gbp: number;
    net_gbp: number;
  }[];
  macro_timeline: {
    date: string;
    run_type: string;
    has_bmu_sp: boolean;
    net_sccp_gbp: number;
    pos_sccp_gbp: number;
    scvp_gbp: number;
    octopus_sccp_gbp: number;
    qcv_mwh: number;
    avg_sbp: number;
    avg_ssc: number;
  }[];
  milestones: { date: string; code: string; label: string }[];
}

export interface TimingResponse {
  start_date: string;
  end_date: string;
  sec_party_id: string | null;
  granular_days: number;
  max_cell_mwh: number;
  intraday: {
    sp: number;
    time: string;
    avg_pos_mwh: number;
    avg_neg_mwh: number;
    avg_net_mwh: number;
    avg_comp_gbp: number;
    avg_weekday_mwh: number;
    avg_weekend_mwh: number;
    avg_sbp: number;
    avg_mpj: number;
    avg_ssc: number;
    is_ev_offpeak: boolean;
  }[];
  heatmap: {
    date: string;
    dow: string;
    is_weekend: boolean;
    total_qcv_mwh: number;
    total_comp_gbp: number;
    avg_sbp: number;
    cells: { sp: number; qcv_mwh: number; comp_gbp: number; sbp: number }[];
  }[];
  vtp_profiles: {
    party_id: string;
    company_name: string;
    avg_sp_mwh: number[];
  }[];
  dow_matrix: {
    dow: string;
    days: number;
    avg_sp_mwh: number[];
    avg_daily_mwh: number;
  }[];
  vtp_choices: { party_id: string; company_name: string }[];
}

export interface CompensationResponse {
  start_date: string;
  end_date: string;
  filters: { sec_party_id: string | null; pri_party_id: string | null };
  totals: {
    total_pos_sccp_gbp: number;
    total_scvp_gbp: number;
    total_vtp_comp_gbp: number;
  };
  suppliers: {
    party_id: string;
    company_name: string;
    roles: string[];
    sccp_gbp: number;
    scvp_gbp: number;
    net_transfer_gbp: number;
    bmu_attributed_comp_gbp: number;
    bmu_qcv_mwh: number;
    reconciliation_diff_gbp: number;
    demand_share_pct: number;
    comp_share_pct: number;
    over_index_ratio: number;
  }[];
  vtps: {
    party_id: string;
    company_name: string;
    roles: string[];
    bmu_count: number;
    supplier_count: number;
    qcv_mwh: number;
    pos_qcv_mwh: number;
    neg_qcv_mwh: number;
    qsd_mwh: number;
    comp_gbp: number;
    share_pct: number;
  }[];
  flows: {
    sec_party_id: string;
    sec_company_name: string;
    pri_party_id: string;
    pri_company_name: string;
    qcv_mwh: number;
    comp_gbp: number;
    bmu_pair_count: number;
    share_of_vtp_pct: number;
  }[];
  bm_only_vlp_activity: {
    sec_party_id: string;
    sec_company_name: string;
    pri_party_id: string;
    pri_company_name: string;
    qsd_mwh: number;
    bmu_count: number;
  }[];
}

export interface ForensicVtp {
  party_id: string;
  company_name: string;
  roles: string[];
  is_amvlp: boolean;
  bmu_count: number;
  pos_qcv_mwh: number;
  neg_qcv_mwh: number;
  net_qcv_mwh: number;
  comp_gbp: number;
  market_share_pct: number;
  ev_focus_score: number;
  baselining_risk_score: number;
  archetype: string;
  evidence: string[];
  tariff_analysis: {
    peak_tariff_share_pct: number;
    offpeak_tariff_share_pct: number;
    weekday_midday_share_pct: number;
    eflh_hours_per_day: number;
    estimated_vtp_revenue_gbp: number;
    peak_tariff_revenue_gbp: number;
    below_ssc_mpj_qcv_mwh: number;
    below_ssc_vtp_revenue_gbp: number;
    deadweight_subsidy_gbp: number;
    has_tariff_clock_fingerprint: boolean;
    clock_steps: {
      bg_0500_pct: number;
      oct_0500_pct: number;
      oct_0530_pct: number;
      eon_0530_pct: number;
      eon_0600_pct: number;
      edf_2300_pct: number;
      oct_2330_pct: number;
      eon_2330_pct: number;
      eon_0000_pct: number;
      edf_2300_drop_gap: number;
    };
    boundary_curves: {
      sp: number;
      time: string;
      MERCURY: number;
      NITTWO01: number;
      BRITGAS: number;
      LENCO: number;
    }[];
  };
  signals: {
    ev_affinity_score: number;
    ev_supplier_share_pct: number;
    octopus_share_pct: number;
    ev_lift: number;
    octopus_lift: number;
    domestic_footprint_score: number;
    gsp_count: number;
    gsp_entropy: number;
    base_bmu_share_pct: number;
    conservation_score: number;
    one_sided_ratio_pct: number;
    low_price_farming_score: number;
    pct_below_ssc: number;
    pct_below_60: number;
    pct_negative_sbp: number;
    sp_price_corr: number | null;
    daily_price_corr: number | null;
    duty_cycle_score: number;
    active_hours_per_day: number;
    day_to_night_ratio: number;
    pre_event_turnup_flag: boolean;
    persistence_score: number;
    active_days: number;
    total_days: number;
    daily_cov: number;
  };
  top_suppliers: {
    party_id: string;
    company_name: string;
    qcv_mwh: number;
    comp_gbp: number;
    share_pct: number;
    is_ev_supplier: boolean;
  }[];
  sp_profile: {
    sp: number;
    time: string;
    avg_pos_mwh: number;
    avg_neg_mwh: number;
    avg_weekday_mwh: number;
    avg_weekend_mwh: number;
  }[];
  daily_series: {
    date: string;
    dow: string;
    pos_qcv_mwh: number;
    neg_qcv_mwh: number;
    net_qcv_mwh: number;
    comp_gbp: number;
    avg_sbp: number;
    min_sbp: number;
    avg_mpj: number;
    avg_ssc: number;
  }[];
  gsp_breakdown: {
    gsp_group: string;
    gsp_name: string;
    abs_qcv_mwh: number;
    share_pct: number;
  }[];
  sub_bmus: {
    suffix: string;
    total_qcv_mwh: number;
    active_days: number;
  }[];
}

export interface ForensicsResponse {
  start_date: string;
  end_date: string;
  granular_days: number;
  benchmarks: {
    gb_ev_supplier_demand_share_pct: number;
    gb_octopus_demand_share_pct: number;
    ev_tariff_suppliers: string[];
  };
  market_verdict: {
    total_comp_gbp: number;
    ev_focused_comp_gbp: number;
    ev_focused_share_pct: number;
    ev_baselining_high_risk_gbp: number;
    ev_baselining_high_risk_share_pct: number;
    total_estimated_vtp_revenue_gbp: number;
    total_peak_tariff_revenue_gbp: number;
    total_below_ssc_vtp_revenue_gbp: number;
    total_deadweight_subsidy_gbp: number;
    headline: string;
  };
  vtps: ForensicVtp[];
}

export interface ExplorerResponse {
  group_by: 'bmu_pair' | 'raw';
  total: number;
  limit: number;
  offset: number;
  items: Record<string, string | number>[];
}

export interface PartiesResponse {
  total: number;
  role_descriptions: Record<string, string>;
  items: {
    party_id: string;
    company_name: string;
    address: string;
    roles: string[];
    is_vtp: boolean;
    is_vlp: boolean;
    is_amvlp: boolean;
    is_supplier: boolean;
    bmu_count: number;
    vtp_comp_gbp: number;
    source: string;
  }[];
}
