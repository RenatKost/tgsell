/** Honest TgSell lot-view labels. Numbers are raw counts; 0 is shown as 0. */

export function formatCount(n) {
	if (n === null || n === undefined || n === '') return '0';
	const v = Number(n);
	if (!Number.isFinite(v)) return '0';
	return String(Math.trunc(v));
}

/** @returns {string | null} Ukrainian label, or null when the API omitted the counts. */
export function siteViewsLabel(views7d, viewsTotal) {
	if (views7d == null && viewsTotal == null) return null;
	const n7 = views7d == null ? 0 : Number(views7d);
	const safe7 = Number.isFinite(n7) ? Math.trunc(n7) : 0;
	let text = `Переглядів лота на TgSell: ${formatCount(safe7)} за 7 днів`;
	if (viewsTotal != null) {
		const tot = Number(viewsTotal);
		const safeTot = Number.isFinite(tot) ? Math.trunc(tot) : 0;
		text += ` · усього ${formatCount(safeTot)}`;
	}
	return text;
}
