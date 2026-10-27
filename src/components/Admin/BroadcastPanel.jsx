import { useEffect, useState } from 'react';
import { broadcastAPI } from '../../services/api';

const box = 'bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-5';
const input = 'w-full rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-800 dark:text-gray-100';
const ids = (s) => s.split(',').map((x) => parseInt(x.trim(), 10)).filter((n) => Number.isInteger(n) && n > 0);
const errText = (e) => { const d = e?.response?.data?.detail; return typeof d === 'string' ? d : 'Помилка запиту'; };

const RELIST = { segment: 'relist_top7', key: 'relist_top7_2026_10_27' };
const RELIST_TEXT = 'Вітаємо! До 1 листопада на TgSell діє акція: кожен новий лот, який схвалить модерація, отримує «Топ» на 7 днів безкоштовно (зазвичай це 10 USDT). Якщо ваш канал ще продається, виставте його знову: https://tgsell.me/sell. Розміщення безкоштовне, комісія 3% береться лише після угоди.';
const sellerName = (i) => (i.username ? `@${i.username}` : `user #${i.user_id}`);
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
	const [count, setCount] = useState(null);
	const [stats, setStats] = useState(null);
	const [err, setErr] = useState('');
	const [busy, setBusy] = useState(false);
	const isRelist = segment === RELIST.segment;
	const pickSegment = (v) => {
		setSegment(v); setCount(null); setStats(null); setErr('');
		if (v === RELIST.segment) { setKey(RELIST.key); setText(RELIST_TEXT); }
	};
	const body = (dry) => ({ campaign_key: key.trim(), text, segment, dry_run: dry, exclude_channel_ids: ids(exCh), exclude_bundle_ids: ids(exB) });

	const calc = async () => {
		setBusy(true); setErr('');
		try { const r = await broadcastAPI.run(body(true)); setCount(r.data); return r.data; }
		catch (e) { setErr(errText(e)); return null; } finally { setBusy(false); }
	};
	const send = async () => {
		if (!text.trim()) { setErr('Введіть текст повідомлення'); return; }
		const c = await calc();
		if (!c) return;
		if (c.over_limit) { setErr(`Забагато отримувачів: ${c.recipients} (ліміт ${c.limit})`); return; }
		if (!window.confirm(`Надіслати повідомлення ${c.to_send} отримувачам (кампанія «${c.campaign_key}»)?`)) return;
		setBusy(true);
		try { const r = await broadcastAPI.run(body(false)); setStats(r.data.stats); }
		catch (e) { setErr(errText(e)); } finally { setBusy(false); }
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
						<option value='relist_top7'>Акція «Топ 7 днів»: продавці знятих / неактивних / проданих лотів (relist_top7_2026_10_27)</option>
					</select>
				</label>
				{isRelist && <p className='text-sm text-amber-600 dark:text-amber-400'>Кампанія з фіксованим текстом. Завжди виключено лоти #61, #94, #95, #96 і канали сітки #1 (15–18). Один продавець отримує одне повідомлення, навіть якщо в нього кілька лотів. Спочатку натисніть «Порахувати» й перевірте список.</p>}
				<p className='text-sm text-gray-500 dark:text-gray-400'>Сегмент «активні»: продавці з активним (опублікованим) лотом, підписані на alert-бота. Ліміт — 500 отримувачів. Повторний запуск тієї самої кампанії не надсилає повідомлення вдруге.</p>
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
				{err && <p className='text-sm text-red-500'>{err}</p>}
				{count && (
					<p className='text-sm text-gray-700 dark:text-gray-200'>
						Отримувачів у сегменті (dry-run, нічого не надіслано): <b>{count.recipients}</b> · уже оброблено в цій кампанії: {count.already_processed} · буде надіслано: <b>{count.to_send}</b>
						{count.over_limit && <span className='text-red-500'> · перевищено ліміт {count.limit}</span>}
					</p>
				)}
				{count?.recipients_list && (
					<div className='space-y-3'>
						<h3 className='text-sm font-semibold text-gray-800 dark:text-white'>Отримувачі (підписані на alert-бота): {count.recipients_list.length}</h3>
						<LotList items={count.recipients_list} />
						<h3 className='text-sm font-semibold text-gray-800 dark:text-white'>Без бота (не отримають): {count.no_bot.length}</h3>
						{count.no_bot.length ? <LotList items={count.no_bot} /> : <p className='text-xs text-gray-400'>Немає</p>}
					</div>
				)}
				<div className='flex flex-wrap gap-2'>
					<button disabled={busy || !key.trim()} onClick={calc} className='px-4 py-2 rounded-xl text-sm font-semibold bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-200 disabled:opacity-50'>Порахувати</button>
					<button disabled={busy || !key.trim()} onClick={send} className='px-4 py-2 rounded-xl text-sm font-semibold bg-[#3498db] text-white disabled:opacity-50'>Надіслати</button>
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
							{stats.errors.map((e) => <li key={e.user_id}>{sellerName(e)}: {e.error}</li>)}
						</ul>
					)}
				</div>
			)}
		</div>
	);
};

export default BroadcastPanel;
