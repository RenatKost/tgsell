import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { BUY_PENDING_KEY, savePendingBuy, peekPendingBuy, clearPendingBuy, hasPendingBuy, markPendingBuyLoggedIn } from '../src/utils/buyIntent.js';

if (typeof globalThis.localStorage === 'undefined') {
	const store = new Map();
	globalThis.localStorage = {
		getItem: (k) => (store.has(k) ? store.get(k) : null),
		setItem: (k, v) => { store.set(String(k), String(v)); },
		removeItem: (k) => { store.delete(k); },
		clear: () => { store.clear(); },
	};
}

describe('buyIntent', () => {
	beforeEach(() => {
		localStorage.clear();
	});

	it('stores a lot id and reads it back', () => {
		assert.equal(savePendingBuy(42), true);
		assert.deepEqual(peekPendingBuy(), { channelId: 42, needLogin: false });
		assert.equal(hasPendingBuy(42), true);
		assert.equal(hasPendingBuy(7), false);
	});

	it('remembers that login is still needed', () => {
		assert.equal(savePendingBuy(8, { needLogin: true }), true);
		assert.equal(peekPendingBuy().needLogin, true);
		markPendingBuyLoggedIn();
		assert.equal(peekPendingBuy().needLogin, false);
		assert.equal(hasPendingBuy(8), true);
	});

	it('rejects junk ids', () => {
		assert.equal(savePendingBuy('nope'), false);
		assert.equal(savePendingBuy(0), false);
		assert.equal(peekPendingBuy(), null);
	});

	it('clears the intent', () => {
		savePendingBuy(9);
		clearPendingBuy();
		assert.equal(peekPendingBuy(), null);
		assert.equal(hasPendingBuy(9), false);
	});

	it('expires a stale intent', () => {
		const stale = { channelId: 5, at: Date.now() - 25 * 60 * 60 * 1000, needLogin: true };
		localStorage.setItem(BUY_PENDING_KEY, JSON.stringify(stale));
		assert.equal(peekPendingBuy(), null);
	});
});
