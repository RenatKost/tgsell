import { fmtNum } from './money';
export const LANGUAGE_LABELS = { ua: 'Україна', ru: 'RU', en: 'EN', other: 'Інше' };

const n = (v) => fmtNum(Number(v));

export const fmtRange = (lo, hi, unit = '') => {
	const has = (v) => v !== null && v !== undefined && v !== '';
	let s;
	if (has(lo) && has(hi)) s = `${n(lo)}–${n(hi)}`;
	else if (has(hi)) s = `до ${n(hi)}`;
	else if (has(lo)) s = `від ${n(lo)}`;
	else return 'будь-яка';
	return unit ? `${s} ${unit}` : s;
};

export const fmtDate = (iso) => (iso ? new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).toLocaleDateString('uk-UA') : '—');
