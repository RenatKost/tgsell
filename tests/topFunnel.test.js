import test from 'node:test';
import assert from 'node:assert/strict';
import {
	topOfferFromCatalog, topButtonLabel, slotsLine, findOpenOrder, openInvoices,
	parseCabinetTopParam, formatKyivDateTime, inTopUntilLabel, formatCountdown,
} from '../src/utils/topFunnel.js';

const cat = {
	items: [{ kind: 'top', price_usdt: 10, terms: '…7 днів…' }, { kind: 'post', price_usdt: 15 }],
	top_slots_free: 3,
	top_slots_max: 3,
	top_days: 7,
};

test('button label and slots line come from catalog, not hardcoded fallbacks when offer is complete', () => {
	const offer = topOfferFromCatalog(cat);
	assert.deepEqual(offer, { price: 10, days: 7, slotsMax: 3, slotsFree: 3, terms: '…7 днів…' });
	assert.equal(topButtonLabel(offer), 'Підняти в Топ — 10 USDT / 7 днів');
	assert.equal(slotsLine(offer), 'Вільно 3 з 3 місць у Топі');
	assert.equal(slotsLine({ ...offer, slotsFree: 0 }), 'Усі місця зайняті');
	assert.equal(slotsLine({ ...offer, slotsFree: 1 }), 'Вільно 1 з 3 місць у Топі');
	// price/days change with catalog
	const other = topOfferFromCatalog({ ...cat, top_days: 14, items: [{ kind: 'top', price_usdt: 12.5, terms: '' }], top_slots_free: 2, top_slots_max: 5 });
	assert.equal(topButtonLabel(other), 'Підняти в Топ — 12.5 USDT / 14 днів');
	assert.equal(slotsLine(other), 'Вільно 2 з 5 місць у Топі');
});

test('findOpenOrder returns the existing awaiting invoice for the same lot, ignores other kinds/channels', () => {
	const orders = [
		{ id: 1, channel_id: 10, kind: 'post', status: 'awaiting_payment', escrow_wallet_address: 'T1' },
		{ id: 2, channel_id: 10, kind: 'top', status: 'awaiting_payment', escrow_wallet_address: 'T2' },
		{ id: 3, channel_id: 11, kind: 'top', status: 'awaiting_payment', escrow_wallet_address: 'T3' },
		{ id: 4, channel_id: 10, kind: 'top', status: 'active', escrow_wallet_address: 'T4' },
	];
	assert.equal(findOpenOrder(orders, 10, 'top').escrow_wallet_address, 'T2');
	assert.equal(findOpenOrder(orders, '10', 'top').id, 2);
	assert.equal(findOpenOrder(orders, 11, 'top').id, 3);
	assert.equal(findOpenOrder(orders, 10, 'post').id, 1);
	assert.equal(findOpenOrder(orders, 99, 'top'), null);
	assert.deepEqual(openInvoices(orders).map((o) => o.id), [1, 2, 3]);
});

test('parseCabinetTopParam reads /cabinet?top=<id> and rejects junk', () => {
	assert.equal(parseCabinetTopParam('?top=42'), 42);
	assert.equal(parseCabinetTopParam('top=42&x=1'), 42);
	assert.equal(parseCabinetTopParam('?tab=my&top=7'), 7);
	assert.equal(parseCabinetTopParam('?top=0'), null);
	assert.equal(parseCabinetTopParam('?top=abc'), null);
	assert.equal(parseCabinetTopParam(''), null);
	assert.equal(parseCabinetTopParam('?foo=1'), null);
});

test('Kyiv datetime label and countdown', () => {
	// 2026-11-18 14:35 UTC = 16:35 Europe/Kyiv (UTC+2 in November)
	const label = formatKyivDateTime('2026-11-18T14:35:00.000Z');
	assert.match(label, /18\.11\.2026/);
	assert.match(label, /16:35/);
	assert.equal(inTopUntilLabel('2026-11-18T14:35:00.000Z'), `У Топі до ${label}`);
	assert.equal(inTopUntilLabel(null), 'У Топі');

	const now = Date.parse('2026-11-11T12:00:00.000Z');
	assert.equal(formatCountdown('2026-11-11T14:30:00.000Z', now), 'Залишилось 2 год 30 хв');
	assert.equal(formatCountdown('2026-11-11T12:10:00.000Z', now), 'Залишилось 10 хв');
	assert.equal(formatCountdown('2026-11-11T11:00:00.000Z', now), 'Строк оплати минув');
	assert.equal(formatCountdown('2026-11-13T12:00:00.000Z', now), 'Залишилось 2 д 0 год');
	assert.equal(formatCountdown('2026-11-11T11:00:00.000Z', now, 'Час підтвердження минув'), 'Час підтвердження минув');
});
