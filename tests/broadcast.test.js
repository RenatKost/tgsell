import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { buildBroadcastBody, canSend, dryRunFingerprint, parseIds, confirmText } from '../src/utils/broadcast.js';

const form = { key: ' promo-1 ', text: 'Привіт', segment: 'targeted', exCh: '', exB: '', targets: '@a, #5' };

describe('admin broadcast helpers', () => {
	it('dry-run by default, checkbox off by default', () => {
		const b = buildBroadcastBody(form);
		assert.equal(b.dry_run, true);
		assert.equal(b.try_no_bot, false);
		assert.equal(b.campaign_key, 'promo-1');
		assert.equal('confirm_token' in b, false);
	});
	it('real send carries the confirm token', () => {
		const b = buildBroadcastBody({ ...form, tryNoBot: true }, { dry: false, confirmToken: 'abc' });
		assert.equal(b.dry_run, false);
		assert.equal(b.confirm_token, 'abc');
		assert.equal(b.try_no_bot, true);
	});
	it('targets only for the targeted segment', () => {
		assert.equal(buildBroadcastBody({ ...form, segment: 'active_sellers' }).targets, '');
	});
	it('send allowed only after a dry-run of the same form', () => {
		const count = { confirm_token: 't', to_send: 2, fingerprint: dryRunFingerprint(form) };
		assert.equal(canSend(count, form), true);
		assert.equal(canSend(count, { ...form, tryNoBot: true }), false);
		assert.equal(canSend(count, { ...form, text: 'інше' }), false);
		assert.equal(canSend(null, form), false);
		assert.equal(canSend({ ...count, over_limit: true }, form), false);
		assert.equal(canSend({ ...count, to_send: 0 }, form), false);
	});
	it('parses ids and builds a Ukrainian confirm', () => {
		assert.deepEqual(parseIds('1, x, 3,-2'), [1, 3]);
		assert.match(confirmText({ to_send: 3, campaign_key: 'k', try_no_bot: true, no_bot_count: 1 }), /Надіслати повідомлення 3 отримувачам/);
	});
});
