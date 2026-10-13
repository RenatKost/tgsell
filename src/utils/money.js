// Display-only USDT formatting: always 2 decimals (half-up). Never use for payment math.
export const fmtUsdt = (v) => {
	const n = Number(v);
	if (v === null || v === undefined || Number.isNaN(n)) return '—';
	return (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);
};
