import test from 'node:test';
import assert from 'node:assert/strict';
import { dealViewer, heroLabel, heroCounterpart, readinessView, transferView, dealChatComposer, isDealChatReadOnly, messageRoleLabel } from '../src/utils/dealViewer.js';

const deal = (extra = {}) => ({ buyer_id: 10, seller_id: 20, buyer_name: 'Олег', seller_name: 'Павло', buyer_ready: false, seller_ready: false,
	buyer_confirmed_transfer: false, seller_confirmed_transfer: false, ...extra });
const admin = { id: 99, role: 'admin' };

test('staff non-party never sees «Ви підтвердили» when nobody confirmed', () => {
	const d = deal();
	const v = dealViewer(admin, d);
	assert.equal(v.isStaffObserver, true);
	const r = readinessView(v, d);
	assert.equal(r.action, null);
	assert.doesNotMatch(r.banner, /Ви підтвердили/);
	assert.equal(r.banner, 'Очікуємо підтвердження готовності обох сторін');
	assert.doesNotMatch(transferView(v, d).banner, /Ви підтвердили/);
});

test('staff non-party: hero is neutral, not «Ви продаєте»', () => {
	const d = deal();
	const v = dealViewer({ id: 5, role: 'moderator' }, d);
	assert.equal(heroLabel(v), 'Гарант TgSell · ви не сторона угоди');
	assert.equal(heroCounterpart(v, d), 'Продавець: Павло · Покупець: Олег');
});

test('staff non-party: one side ready names the side still waiting', () => {
	const v = dealViewer(admin, deal());
	assert.equal(readinessView(v, deal({ buyer_ready: true })).banner, 'Очікуємо підтвердження готовності продавця');
	assert.equal(transferView(v, deal({ seller_confirmed_transfer: true })).banner, 'Очікуємо підтвердження передачі від покупця');
});

test('parties keep their wording and buttons', () => {
	const d = deal();
	const b = dealViewer({ id: 10, role: 'user' }, d);
	const s = dealViewer({ id: 20, role: 'admin' }, d); // admin who is the seller is a party
	assert.equal(heroLabel(b), 'Ви купуєте');
	assert.equal(heroLabel(s), 'Ви продаєте');
	assert.equal(readinessView(b, d).action, 'confirm');
	assert.equal(readinessView(s, deal({ seller_ready: true })).banner, 'Ви підтвердили. Очікуйте іншу сторону');
	assert.equal(transferView(b, deal({ buyer_confirmed_transfer: true })).banner, 'Ви підтвердили. Очікуйте іншу сторону');
});

test('id type mismatch does not turn a party into an observer', () => {
	const v = dealViewer({ id: '20', role: 'user' }, deal());
	assert.equal(v.isSeller, true);
	assert.equal(dealViewer(null, deal()).isParty, false);
});

test('closed deal (completed or cancelled) is read-only chat', () => {
	const d = deal({ status: 'completed' });
	const c = dealChatComposer({ id: 10, role: 'user' }, d);
	assert.equal(isDealChatReadOnly(d), true);
	assert.equal(c.readOnly, true);
	assert.equal(c.hint, 'Угоду закрито — чат лише для читання');
	assert.equal(c.placeholder, 'Угоду закрито — чат лише для читання');
	assert.equal(c.asGuarantor, false);
	assert.equal(isDealChatReadOnly(deal({ status: 'cancelled' })), true);
	assert.equal(isDealChatReadOnly(deal({ status: 'paid' })), false);
});

test('staff non-party on an open deal writes as guarantor', () => {
	const c = dealChatComposer(admin, deal({ status: 'paid' }));
	assert.equal(c.readOnly, false);
	assert.equal(c.asGuarantor, true);
	assert.equal(c.placeholder, 'Написати як гарант TgSell…');
});

test('staff who is a party keeps the party composer', () => {
	const c = dealChatComposer({ id: 20, role: 'admin' }, deal({ status: 'paid' }));
	assert.equal(c.asGuarantor, false);
	assert.equal(c.placeholder, 'Написати…');
});

test('messageRoleLabel from sender_role / as_guarantor', () => {
	assert.equal(messageRoleLabel({ sender_role: 'seller' }), 'Продавець');
	assert.equal(messageRoleLabel({ sender_role: 'buyer' }), 'Покупець');
	assert.equal(messageRoleLabel({ sender_role: 'guarantor' }), 'Гарант');
	assert.equal(messageRoleLabel({ sender_role: 'seller', as_guarantor: true }), 'Гарант');
	assert.equal(messageRoleLabel({ is_system: true, sender_role: 'seller' }), null);
	assert.equal(messageRoleLabel(null), null);
});
