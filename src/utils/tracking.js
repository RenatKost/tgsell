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

// Attribution: utm_* from the landing URL + referer *domain* only (no full URL, no PII).
// Captured once per tab session and attached to visit events (server dedupes visits).
const ATTR_KEY = 'tg_attr';
const UTM_KEYS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];
export const getAttribution = () => {
	try {
		const saved = sessionStorage.getItem(ATTR_KEY);
		if (saved) return JSON.parse(saved);
		const attr = {};
		const qs = new URLSearchParams(window.location.search);
		UTM_KEYS.forEach((k) => { const v = qs.get(k); if (v) attr[k] = v.slice(0, 64); });
		if (document.referrer) {
			const host = new URL(document.referrer).hostname.replace(/^www\./, '');
			if (host && host !== window.location.hostname.replace(/^www\./, '')) attr.ref_domain = host.slice(0, 64);
		}
		sessionStorage.setItem(ATTR_KEY, JSON.stringify(attr));
		return attr;
	} catch { return {}; }
};

export const trackEvent = (type, extra = {}) => {
	const attr = type === 'visit' ? getAttribution() : {};
	trackingAPI.event({ type, anon: anonId(), ...attr, ...extra }).catch(() => {});
};

// Server treats heartbeats closer than HEARTBEAT_MIN_INTERVAL (20 s) per session as a
// no-op (200, throttled) and only answers 429 on real flooding (>12/min per session).
// Client never sends more often than every 30 s. On 429 it skips exactly one interval
// (no exponential growth): the gap to the next beat stays < HEARTBEAT_MAX_GAP (120 s),
// so the server still credits the time in between — activity is not lost.
const HEARTBEAT_MIN_GAP_MS = 30 * 1000;
let lastHeartbeatAt = 0;
let heartbeatBlockedUntil = 0;

export const sendHeartbeat = () => {
	if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
	const now = Date.now();
	if (now - lastHeartbeatAt < HEARTBEAT_MIN_GAP_MS || now < heartbeatBlockedUntil) return;
	const sid = sessionId();
	if (!sid) return;
	lastHeartbeatAt = now;
	trackingAPI.heartbeat({ sid, anon: anonId() })
		.catch((err) => {
			if (err?.response?.status === 429) {
				heartbeatBlockedUntil = Date.now() + HEARTBEAT_MS;
			}
		});
};
