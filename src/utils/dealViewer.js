// Who is looking at a deal page and which wording is honest for them.
// A staff member (admin/moderator) who is NOT the buyer or seller is an observer (guarantor):
// never show party wording like «Ви продаєте» or «Ви підтвердили» to them.

const sameId = (a, b) => a != null && b != null && String(a) === String(b);

export const isStaffRole = (role) => role === 'admin' || role === 'moderator';

export function dealViewer(user, deal) {
	const isBuyer = sameId(user?.id, deal?.buyer_id);
	const isSeller = !isBuyer && sameId(user?.id, deal?.seller_id);
	const isParty = isBuyer || isSeller;
	const isObserver = !isParty;
	const isStaffObserver = isObserver && isStaffRole(user?.role);
	return { isBuyer, isSeller, isParty, isObserver, isStaffObserver };
}

export function heroLabel(v) {
	if (v.isBuyer) return 'Ви купуєте';
	if (v.isSeller) return 'Ви продаєте';
	return v.isStaffObserver ? 'Гарант TgSell · ви не сторона угоди' : 'Перегляд угоди';
}

export function heroCounterpart(v, deal) {
	if (v.isBuyer) return deal.seller_name || 'Продавець';
	if (v.isSeller) return deal.buyer_name || 'Покупець';
	return `Продавець: ${deal.seller_name || '—'} · Покупець: ${deal.buyer_name || '—'}`;
}

const waitingText = (buyerDone, sellerDone, what) => {
	if (!buyerDone && !sellerDone) return `Очікуємо ${what} обох сторін`;
	if (!buyerDone) return `Очікуємо ${what} покупця`;
	if (!sellerDone) return `Очікуємо ${what} продавця`;
	return 'Обидві сторони підтвердили';
};

// Readiness step: 'confirm' = show the button; otherwise { banner } text.
export function readinessView(v, deal) {
	if ((v.isBuyer && !deal.buyer_ready) || (v.isSeller && !deal.seller_ready)) return { action: 'confirm' };
	if (v.isParty) return { action: null, banner: 'Ви підтвердили. Очікуйте іншу сторону' };
	return { action: null, banner: waitingText(!!deal.buyer_ready, !!deal.seller_ready, 'підтвердження готовності') };
}

export function transferView(v, deal) {
	if ((v.isBuyer && !deal.buyer_confirmed_transfer) || (v.isSeller && !deal.seller_confirmed_transfer)) return { action: 'confirm' };
	if (v.isParty) return { action: null, banner: 'Ви підтвердили. Очікуйте іншу сторону' };
	return { action: null, banner: waitingText(!!deal.buyer_confirmed_transfer, !!deal.seller_confirmed_transfer, 'підтвердження передачі від') };
}
