import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { dealTitle } from '../src/utils/dealTitle.js';

describe('dealTitle', () => {
	it('prefers the channel name', () => {
		assert.equal(dealTitle({ id: 7, channel_name: 'News UA', channel_id: 4 }), 'News UA');
	});

	it('uses the bundle name when the channel is missing', () => {
		assert.equal(dealTitle({ id: 7, channel_id: null, bundle_name: 'Медіа-сітка' }), 'Медіа-сітка');
	});

	it('uses the external link, then a generic external label', () => {
		assert.equal(dealTitle({ id: 7, is_external: true, channel_link: 'https://t.me/example' }), 'https://t.me/example');
		assert.equal(dealTitle({ id: 7, is_external: true }), 'Зовнішня угода');
	});

	it('falls back to Канал #id when the id is present', () => {
		assert.equal(dealTitle({ id: 7, channel_id: 84 }), 'Канал #84');
	});

	it('never renders «null» when channel_id is missing', () => {
		assert.equal(dealTitle({ id: 7, channel_id: null }), 'Угода #7');
		assert.equal(dealTitle({ id: 6, channel_name: '', channel_id: undefined }), 'Угода #6');
		assert.ok(!String(dealTitle({ id: 7, channel_id: null })).includes('null'));
	});
});
