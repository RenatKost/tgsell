/** Client-side bounds for a price offer. The server remains the source of truth. */

export const OFFER_MIN_FRACTION = 0.5;

export function offerBounds(lotPrice) {
	const price = Number(lotPrice);
	if (!(price > 0)) return null;
	const priceCents = Math.round(price * 100);
	const minCents = Math.ceil(priceCents * OFFER_MIN_FRACTION);
	const maxCents = priceCents - 1;
	if (minCents > maxCents) return null;
	return { min: minCents / 100, max: maxCents / 100, price: priceCents / 100 };
}

export function validateOfferAmount(amount, lotPrice) {
	const bounds = offerBounds(lotPrice);
	if (!bounds) return 'Для цього лота не можна запропонувати нижчу ціну';
	const n = Number(amount);
	if (!Number.isFinite(n) || n <= 0) return 'Вкажіть суму в USDT';
	const cents = Math.round(n * 100);
	if (Math.abs(n * 100 - cents) > 1e-6) return 'Сума має бути з точністю до 0,01 USDT';
	if (cents > Math.round(bounds.max * 100)) return 'Пропозиція має бути нижчою за ціну лота';
	if (cents < Math.round(bounds.min * 100)) return 'Пропозиція має бути не нижчою за 50% ціни лота';
	return null;
}
