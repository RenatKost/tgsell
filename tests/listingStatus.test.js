import test from 'node:test';
import assert from 'node:assert/strict';
import { LISTING_STATUS } from '../src/utils/listingStatus.js';

test('needs_clarification has a dedicated Ukrainian label and does not fall back to pending', () => {
	assert.equal(LISTING_STATUS.needs_clarification.text, 'Очікує уточнення');
	assert.equal(LISTING_STATUS.needs_clarification.tone, 'orange');
	assert.notEqual(LISTING_STATUS.needs_clarification.text, LISTING_STATUS.pending.text);
});

test('all known channel statuses have a label', () => {
	for (const s of ['pending', 'needs_clarification', 'approved', 'rejected', 'sold', 'removed']) {
		assert.ok(LISTING_STATUS[s], `missing LISTING_STATUS.${s}`);
		assert.ok(LISTING_STATUS[s].text);
	}
});
