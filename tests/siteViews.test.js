import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { formatCount, siteViewsLabel } from '../src/utils/siteViews.js';

describe('siteViewsLabel', () => {
	it('returns null when the API omitted the counts', () => {
		assert.equal(siteViewsLabel(undefined, undefined), null);
		assert.equal(siteViewsLabel(null, null), null);
	});

	it('shows 0 as 0, not a dash or a multiplier', () => {
		assert.equal(siteViewsLabel(0, 0), 'Переглядів лота на TgSell: 0 за 7 днів · усього 0');
		assert.equal(formatCount(0), '0');
	});

	it('includes the 7-day window and the all-time total when both are present', () => {
		assert.equal(
			siteViewsLabel(12, 40),
			'Переглядів лота на TgSell: 12 за 7 днів · усього 40',
		);
	});

	it('omits the total when only the 7-day count is provided', () => {
		assert.equal(siteViewsLabel(3, null), 'Переглядів лота на TgSell: 3 за 7 днів');
	});
});
