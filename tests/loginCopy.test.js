import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { loginModalCopy } from '../src/utils/loginCopy.js';

describe('loginModalCopy', () => {
	it('uses offer-specific wording', () => {
		const c = loginModalCopy('offer');
		assert.equal(c.title, 'Увійдіть, щоб запропонувати ціну');
		assert.match(c.subtitle, /свою ціну/);
		assert.doesNotMatch(c.title, /купити канал/);
	});

	it('keeps the buy wording by default', () => {
		const c = loginModalCopy('buy');
		assert.equal(c.title, 'Увійдіть, щоб купити канал');
		assert.match(c.subtitle, /ескроу/);
	});
});
