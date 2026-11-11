import { parseUtc } from './datetime.js';

const KYIV = 'Europe/Kyiv';

export const OPEN_INVOICE_STATUSES = ['awaiting_payment'];

export function topOfferFromCatalog(cat) {
	if (!cat) return null;
	const item = (cat.items || []).find((i) => i.kind === 'top');
	if (!item) return null;
	const price = Number(item.price_usdt);
	const days = Number(cat.top_days);
	const slotsMax = Number(cat.top_slots_max);
	const slotsFree = Number(cat.top_slots_free);
	return {
		price: Number.isFinite(price) ? price : null,
		days: Number.isFinite(days) && days > 0 ? days : null,
		slotsMax: Number.isFinite(slotsMax) && slotsMax > 0 ? slotsMax : null,
		slotsFree: Number.isFinite(slotsFree) && slotsFree >= 0 ? slotsFree : null,
		terms: item.terms || '',
	};
}

export function topButtonLabel(offer) {
	if (!offer || offer.price == null || offer.days == null) return 'Підняти в Топ';
	const price = Number.isInteger(offer.price) ? String(offer.price) : String(offer.price);
	return `Підняти в Топ — ${price} USDT / ${offer.days} днів`;
}

export function slotsLine(offer) {
	if (!offer) return '';
	if (offer.slotsFree === 0) return 'Усі місця зайняті';
	if (offer.slotsFree != null && offer.slotsMax != null) {
		return `Вільно ${offer.slotsFree} з ${offer.slotsMax} місць у Топі`;
	}
	if (offer.slotsFree != null) return `Вільно ${offer.slotsFree} місць у Топі`;
	return '';
}

export function findOpenOrder(orders, channelId, kind = 'top') {
	const cid = Number(channelId);
	if (!Number.isFinite(cid) || !Array.isArray(orders)) return null;
	return orders.find((o) => Number(o.channel_id) === cid
		&& o.kind === kind
		&& OPEN_INVOICE_STATUSES.includes(o.status)) || null;
}

export function openInvoices(orders) {
	if (!Array.isArray(orders)) return [];
	return orders.filter((o) => OPEN_INVOICE_STATUSES.includes(o.status));
}

export function parseCabinetTopParam(search) {
	const qs = new URLSearchParams(typeof search === 'string' && search.startsWith('?') ? search.slice(1) : (search || ''));
	const raw = qs.get('top');
	const id = raw ? Number(raw) : NaN;
	return Number.isInteger(id) && id > 0 ? id : null;
}

export function formatKyivDateTime(value) {
	const d = parseUtc(value);
	if (!d || isNaN(d.getTime())) return '';
	return d.toLocaleString('uk-UA', {
		timeZone: KYIV,
		day: '2-digit',
		month: '2-digit',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
	});
}

export function inTopUntilLabel(topUntil) {
	const label = formatKyivDateTime(topUntil);
	return label ? `У Топі до ${label}` : 'У Топі';
}

export function formatCountdown(deadline, nowMs, expiredLabel) {
	const d = parseUtc(deadline);
	if (!d || isNaN(d.getTime())) return '';
	const ms = d.getTime() - (nowMs ?? Date.now());
	if (ms <= 0) return expiredLabel || 'Строк оплати минув';
	const totalMin = Math.floor(ms / 60000);
	const hours = Math.floor(totalMin / 60);
	const minutes = totalMin % 60;
	if (hours >= 24) {
		const days = Math.floor(hours / 24);
		const remH = hours % 24;
		return `Залишилось ${days} д ${remH} год`;
	}
	if (hours > 0) return `Залишилось ${hours} год ${minutes} хв`;
	return `Залишилось ${minutes} хв`;
}

export function invoiceIsOpen(order) {
	return !!(order && OPEN_INVOICE_STATUSES.includes(order.status));
}
