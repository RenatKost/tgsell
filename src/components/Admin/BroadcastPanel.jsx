import { useEffect, useState } from 'react';
import { broadcastAPI } from '../../services/api';
import { buildBroadcastBody, canSend, confirmText, dryRunFingerprint, NO_BOT_HINT } from '../../utils/broadcast';

const box = 'bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-5';
const input = 'w-full rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-800 dark:text-gray-100';
const errText = (e) => { const d = e?.response?.data?.detail; return typeof d === 'string' ? d : 'Помилка запиту'; };

const RELIST = { segment: 'relist_top7', key: 'relist_top7_2026_10_27' };
const RELIST_TEXT = 'Вітаємо! До 1 листопада на TgSell діє акція: кожен новий лот, який схвалить модерація, отримує «Топ» на 7 днів безкоштовно (зазвичай це 10 USDT). Якщо ваш канал ще продається, виставте його знову: https://tgsell.me/sell. Розміщення безкоштовне, комісія 3% береться лише після угоди.';
const sellerName = (i) => (i.username ? `@${i.username}` : `user #${i.user_id}`);
const NoBotList = ({ items }) => (
	<ul className='space-y-1 text-xs text-gray-700 dark:text-gray-200'>
		{items.map((i) => (
			<li key={i.user_id} className='flex flex-wrap gap-x-2'>
				<span className='font-medium'>{sellerName(i)}</span>
				<span className='text-gray-400'>{i.reason_label}</span>
				{i.lots?.length > 0 && <span className='text-gray-400'>· лоти {i.lots.map((l) => `#${l.id}`).join(', ')}</span>}
			</li>
		))}
	</ul>
);
const LotList = ({ items }) => (
	<div className='overflow-x-auto'>
		<table className='w-full text-xs text-left text-gray-700 dark:text-gray-200'>
			<thead><tr className='text-gray-400'><th className='py-1 pr-3'>Продавець</th><th className='py-1 pr-3'>Лот</th><th className='py-1 pr-3'>Канал</th><th className='py-1'>Статус</th></tr></thead>
			<tbody>
				{items.flatMap((i) => i.lots.map((l, n) => (
					<tr key={`${i.user_id}-${l.id}`} className='border-t border-gray-100 dark:border-slate-700'>
						<td className='py-1 pr-3'>{n === 0 ? sellerName(i) : ''}</td><td className='py-1 pr-3'>#{l.id}</td>
						<td className='py-1 pr-3 break-all'>{l.channel || l.link}</td><td className='py-1'>{l.status_label}</td>
					</tr>
				)))}
			</tbody>
		</table>
	</div>
);

const BroadcastPanel = () => {
	const [segment, setSegment] = useState('active_sellers');
	const [text, setText] = useState('');
	const [key, setKey] = useState('');
	const [exCh, setExCh] = useState('');
	const [exB, setExB] = useState('');
	const [targets, setTargets] = useState('');
	const [tryNoBot, setTryNoBot] = useState(false);
	const [count, setCount] = useState(null);
	const [stats, setStats] = useState(null);
	const [err, setErr] = useState('');
	const [busy, setBusy] = useState(false);
	const isRelist = segment === RELIST.segment;
	const isTargeted = segment === 'targeted';
	const form = { key, text, segment, exCh, exB, targets, tryNoBot };
	const pickSegment = (v) => {
		setSegment(v); setCount(null); setStats(null); setErr(''); setTryNoBot(false);
		if (v === RELIST.segment) { setKey(RELIST.key); setText(RELIST_TEXT); }
	};

	const calc = async () => {
		setBusy(true); setErr('');
		try {
			const r = await broadcastAPI.run(buildBroadcastBody(form));
			setCount({ ...r.data, fingerprint: dryRunFingerprint(form) });
		} catch (e) { setErr(errText(e)); setCount(null); } finally { setBusy(false); }
	};
	const send = async () => {
		if (!text.trim()) { setErr('Введіть текст повідомлення'); return; }
		if (!canSend(count, form)) { setErr('Спершу натисніть «Порахувати» і перевірте отримувачів'); return; }
		if (!window.confirm(confirmText(count))) return;
		setBusy(true); setErr('');
		try {
			const r = await broadcastAPI.run(buildBroadcastBody(form, { dry: false, confirmToken: count.confirm_token }));
			setStats(r.data.stats); setCount(null);
		} catch (e) { setErr(errText(e)); setCount(null); } finally { setBusy(false); }
	};
	useEffect(() => {
		if (!stats?.running) return undefined;
		const t = setInterval(() => broadcastAPI.stats(stats.campaign_key).then((r) => setStats(r.data)).catch(() => {}), 2000);
		return () => clearInterval(t);
	}, [stats?.running, stats?.campaign_key]);

	return (
		<div className='space-y-6 max-w-3xl'>
			<h1 className='text-2xl font-bold text-gray-800 dark:text-white'>Розсилка</h1>
			<div className={`${box} space-y-4`}>
				<label className='block text-xs text-gray-400'>Сегмент
					<select className={`${input} mt-1`} value={segment} onChange={(e) => pickSegment(e.target.value)}>
						<option value='active_sellers'>Продавці з активним лотом</option>
					<option value='targeted'>Адресна розсилка: вибрані користувачі або лоти</option>
						<option value='relist_top7'>Акція «Топ 7 днів»: продавці знятих / неактивних / проданих лотів (relist_top7_2026_10_27)</option>
					</select>
				</label>
				{isRelist && <p className='text-sm text-amber-600 dark:text-amber-400'>Кампанія з фіксованим текстом. Завжди виключено лоти #61, #94, #95, #96 і канали сітки #1 (15–18). Один продавець отримує одне повідомлення, навіть якщо в нього кілька лотів. Спочатку натисніть «Порахувати» й перевірте список.</p>}
				{isTargeted && (
					<label className='block text-xs text-gray-400'>Отримувачі: ID користувача, @username або #ID лота (отримає продавець лота), через кому чи з нового рядка
						<textarea rows={3} className={`${input} mt-1`} placeholder='12, @seller_name, #45' value={targets} onChange={(e) => setTargets(e.target.value)} />
					</label>
				)}
				<p className='text-sm text-gray-500 dark:text-gray-400'>Спершу «Порахувати» (dry-run): нічого не надсилається, ви бачите отримувачів і тих, хто без бота. «Надіслати» стає доступним лише після перевірки, а будь-яка зміна вимагає нової. Ліміт — 500 отримувачів, повідомлення йдуть з паузою (~10 за секунду). Повторний запуск тієї самої кампанії не надсилає повідомлення вдруге.</p>
				<label className='block text-xs text-gray-400'>Текст повідомлення (HTML Telegram)
					<textarea rows={6} maxLength={4000} readOnly={isRelist} className={`${input} mt-1`} value={text} onChange={(e) => setText(e.target.value)} />
				</label>
				<label className='block text-xs text-gray-400'>campaign_key (унікальний ключ кампанії)
					<input readOnly={isRelist} className={`${input} mt-1`} placeholder='promo-2026-10' value={key} onChange={(e) => setKey(e.target.value)} />
				</label>
				<div className='grid sm:grid-cols-2 gap-3'>
					<label className='block text-xs text-gray-400'>Виключити лоти (ID каналів, через кому)
						<input className={`${input} mt-1`} placeholder='12, 34' value={exCh} onChange={(e) => setExCh(e.target.value)} />
					</label>
					<label className='block text-xs text-gray-400'>Виключити сітки (ID, через кому)
						<input className={`${input} mt-1`} placeholder='5' value={exB} onChange={(e) => setExB(e.target.value)} />
					</label>
				</div>
				<label className='flex items-start gap-2 text-sm text-gray-700 dark:text-gray-200'>
					<input type='checkbox' className='mt-1' checked={tryNoBot} onChange={(e) => setTryNoBot(e.target.checked)} />
					<span>Спробувати надіслати й тим, хто без бота <span className='text-gray-400'>(за замовчуванням вимкнено; повідомлення дійде, лише якщо людина колись писала боту і не заблокувала його)</span></span>
				</label>
				{err && <p className='text-sm text-red-500'>{err}</p>}
				{count && (
					<div className='space-y-3 rounded-xl bg-gray-50 dark:bg-slate-900/60 p-4'>
						<p className='text-sm text-gray-700 dark:text-gray-200'>
							Dry-run, нічого не надіслано. Отримувачів: <b>{count.recipients}</b> (з ботом: {count.subscribed}{count.try_no_bot ? `, спроба без бота: ${count.recipients - count.subscribed}` : ''}) · уже оброблено в цій кампанії: {count.already_processed} · буде надіслано: <b>{count.to_send}</b>
							{count.over_limit && <span className='text-red-500'> · перевищено ліміт {count.limit}</span>}
						</p>
						{count.not_found?.length > 0 && <p className='text-xs text-amber-600'>Не знайдено: {count.not_found.join(', ')}</p>}
						{count.invalid?.length > 0 && <p className='text-xs text-amber-600'>Не розпізнано: {count.invalid.join(', ')}</p>}
						{count.excluded?.length > 0 && <p className='text-xs text-gray-400'>Виключено (заблоковані, неактивні або акаунти власників): {count.excluded.map((i) => `#${i}`).join(', ')}</p>}
						{isRelist && count.recipients_list && (
							<>
								<h3 className='text-sm font-semibold text-gray-800 dark:text-white'>Отримувачі (підписані на alert-бота): {count.recipients_list.length}</h3>
								<LotList items={count.recipients_list} />
							</>
						)}
						{isTargeted && count.recipients_list?.length > 0 && (
							<p className='text-xs text-gray-600 dark:text-gray-300'>З ботом: {count.recipients_list.map(sellerName).join(', ')}</p>
						)}
						<h3 className='text-sm font-semibold text-gray-800 dark:text-white'>Без бота{count.try_no_bot ? ' (спробуємо надіслати)' : ' (не отримають)'}: {count.no_bot_count}</h3>
						{count.no_bot?.length ? (<><p className='text-xs text-gray-400'>{NO_BOT_HINT}</p><NoBotList items={count.no_bot} /></>) : <p className='text-xs text-gray-400'>Немає</p>}
					</div>
				)}
				<div className='flex flex-wrap gap-2'>
					<button disabled={busy || !key.trim()} onClick={calc} className='px-4 py-2 rounded-xl text-sm font-semibold bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-200 disabled:opacity-50'>Порахувати</button>
					<button disabled={busy || !key.trim() || !canSend(count, form)} onClick={send} className='px-4 py-2 rounded-xl text-sm font-semibold bg-[#3498db] text-white disabled:opacity-50'>Надіслати</button>
				</div>
			</div>
			{stats && (
				<div className={box}>
					<h2 className='font-bold text-gray-800 dark:text-white mb-3'>Кампанія «{stats.campaign_key}» {stats.running ? '— надсилається…' : ''}</h2>
					<div className='grid grid-cols-3 gap-3 text-center'>
						<div><div className='text-2xl font-bold text-green-600'>{stats.sent}</div><div className='text-xs text-gray-400'>Надіслано</div></div>
						<div><div className='text-2xl font-bold text-red-500'>{stats.failed}</div><div className='text-xs text-gray-400'>Помилки</div></div>
						<div><div className='text-2xl font-bold text-gray-500'>{stats.pending}</div><div className='text-xs text-gray-400'>В черзі</div></div>
					</div>
					{stats.errors?.length > 0 && (
						<ul className='mt-4 space-y-1 text-xs text-red-500'>
							{stats.errors.map((e) => <li key={e.user_id}>{sellerName(e)}: {e.reason_label ? `${e.reason_label} — ` : ''}{e.error}</li>)}
						</ul>
					)}
				</div>
			)}
		</div>
	);
};

export default BroadcastPanel;
