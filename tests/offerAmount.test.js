import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { offerBounds, validateOfferAmount } from '../src/utils/offerAmount.js';
import { OFFER_PENDING_KEY, savePendingOffer, peekPendingOffer, clearPendingOffer } from '../src/utils/offerIntent.js';

if (typeof globalThis.localStorage === 'undefined') {
	const store = new Map();
	globalThis.localStorage = {
		getItem: (k) => (store.has(k) ? store.get(k) : null),
		setItem: (k, v) => { store.set(String(k), String(v)); },
		removeItem: (k) => { store.delete(k); },
		clear: () => { store.clear(); },
	};
}

describe('offerAmount', () => {
	it('requires an amount strictly below the lot price and at least 50%', () => {
		assert.deepEqual(offerBounds(100), { min: 50, max: 99.99, price: 100 });
		assert.equal(validateOfferAmount(100, 100), 'Пропозиція має бути нижчою за ціну лота');
		assert.equal(validateOfferAmount(49.99, 100), 'Пропозиція має бути не нижчою за 50% ціни лота');
		assert.equal(validateOfferAmount(50, 100), null);
		assert.equal(validateOfferAmount(30, 100), 'Пропозиція має бути не нижчою за 50% ціни лота');
		assert.equal(validateOfferAmount(99.99, 100), null);
	});

	it('rejects junk', () => {
		assert.ok(validateOfferAmount('', 100));
		assert.ok(validateOfferAmount(0, 100));
	});
});

describe('offerIntent', () => {
	beforeEach(() => localStorage.clear());

	it('stores and expires a pending offer intent', () => {
		assert.equal(savePendingOffer(7, { needLogin: true }), true);
		assert.deepEqual(peekPendingOffer(), { channelId: 7, needLogin: true });
		clearPendingOffer();
		assert.equal(peekPendingOffer(), null);
		localStorage.setItem(OFFER_PENDING_KEY, JSON.stringify({ channelId: 3, at: Date.now() - 25 * 60 * 60 * 1000 }));
		assert.equal(peekPendingOffer(), null);
	});
});
