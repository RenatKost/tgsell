/** Persist a guest's intent to buy a specific lot across Telegram login (like the sell-form draft). */

export const BUY_PENDING_KEY = 'tgsell_pending_buy';
export const BUY_PENDING_TTL_MS = 24 * 60 * 60 * 1000;

export function savePendingBuy(channelId, { needLogin } = {}) {
	const id = Number(channelId);
	if (!(id > 0)) return false;
	try {
		localStorage.setItem(BUY_PENDING_KEY, JSON.stringify({
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
export function peekPendingBuy() {
	try {
		const raw = localStorage.getItem(BUY_PENDING_KEY);
		if (!raw) return null;
		const v = JSON.parse(raw);
		const id = Number(v?.channelId);
		if (!(id > 0) || Date.now() - Number(v.at || 0) > BUY_PENDING_TTL_MS) {
			localStorage.removeItem(BUY_PENDING_KEY);
			return null;
		}
		return { channelId: id, needLogin: !!v.needLogin };
	} catch {
		return null;
	}
}

export function clearPendingBuy() {
	try { localStorage.removeItem(BUY_PENDING_KEY); } catch { /* ignore */ }
}

/** True when a stored intent matches this lot (still within TTL). */
export function hasPendingBuy(channelId) {
	const pending = peekPendingBuy();
	const id = Number(channelId);
	return pending != null && id > 0 && pending.channelId === id;
}

/** After a successful login from the buy flow, stop treating the intent as 'needs login'. */
export function markPendingBuyLoggedIn() {
	const pending = peekPendingBuy();
	if (!pending) return;
	savePendingBuy(pending.channelId, { needLogin: false });
}
