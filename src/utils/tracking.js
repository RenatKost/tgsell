// Task 23: first-party activity tracking. No IP / UA / search text sent.
import { trackingAPI } from '../services/api';

const ANON_KEY = 'tg_anon_id';
const SID_KEY = 'tg_sid';
const SID_TS_KEY = 'tg_sid_ts';
const SESSION_IDLE_MS = 30 * 60 * 1000;
export const HEARTBEAT_MS = 45 * 1000;

const rid = () => (crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

export const anonId = () => {
	try {
		let v = localStorage.getItem(ANON_KEY);
		if (!v) { v = rid(); localStorage.setItem(ANON_KEY, v); }
		return v;
	} catch { return null; }
};

// One session per tab; a new one after 30 min of no visible activity.
export const sessionId = () => {
	try {
		const now = Date.now();
		let v = sessionStorage.getItem(SID_KEY);
		const ts = Number(sessionStorage.getItem(SID_TS_KEY) || 0);
		if (!v || now - ts > SESSION_IDLE_MS) { v = rid(); sessionStorage.setItem(SID_KEY, v); }
		sessionStorage.setItem(SID_TS_KEY, String(now));
		return v;
	} catch { return null; }
};

export const pageFromPath = (path) => {
	const p = (path || '/').split('/')[1] || '';
	const map = { '': 'home', catalog: 'catalog', channel: 'channel', auction: 'auction', cabinet: 'cabinet', sell: 'sell', 'sell-bundle': 'sell', deal: 'deal', bundle: 'bundle', faq: 'faq' };
	return map[p] || 'other';
};

export const trackEvent = (type, extra = {}) => {
	trackingAPI.event({ type, anon: anonId(), ...extra }).catch(() => {});
};

export const sendHeartbeat = () => {
	if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
	const sid = sessionId();
	if (!sid) return;
	trackingAPI.heartbeat({ sid, anon: anonId() }).catch(() => {});
};
