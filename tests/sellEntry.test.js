import test from 'node:test';
import assert from 'node:assert/strict';
import { wantsDirectSingle } from '../src/utils/sellEntry.js';

test('IG ad URL opens single form', () => {
	assert.equal(wantsDirectSingle('?utm_source=instagram&utm_medium=paid&utm_campaign=promo_top_image'), true);
	assert.equal(wantsDirectSingle('?utm_campaign=PROMO_TOP7'), true);
});
test('stored first-touch campaign opens single form', () => {
	assert.equal(wantsDirectSingle('', 'promo_top_image'), true);
	assert.equal(wantsDirectSingle('?x=1', 'promo_top7'), true);
});
test('?type=single opens single form', () => {
	assert.equal(wantsDirectSingle('?type=single'), true);
});
test('other visitors see the type chooser', () => {
	assert.equal(wantsDirectSingle(''), false);
	assert.equal(wantsDirectSingle('?utm_campaign=other', 'qa_funnel_check'), false);
	assert.equal(wantsDirectSingle('?type=bundle'), false);
	assert.equal(wantsDirectSingle(null, null), false);
});
