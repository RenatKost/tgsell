/** Deal-page banner: ask a party to start the alerts bot so they get deal notifications. */

export const DEFAULT_ALERT_BOT_USERNAME = 'tgsell_alert_bot';

export function alertBotUsername(tgNotify) {
	const raw = (tgNotify && tgNotify.bot_username) || DEFAULT_ALERT_BOT_USERNAME;
	return String(raw).replace(/^@/, '');
}

/**
 * Show the banner to a deal party when the alerts bot cannot write to them.
 * Status does not matter: active and closed (completed/cancelled) deals both notify via Telegram.
 * Staff observers are not parties and do not see it.
 */
export function shouldShowDealBotBanner({ isParty, tgNotify }) {
	if (!isParty || !tgNotify) return false;
	return Boolean(tgNotify.bot_unreachable || !tgNotify.bot_started);
}

export function dealBotBannerCopy(tgNotify) {
	const bot = `@${alertBotUsername(tgNotify)}`;
	if (tgNotify && tgNotify.bot_unreachable) {
		return `Не вдалося доставити повідомлення в Telegram. Запустіть ${bot}, щоб отримувати сповіщення угоди`;
	}
	return `Запустіть ${bot}, щоб отримувати сповіщення угоди`;
}

export function dealBotBannerHint(tgNotify) {
	if (tgNotify && !tgNotify.telegram_bound) {
		return 'Спершу увійдіть на сайт через Telegram.';
	}
	return null;
}
