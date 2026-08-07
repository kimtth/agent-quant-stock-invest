export function formatPrice(value) {
  if (!Number.isFinite(value) || value === 0) return '$0.00';
  if (value >= 1000) {
    return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (value >= 1) return `$${value.toFixed(2)}`;
  return `$${value.toFixed(4)}`;
}

export function formatChange(value) {
  if (!Number.isFinite(value)) return '+0.00%';
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

/** Shorter price form used when the watchlist column is too narrow. */
export function formatPriceCompact(value) {
  if (!Number.isFinite(value) || value === 0) return '$0.00';
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(1)}K`;
  if (value >= 100) return `$${value.toFixed(1)}`;
  if (value >= 1) return `$${value.toFixed(2)}`;
  return `$${value.toFixed(3)}`;
}

export function formatCompact(value) {
  if (!Number.isFinite(value) || value === 0) return 'N/A';
  if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return value.toLocaleString('en-US');
}

export function formatNumber(value, digits = 2) {
  return Number.isFinite(value) ? value.toFixed(digits) : 'N/A';
}

export function formatClock(date = new Date()) {
  return date.toLocaleTimeString('en-US', { hour12: false });
}

export function axisLabels(timestamps, count, days) {
  const labels = [];
  const step = Math.max(1, Math.floor(count / Math.min(8, count)));
  for (let i = 0; i < count; i++) {
    const isTick = i === 0 || i === count - 1 || i % step === 0;
    if (!isTick || !Number.isFinite(timestamps?.[i])) {
      labels.push(isTick ? String(i + 1) : ' ');
      continue;
    }
    const date = new Date(timestamps[i]);
    if (days <= 1) {
      labels.push(
        `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
      );
    } else {
      labels.push(
        `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')}`
      );
    }
  }
  return labels;
}
