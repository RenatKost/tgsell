/** Persist a guest's intent to open the price-offer modal after Telegram login. */

export const OFFER_PENDING_KEY = 'tgsell_pending_offer';
export const OFFER_PENDING_TTL_MS = 24 * 60 * 60 * 1000;

export function savePendingOffer(channelId, { needLogin } = {}) {
	const id = Number(channelId);
	if (!(id > 0)) return false;
	try {
		localStorage.setItem(OFFER_PENDING_KEY, JSON.stringify({
			channelId: id,
			at: Date.now(),
			needLogin: !!needLogin,
		}));
		return true;
	} catch {
		return false;
	}
}

/** @returns {{ channelId: number, needLogin: boolean } | null} */
export function peekPendingOffer() {
	try {
		const raw = localStorage.getItem(OFFER_PENDING_KEY);
		if (!raw) return null;
		const v = JSON.parse(raw);
		const id = Number(v?.channelId);
		if (!(id > 0) || Date.now() - Number(v.at || 0) > OFFER_PENDING_TTL_MS) {
			localStorage.removeItem(OFFER_PENDING_KEY);
			return null;
		}
		return { channelId: id, needLogin: !!v.needLogin };
	} catch {
		return null;
	}
}

export function clearPendingOffer() {
	try { localStorage.removeItem(OFFER_PENDING_KEY); } catch { /* ignore */ }
}

export function markPendingOfferLoggedIn() {
	const pending = peekPendingOffer();
	if (!pending) return;
	savePendingOffer(pending.channelId, { needLogin: false });
}
