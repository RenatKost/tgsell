/** User-facing notice when /channel/:id?offer=:id cannot open the confirm step. */

export const OFFER_LINK_GENERIC = 'Пропозицію не знайдено або вона вже неактуальна';
export const OFFER_LINK_EXPIRED_48H = 'Термін на створення угоди минув (48 годин після прийняття пропозиції)';
export const OFFER_LINK_LOT_IN_DEAL = 'Лот уже в угоді — ця пропозиція закрита';
export const ACCEPT_DEAL_TTL_MS = 48 * 60 * 60 * 1000;

export function isAcceptanceWindowOpen(offer, now = Date.now()) {
	if (!offer || offer.status !== 'accepted' || offer.deal_id) return false;
	const raw = offer.accepted_at || offer.decided_at;
	const t = raw != null ? Date.parse(raw) : NaN;
	return Number.isFinite(t) && t + ACCEPT_DEAL_TTL_MS >= now;
}

/**
 * @returns {string|null} Ukrainian notice, or null when the page should keep current behaviour
 *   (open confirm if can_create_deal, otherwise stay silent — e.g. seller viewing a still-valid accepted offer).
 */
export function offerLinkNotice(offer, { channelId, error } = {}) {
	if (error || !offer) return OFFER_LINK_GENERIC;
	if (Number(offer.channel_id) !== Number(channelId)) return OFFER_LINK_GENERIC;
	if (offer.can_create_deal) return null;
	if (offer.status === 'closed' && offer.close_reason === 'lot_in_deal') {
		return OFFER_LINK_LOT_IN_DEAL;
	}
	if (offer.status === 'accepted' && !offer.deal_id) {
		return isAcceptanceWindowOpen(offer) ? null : OFFER_LINK_EXPIRED_48H;
	}
	return OFFER_LINK_GENERIC;
}
