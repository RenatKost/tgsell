import { Fragment, useEffect, useState } from 'react';
import { userActivityAPI } from '../../services/api';

const errMsg = (e) => e?.response?.data?.detail || e?.message || 'Помилка';
const fmtTime = (s) => {
	s = Math.round(s || 0);
	if (s < 60) return `${s} с`;
	const m = Math.round(s / 60);
	return m < 60 ? `${m} хв` : `${Math.floor(m / 60)} год ${m % 60} хв`;
};
const fmtDate = (v) => v ? new Date(v + (v.endsWith('Z') ? '' : 'Z')).toLocaleString('uk-UA', { timeZone: 'Europe/Chisinau', dateStyle: 'short', timeStyle: 'short' }) : '—';

const UserActivityPanel = () => {
	const [items, setItems] = useState([]);
	const [funnels, setFunnels] = useState([]);
	const [msg, setMsg] = useState('');
	const [open, setOpen] = useState(null);

	useEffect(() => {
		(async () => {
			try {
				const [u, f] = await Promise.all([userActivityAPI.users(), userActivityAPI.funnel()]);
				setItems(u.data.items || []);
				setFunnels(f.data.funnels || []);
			} catch (e) { setMsg(errMsg(e)); }
		})();
	}, []);

	return (
		<div className='space-y-6'>
			{msg && <div className='text-sm text-red-600'>{msg}</div>}

			<div className='grid md:grid-cols-2 gap-4'>
				{funnels.map(f => (
					<div key={f.days} className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-4'>
						<h3 className='font-semibold text-gray-800 dark:text-gray-100 mb-3'>Воронка · {f.days} днів</h3>
						<div className='space-y-2'>
							{f.steps.map(s => (
								<div key={s.step} className='flex items-center justify-between text-sm'>
									<span className='text-gray-600 dark:text-gray-300'>{s.label}</span>
									<span className='font-semibold text-gray-800 dark:text-gray-100'>
										{s.users}
										{s.from_prev_pct != null && <span className='ml-2 text-xs font-normal text-gray-400'>{s.from_prev_pct}% від попереднього</span>}
									</span>
								</div>
							))}
						</div>
					</div>
				))}
			</div>

			<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 overflow-x-auto'>
				<table className='w-full text-sm'>
					<thead>
						<tr className='text-left text-xs text-gray-400 border-b dark:border-slate-700'>
							<th className='px-4 py-3'>Користувач</th>
							<th className='px-3 py-3'>Останній візит</th>
							<th className='px-3 py-3'>Сесії 7д / 30д</th>
							<th className='px-3 py-3'>Час 7д / 30д</th>
							<th className='px-3 py-3'>Перегляди</th>
							<th className='px-3 py-3'>Угоди</th>
						</tr>
					</thead>
					<tbody>
						{items.map(u => (
							<Fragment key={u.user_id}>
								<tr key={u.user_id} onClick={() => setOpen(open === u.user_id ? null : u.user_id)} className='border-t dark:border-slate-700 cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-700'>
									<td className='px-4 py-3'>
										<span className='font-semibold text-gray-800 dark:text-gray-100'>#{u.user_id} {u.first_name}</span>
										{u.username && <span className='text-gray-400'> @{u.username}</span>}
									</td>
									<td className='px-3 py-3 text-gray-500'>{fmtDate(u.last_seen_at)}</td>
									<td className='px-3 py-3'>{u.sessions_7d} / {u.sessions_30d}</td>
									<td className='px-3 py-3'>{fmtTime(u.seconds_7d)} / {fmtTime(u.seconds_30d)}</td>
									<td className='px-3 py-3'>{u.views_30d}</td>
									<td className='px-3 py-3'>{u.deals_30d} <span className='text-gray-400'>(оплачено {u.paid_30d})</span></td>
								</tr>
								{open === u.user_id && (
									<tr key={`${u.user_id}-d`} className='bg-gray-50 dark:bg-slate-900/40'>
										<td colSpan={6} className='px-4 py-3 text-gray-600 dark:text-gray-300'>
											<div>Переглядав: {u.viewed.length ? u.viewed.map(v => v.name || `#${v.channel_id}`).join(', ') : 'немає даних'}</div>
											<div className='text-xs text-gray-400 mt-1'>Пошуки: {u.searches_30d} · Обране: {u.favorites_30d} · Входи: {u.logins_30d} · Угод усього: {u.deals_total}</div>
										</td>
									</tr>
								)}
							</Fragment>
						))}
						{!items.length && <tr><td colSpan={6} className='px-4 py-6 text-gray-400'>Ще немає активності</td></tr>}
					</tbody>
				</table>
			</div>
		</div>
	);
};

export default UserActivityPanel;
