import test from 'node:test';
import assert from 'node:assert/strict';
import { takedownInfo } from '../src/utils/takedown.js';

test('rejected lot shows the owner-only reason with the support hint', () => {
	const t = takedownInfo({ status: 'rejected', takedown_reason: 'Менше 100 підписників' });
	assert.equal(t.label, 'Причина відхилення');
	assert.equal(t.reason, 'Менше 100 підписників');
	assert.match(t.hint, /@tgsell_support_bot/);
});

test('removed by admin shows reason + hint; removed by seller has no hint', () => {
	const a = takedownInfo({ status: 'removed', takedown_reason: 'Видалено адміністратором' });
	assert.equal(a.label, 'Причина зняття');
	assert.ok(a.hint);
	const s = takedownInfo({ status: 'removed', takedown_reason: 'Знято продавцем' });
	assert.equal(s.hint, null);
});

test('published lot or missing reason → nothing', () => {
	assert.equal(takedownInfo({ status: 'approved', takedown_reason: 'old' }), null);
	assert.equal(takedownInfo({ status: 'rejected' }), null);
	assert.equal(takedownInfo(null), null);
});
