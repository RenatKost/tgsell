/** Display title for a deal in cabinets and on the deal page. Never renders «null». */

export function dealTitle(deal) {
	if (!deal || typeof deal !== 'object') return 'Угода';
	const name = String(deal.channel_name || '').trim();
	if (name) return name;
	const bundle = String(deal.bundle_name || '').trim();
	if (bundle) return bundle;
	if (deal.is_external) {
		const link = String(deal.channel_link || deal.external_channel_link || '').trim();
		return link || 'Зовнішня угода';
	}
	const channelId = Number(deal.channel_id);
	if (Number.isFinite(channelId) && channelId > 0) return `Канал #${channelId}`;
	const dealId = Number(deal.id);
	if (Number.isFinite(dealId) && dealId > 0) return `Угода #${dealId}`;
	return 'Угода';
}
