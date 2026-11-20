// Admin broadcast helpers (pure, unit-tested in tests/broadcast.test.js).

export const parseIds = (s) => String(s || '').split(',').map((x) => parseInt(x.trim(), 10)).filter((n) => Number.isInteger(n) && n > 0);

// Request body for POST /admin/broadcast. «Спробувати надіслати» (tryNoBot) is off unless ticked.
export const buildBroadcastBody = ({ key, text, segment, exCh, exB, targets, tryNoBot = false }, { dry = true, confirmToken = '' } = {}) => {
	const body = {
		campaign_key: String(key || '').trim(), text: text || '', segment, dry_run: dry,
		exclude_channel_ids: parseIds(exCh), exclude_bundle_ids: parseIds(exB),
		targets: segment === 'targeted' ? (targets || '') : '',
		try_no_bot: Boolean(tryNoBot),
	};
	if (!dry) body.confirm_token = confirmToken || '';
	return body;
};

// Fingerprint of what the admin checked in the dry-run; any change hides «Надіслати» until a new dry-run.
export const dryRunFingerprint = (form) => JSON.stringify(buildBroadcastBody(form));

export const canSend = (count, form) => Boolean(count && count.confirm_token && !count.over_limit && count.to_send > 0
	&& count.fingerprint === dryRunFingerprint(form));

export const NO_BOT_HINT = 'Ці люди не запускали @tgsell_alert_bot або бот для них недоступний. За замовчуванням вони не отримають повідомлення.';

export const confirmText = (count) => {
	const extra = count.try_no_bot ? ` (разом зі спробою для ${count.no_bot_count} без бота)` : '';
	return `Надіслати повідомлення ${count.to_send} отримувачам${extra}, кампанія «${count.campaign_key}»? Скасувати відправку після старту не можна.`;
};
