// Display-only number formatting. Never use for payment math or for values sent to API / copied to clipboard.
// Thousands separator — non-breaking space (U+00A0): 97 000 000.
export const NBSP = '\u00A0';

const groupInt = (s) => s.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);

const groupFixed = (fixed, dec) => {
	const neg = fixed.startsWith('-');
	const [i, f] = (neg ? fixed.slice(1) : fixed).split('.');
	return (neg ? '-' : '') + groupInt(i) + (f !== undefined ? dec + f : '');
};

// Generic number: up to `max` fraction digits (trailing zeros trimmed), `min` forced.
// null / undefined / '' / NaN → '' (so `fmtNum(x) || '—'` fallbacks keep working).
export const fmtNum = (v, { min = 0, max = 2, dec = ',' } = {}) => {
	if (v === null || v === undefined || v === '') return '';
	const n = Number(v);
	if (!Number.isFinite(n)) return '';
	let s = (Math.round((Math.abs(n) + Number.EPSILON) * 10 ** max) / 10 ** max).toFixed(max);
	if (max > min) s = s.replace(new RegExp(`0{1,${max - min}}$`), '').replace(/\.$/, '');
	return groupFixed((n < 0 && Number(s) !== 0 ? '-' : '') + s, dec);
};

// USDT amount: always 2 decimals (half-up), dot as decimal separator — as before, now with grouping.
export const fmtUsdt = (v) => {
	const n = Number(v);
	if (v === null || v === undefined || Number.isNaN(n)) return '—';
	return groupFixed((Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2), '.');
};

// Shared price limit for all price inputs (mirrors backend MAX_PRICE_USDT).
export const MAX_PRICE_USDT = 10_000_000;
export const MAX_PRICE_HINT = `Максимальна ціна — ${groupInt(String(MAX_PRICE_USDT))} USDT`;

// Приватна угода /escrow: власний ліміт бекенда (backend/app/services/external_escrow.py MAX_PRICE_USDT = 1 000 000).
export const ESCROW_MAX_PRICE_USDT = 1_000_000;
export const ESCROW_MAX_PRICE_HINT = `Максимальна ціна — ${groupInt(String(ESCROW_MAX_PRICE_USDT))} USDT`;

// Сира сума для інструкцій оплати: 2 знаки, БЕЗ роздільників — безпечно копіювати у гаманець.
export const rawUsdt = (v) => {
	const n = Number(v);
	if (v === null || v === undefined || Number.isNaN(n)) return '—';
	return (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2);
};
