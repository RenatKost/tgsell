import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { offerLinkNotice, OFFER_LINK_GENERIC, OFFER_LINK_EXPIRED_48H, OFFER_LINK_LOT_IN_DEAL } from '../src/utils/offerLink.js';

const recent = new Date().toISOString();
const stale = new Date(Date.now() - 49 * 60 * 60 * 1000).toISOString();

describe('offerLinkNotice', () => {
	it('is silent for a valid accepted offer the buyer can convert', () => {
		assert.equal(offerLinkNotice({
			channel_id: 10, status: 'accepted', can_create_deal: true, deal_id: null, accepted_at: recent,
		}, { channelId: 10 }), null);
	});

	it('is silent for a still-valid accepted offer the seller is viewing', () => {
		assert.equal(offerLinkNotice({
			channel_id: 10, status: 'accepted', can_create_deal: false, deal_id: null, accepted_at: recent,
		}, { channelId: 10 }), null);
	});

	it('explains an expired 48h acceptance window', () => {
		assert.equal(offerLinkNotice({
			channel_id: 10, status: 'accepted', can_create_deal: false, deal_id: null, accepted_at: stale,
		}, { channelId: 10 }), OFFER_LINK_EXPIRED_48H);
	});

	it('explains a competing deal that closed the offer', () => {
		assert.equal(offerLinkNotice({
			channel_id: 10, status: 'closed', close_reason: 'lot_in_deal', can_create_deal: false,
		}, { channelId: 10 }), OFFER_LINK_LOT_IN_DEAL);
	});

	it('uses a generic notice for missing, foreign, or mismatched offers', () => {
		assert.equal(offerLinkNotice(null, { channelId: 10, error: { response: { status: 404 } } }), OFFER_LINK_GENERIC);
		assert.equal(offerLinkNotice(null, { channelId: 10, error: { response: { status: 403 } } }), OFFER_LINK_GENERIC);
		assert.equal(offerLinkNotice({
			channel_id: 99, status: 'accepted', can_create_deal: true, accepted_at: recent,
		}, { channelId: 10 }), OFFER_LINK_GENERIC);
		assert.equal(offerLinkNotice({
			channel_id: 10, status: 'declined', can_create_deal: false,
		}, { channelId: 10 }), OFFER_LINK_GENERIC);
	});
});
