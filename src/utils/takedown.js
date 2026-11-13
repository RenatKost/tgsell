// Seller cabinet: why a lot is off the catalog (owner-only `takedown_reason` from the API).
const SUPPORT_HINT = 'Щоб повернути лот у каталог, усуньте причину й напишіть у підтримку @tgsell_support_bot — модератор перевірить і відновить публікацію.';

export function takedownInfo(channel) {
	if (!channel) return null;
	const reason = (channel.takedown_reason || channel.rejection_reason || '').trim();
	if (channel.status === 'rejected' && reason) {
		return { label: 'Причина відхилення', reason, hint: SUPPORT_HINT };
	}
	if (channel.status === 'removed' && reason) {
		// Removed by the seller themselves: no support hint needed.
		const bySeller = reason === 'Знято продавцем';
		return { label: 'Причина зняття', reason, hint: bySeller ? null : SUPPORT_HINT };
	}
	return null;
}
