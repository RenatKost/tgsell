// Which /sell entry to show. Pure (no imports) so it can be unit-tested with `node --test`.
// Ad campaigns that promote a single-channel listing open the «Один канал» form directly
// (the ad link itself never changes); ?type=single does the same for any link.
export const DIRECT_SINGLE_CAMPAIGNS = ['promo_top_image', 'promo_top7'];

/** search: location.search; storedCampaign: first-touch utm_campaign (may be null). */
export function wantsDirectSingle(search, storedCampaign = null) {
	const qs = new URLSearchParams(search || '');
	if ((qs.get('type') || '').trim().toLowerCase() === 'single') return true;
	const urlCampaign = (qs.get('utm_campaign') || '').trim().toLowerCase();
	return [urlCampaign, (storedCampaign || '').toLowerCase()].some((c) => c && DIRECT_SINGLE_CAMPAIGNS.includes(c));
}
