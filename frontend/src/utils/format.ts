export function fmtGbp(val: number, compact = false): string {
  if (compact) {
    const abs = Math.abs(val);
    const sign = val < 0 ? '-' : '';
    if (abs >= 1_000_000) return `${sign}£${(abs / 1_000_000).toFixed(2)}m`;
    if (abs >= 1_000) return `${sign}£${(abs / 1_000).toFixed(1)}k`;
    return `${sign}£${abs.toFixed(0)}`;
  }
  const sign = val < 0 ? '-' : '';
  return `${sign}£${Math.abs(val).toLocaleString('en-GB', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  })}`;
}

export function fmtGbpExact(val: number): string {
  const sign = val < 0 ? '-' : '';
  return `${sign}£${Math.abs(val).toLocaleString('en-GB', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function fmtMwh(val: number, decimals = 1): string {
  return `${val.toLocaleString('en-GB', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })} MWh`;
}

export function fmtSignedGbp(val: number, compact = false): string {
  const prefix = val > 0 ? '+' : '';
  return `${prefix}${fmtGbp(val, compact)}`;
}

export function spToTime(sp: number): string {
  const hh = Math.floor((sp - 1) / 2) % 24;
  const mm = (sp - 1) % 2 === 0 ? '00' : '30';
  return `${String(hh).padStart(2, '0')}:${mm}`;
}

export function shortDate(iso: string): string {
  if (!iso) return '';
  const [, m, d] = iso.split('-');
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return `${Number(d)} ${months[Number(m) - 1] ?? m}`;
}

export function riskTone(score: number): 'high' | 'mid' | 'low' {
  if (score >= 65) return 'high';
  if (score >= 45) return 'mid';
  return 'low';
}
