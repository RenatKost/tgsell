import { useEffect, useState } from 'react';
import { broadcastAPI } from '../../services/api';

const box = 'bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-5';
const input = 'w-full rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-800 dark:text-gray-100';
const ids = (s) => s.split(',').map((x) => parseInt(x.trim(), 10)).filter((n) => Number.isInteger(n) && n > 0);
const errText = (e) => { const d = e?.response?.data?.detail; return typeof d === 'string' ? d : 'Помилка запиту'; };

const BroadcastPanel = () => {
	const [text, setText] = useState('');
	const [key, setKey] = useState('');
	const [exCh, setExCh] = useState('');
	const [exB, setExB] = useState('');
	const [count, setCount] = useState(null);
	const [stats, setStats] = useState(null);
	const [err, setErr] = useState('');
	const [busy, setBusy] = useState(false);
	const body = (dry) => ({ campaign_key: key.trim(), text, dry_run: dry, exclude_channel_ids: ids(exCh), exclude_bundle_ids: ids(exB) });

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
				<p className='text-sm text-gray-500 dark:text-gray-400'>Сегмент: продавці з активним (опублікованим) лотом, підписані на alert-бота. Ліміт — 500 отримувачів. Повторний запуск тієї самої кампанії не надсилає повідомлення вдруге.</p>
				<label className='block text-xs text-gray-400'>Текст повідомлення (HTML Telegram)
					<textarea rows={6} maxLength={4000} className={`${input} mt-1`} value={text} onChange={(e) => setText(e.target.value)} />
				</label>
				<label className='block text-xs text-gray-400'>campaign_key (унікальний ключ кампанії)
					<input className={`${input} mt-1`} placeholder='promo-2026-10' value={key} onChange={(e) => setKey(e.target.value)} />
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
						Отримувачів у сегменті: <b>{count.recipients}</b> · уже оброблено в цій кампанії: {count.already_processed} · буде надіслано: <b>{count.to_send}</b>
						{count.over_limit && <span className='text-red-500'> · перевищено ліміт {count.limit}</span>}
					</p>
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
				</div>
			)}
		</div>
	);
};

export default BroadcastPanel;
