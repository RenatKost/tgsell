// Джерело: backend/app/data/market_prices.json (внутрішні дані, не показувати на сайті).
// Тут лише коефіцієнти $/підписник; кількості, джерела та дати не потрапляють у бандл.
export const MARKET = {
	medianPerSub: 0.096,
	lowPerSub: 0.095,
	highPerSub: 0.115,
};

export const estimate = (subs) => ({
	median: subs * MARKET.medianPerSub,
	low: subs * MARKET.lowPerSub,
	high: subs * MARKET.highPerSub,
});

export const usd = (v) => '$' + Math.round(v).toLocaleString('uk-UA');
