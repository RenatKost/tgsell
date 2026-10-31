// UTM first-touch attribution: utm_source / utm_campaign / utm_content from the landing URL are kept
// (localStorage + cookie, 30 days, first touch wins) and sent with registration and lot submission.
// Every landing that carries utm_* also sends one anonymous visit beacon (no PII).
import { trackingAPI } from '../services/api';
import { anonId } from './tracking';

const KEY = 'tgsell_utm';
const TTL_MS = 30 * 24 * 3600 * 1000;
const FIELDS = ['utm_source', 'utm_campaign', 'utm_content'];
const clean = (v) => (v || '').trim().toLowerCase().replace(/[^0-9a-z_\-.~+%]/g, '').slice(0, 64);

export function readUtmFromSearch(search) {
	const qs = new URLSearchParams(search || '');
	const out = {};
	FIELDS.forEach((k) => { const v = clean(qs.get(k)); if (v) out[k] = v; });
	return out.utm_source || out.utm_campaign ? out : null;
}

export function getUtm() {
	try {
		const raw = localStorage.getItem(KEY);
		if (raw) {
			const v = JSON.parse(raw);
			if (v && Date.now() - (v.at || 0) < TTL_MS) return v;
			localStorage.removeItem(KEY);
		}
		const m = document.cookie.match(/(?:^|; )tgsell_utm=([^;]+)/);
		if (m) {
			const v = JSON.parse(decodeURIComponent(m[1]));
			if (v && (v.utm_source || v.utm_campaign)) return v;
		}
	} catch { /* storage unavailable */ }
	return null;
}

/** utm_* fields for API payloads (registration, lot, bundle). Empty object when none stored. */
export function utmPayload() {
	const v = getUtm();
	if (!v) return {};
	const out = {};
	FIELDS.forEach((k) => { if (v[k]) out[k] = v[k]; });
	return out;
}

export function captureUtm(loc = window.location) {
	try {
		const fresh = readUtmFromSearch(loc.search);
		if (!fresh) return;
		if (!getUtm()) {
			const v = { ...fresh, at: Date.now() };
			localStorage.setItem(KEY, JSON.stringify(v));
			document.cookie = `${KEY}=${encodeURIComponent(JSON.stringify(v))}; max-age=${TTL_MS / 1000}; path=/; samesite=lax`;
		}
		const dedupe = `tgsell_utm_sent:${loc.pathname}:${FIELDS.map((k) => fresh[k] || '').join('|')}`;
		if (sessionStorage.getItem(dedupe)) return;
		sessionStorage.setItem(dedupe, '1');
		trackingAPI.utm({ anon: anonId(), path: loc.pathname, ...fresh }).catch(() => {});
	} catch { /* noop */ }
}

/** Funnel step of a UTM visitor (login_click / form_start / form_submit_attempt): once per tab session
 *  per step (dedupe keyed by step only, so an auto-open and a later click never double-count),
 *  only for visitors that came from a campaign. Never throws. */
export function trackFunnel(event, extra = {}) {
	try {
		const utm = utmPayload();
		if (!utm.utm_source && !utm.utm_campaign) return;
		const k = `tgsell_funnel_sent:${event}`;
		if (sessionStorage.getItem(k)) return;
		sessionStorage.setItem(k, '1');
		const body = { anon: anonId(), event, ...utm };
		if (extra && Object.keys(extra).length) { body.meta = { ...extra }; if (extra.auto === true) body.auto = true; }
		Promise.resolve(trackingAPI.funnel(body)).catch(() => {});
	} catch { /* noop */ }
}

export const isPromoTop7 = () => getUtm()?.utm_campaign === 'promo_top7';
