// Джерело: /workspace/market/tumobog_summary.md (те саме, що backend/app/data/market_prices.json).
// Публічні оголошення про продаж (ціни запиту, не закриті угоди), 15.07–15.10.2026,
// 158 унікальних лотів; ціна за підписника розрахована для 152 з них.
export const MARKET = {
	period: '15.07–15.10.2026',
	listings: 158,
	nPerSub: 152,
	medianPerSub: 0.096, // усі лоти, n=152
	lowPerSub: 0.095, // медіана для мереж (сіток) каналів, n=65
	highPerSub: 0.115, // медіана для окремих каналів, n=82
	nNetwork: 65,
	nChannel: 82,
	uahRate: 41.5, // курс, за яким гривневі ціни перераховано в USD у джерелі
};

export const estimate = (subs) => ({
	median: subs * MARKET.medianPerSub,
	low: subs * MARKET.lowPerSub,
	high: subs * MARKET.highPerSub,
});

export const usd = (v) => '$' + Math.round(v).toLocaleString('uk-UA');
