import { useEffect, useState } from 'react';
import { wantedAPI } from '../../services/api';
import { fmtRange, fmtDate, LANGUAGE_LABELS } from '../../utils/wanted';

const FILTERS = [
	{ v: 'pending', t: 'На модерації' }, { v: 'approved', t: 'Схвалені' },
	{ v: 'rejected', t: 'Відхилені' }, { v: 'all', t: 'Всі' },
];

const Stat = ({ label, value }) => (
	<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-4'>
		<div className='text-xs text-gray-400'>{label}</div>
		<div className='text-2xl font-bold text-gray-800 dark:text-gray-100'>{value ?? '—'}</div>
	</div>
);

const WantedPanel = () => {
	const [status, setStatus] = useState('pending');
	const [items, setItems] = useState([]);
	const [stats, setStats] = useState(null);
	const [busy, setBusy] = useState(null);
	const [err, setErr] = useState('');

	const load = async () => {
		try {
			const [l, s] = await Promise.all([wantedAPI.adminList(status), wantedAPI.adminStats()]);
			setItems(l.data.items || []); setStats(s.data); setErr('');
		} catch (e) { setErr(e?.response?.data?.detail || 'Помилка завантаження'); }
	};
	useEffect(() => { load(); }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

	const act = async (id, fn) => {
		setBusy(id);
		try { await fn(); await load(); } catch (e) { alert(e?.response?.data?.detail || 'Помилка'); }
		finally { setBusy(null); }
	};
	const reject = (id) => {
		const reason = window.prompt('Причина відхилення', 'Не відповідає правилам');
		if (reason === null) return;
		act(id, () => wantedAPI.reject(id, reason));
	};

	return (
		<div className='space-y-4'>
			<div className='flex items-center justify-between'>
				<h2 className='text-2xl font-bold text-gray-800 dark:text-gray-100'>Шукаю канал</h2>
				<button onClick={load} className='bg-[#3498db] text-white px-4 py-2 rounded-xl text-sm font-semibold'>Оновити</button>
			</div>
			<div className='grid grid-cols-2 md:grid-cols-4 gap-3'>
				<Stat label='Запитів усього' value={stats?.requests_total} />
				<Stat label='Активних / на модерації' value={stats ? `${stats.active} / ${stats.pending}` : null} />
				<Stat label='Лотів через кнопку' value={stats?.lots_from_button} />
				<Stat label='Угод з цих лотів' value={stats?.deals_from_lots} />
			</div>
			<div className='flex gap-2'>
				{FILTERS.map((f) => (
					<button key={f.v} onClick={() => setStatus(f.v)}
						className={`px-3 py-1.5 rounded-xl text-sm ${status === f.v ? 'bg-[#3498db] text-white' : 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-gray-300'}`}>{f.t}</button>
				))}
			</div>
			{err && <div className='text-sm text-red-600'>{err}</div>}
			<div className='space-y-3'>
				{items.length === 0 && <div className='text-gray-400 text-sm'>Немає запитів</div>}
				{items.map((r) => (
					<div key={r.id} className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-4 text-sm text-gray-700 dark:text-gray-300'>
						<div className='flex flex-wrap gap-x-4 gap-y-1 items-center'>
							<b>#{r.id} {r.category}</b>
							<span>{fmtRange(r.subs_min, r.subs_max, 'підп.')}</span>
							<span>{fmtRange(r.budget_min, r.budget_max, 'USDT')}</span>
							<span>{LANGUAGE_LABELS[r.language] || r.language}</span>
							<span className='text-gray-400'>{fmtDate(r.created_at)} · користувач #{r.user_id} {r.user_name ? `(${r.user_name})` : ''}</span>
							<span className='text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-slate-700'>{r.status}</span>
						</div>
						{r.comment && <p className='mt-2 break-words'>{r.comment}</p>}
						{r.auto_flags?.length > 0 && <p className='mt-2 text-red-500 font-semibold'>⚠ Автоперевірка: {r.auto_flags.join(', ')}</p>}
						{r.rejection_reason && <p className='mt-2 text-red-500'>Причина: {r.rejection_reason}</p>}
						{r.status === 'pending' && (
							<div className='mt-3 flex gap-2'>
								<button disabled={busy === r.id} onClick={() => act(r.id, () => wantedAPI.approve(r.id))}
									className='bg-green-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50'>Схвалити</button>
								<button disabled={busy === r.id} onClick={() => reject(r.id)}
									className='bg-red-600 text-white px-3 py-1.5 rounded-lg disabled:opacity-50'>Відхилити</button>
							</div>
						)}
					</div>
				))}
			</div>
		</div>
	);
};

export default WantedPanel;
