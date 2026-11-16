import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
	shouldShowDealBotBanner,
	dealBotBannerCopy,
	dealBotBannerHint,
	alertBotUsername,
} from '../src/utils/dealBotBanner.js';

const notify = (extra = {}) => ({
	telegram_bound: true,
	bot_started: false,
	bot_unreachable: false,
	deep_link: 'https://t.me/tgsell_alert_bot?start=deal_35',
	bot_username: 'tgsell_alert_bot',
	...extra,
});

describe('shouldShowDealBotBanner', () => {
	it('shows for a party who has not started the bot, including closed deals', () => {
		const tg = notify();
		assert.equal(shouldShowDealBotBanner({ isParty: true, tgNotify: tg }), true);
		// status is intentionally not a parameter — closed deals must still show it
	});

	it('shows when the last delivery was chat not found / unreachable', () => {
		assert.equal(shouldShowDealBotBanner({
			isParty: true,
			tgNotify: notify({ bot_started: true, bot_unreachable: true }),
		}), true);
	});

	it('hides when the party already has a working bot chat', () => {
		assert.equal(shouldShowDealBotBanner({
			isParty: true,
			tgNotify: notify({ bot_started: true, bot_unreachable: false }),
		}), false);
	});

	it('hides for staff observers and when notify is missing', () => {
		assert.equal(shouldShowDealBotBanner({ isParty: false, tgNotify: notify() }), false);
		assert.equal(shouldShowDealBotBanner({ isParty: true, tgNotify: null }), false);
	});
});

describe('dealBotBannerCopy', () => {
	it('asks the party to start the alerts bot', () => {
		assert.equal(
			dealBotBannerCopy(notify()),
			'Запустіть @tgsell_alert_bot, щоб отримувати сповіщення угоди',
		);
	});

	it('explains a failed Telegram delivery and still names the bot', () => {
		assert.equal(
			dealBotBannerCopy(notify({ bot_unreachable: true })),
			'Не вдалося доставити повідомлення в Telegram. Запустіть @tgsell_alert_bot, щоб отримувати сповіщення угоди',
		);
	});

	it('uses the username from the API when present', () => {
		assert.equal(alertBotUsername(notify({ bot_username: '@OtherBot' })), 'OtherBot');
		assert.match(dealBotBannerCopy(notify({ bot_username: 'OtherBot' })), /@OtherBot/);
	});

	it('hints to bind Telegram when the account has no telegram id', () => {
		assert.equal(dealBotBannerHint(notify({ telegram_bound: false })), 'Спершу увійдіть на сайт через Telegram.');
		assert.equal(dealBotBannerHint(notify()), null);
	});
});
