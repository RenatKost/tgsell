// Task 28: ER for tiny / new channels can be absurd (2200%, 654%).
// Keep in sync with backend/app/utils/er.py.
export const ER_MAX_PLAUSIBLE = 100;
export const ER_MIN_SUBSCRIBERS = 50;
export const ER_NO_DATA = 'мало даних';

export const reliableEr = (er, subscribers) => {
	if (er == null || er === '') return null;
	const n = Number(er);
	if (!Number.isFinite(n) || n < 0 || n > ER_MAX_PLAUSIBLE) return null;
	if (subscribers != null && Number(subscribers) < ER_MIN_SUBSCRIBERS) return null;
	return n;
};

// '—' when ER is unknown, 'мало даних' when it is implausible, otherwise '12.3%'.
export const formatEr = (er, subscribers, digits = 1) => {
	if (er == null || er === '') return '—';
	const n = reliableEr(er, subscribers);
	return n == null ? ER_NO_DATA : `${n.toFixed(digits)}%`;
};
