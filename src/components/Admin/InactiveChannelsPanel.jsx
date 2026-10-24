import { fmtNum } from '../../utils/money';
import { useEffect, useState } from 'react';
import { adminAPI } from '../../services/api';

const fmt = v => (v ? new Date(v).toLocaleString() : '—');

const InactiveChannelsPanel = () => {
	const [items, setItems] = useState([]);
	const [err, setErr] = useState('');
	const [busy, setBusy] = useState(null);

	const load = async () => {
		try { const { data } = await adminAPI.inactiveChannels(); setItems(data.items || []); setErr(''); }
		catch (e) { setErr(e?.response?.data?.detail || 'Помилка завантаження'); }
	};
	useEffect(() => { load(); }, []);

	const remove = async (c) => {
		if (c.blockers?.length) { alert('Неможливо зняти з біржі:\n' + c.blockers.join('\n')); return; }
		if (!window.confirm(`Зняти лот #${c.id} ${c.channel_name || c.telegram_link} з біржі?\nПричина: ${c.reason || '—'}`)) return;
		setBusy(c.id);
		try { await adminAPI.removeChannel(c.id); await load(); }
		catch (e) { alert(e?.response?.data?.detail || 'Помилка'); }
		finally { setBusy(null); }
	};

	return (
		<div className='space-y-4'>
			<div className='flex items-center justify-between'>
				<h2 className='text-2xl font-bold text-gray-800 dark:text-gray-100'>Неактивні канали</h2>
				<button onClick={load} className='bg-[#3498db] text-white px-4 py-2 rounded-xl text-sm font-semibold'>Оновити</button>
			</div>
			<p className='text-sm text-gray-500 dark:text-gray-400'>Лоти, чий username не резолвиться, канал видалено або бот втратив доступ (за даними збирача статистики).</p>
			{err && <div className='text-sm text-red-600'>{err}</div>}
			<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 overflow-x-auto'>
				<table className='w-full text-sm text-gray-700 dark:text-gray-300'>
					<thead><tr className='text-left text-xs text-gray-400 uppercase'>
						<th className='p-3'>Лот</th><th className='p-3'>Причина</th><th className='p-3'>Неактивний з</th><th className='p-3'>Остання успішна перевірка</th><th className='p-3'></th>
					</tr></thead>
					<tbody>
						{items.length === 0 && <tr><td colSpan={5} className='p-4 text-center text-gray-400'>Немає неактивних каналів</td></tr>}
						{items.map(c => (
							<tr key={c.id} className='border-t border-gray-100 dark:border-slate-700 align-top'>
								<td className='p-3'>
									<div className='font-semibold'>#{c.id} {c.channel_name}</div>
									<a href={c.telegram_link} target='_blank' rel='noreferrer' className='text-xs text-[#3498db] break-all'>{c.telegram_link}</a>
									<div className='text-xs text-gray-400'>{c.status} · {fmtNum(c.price)} USDT</div>
								</td>
								<td className='p-3 text-xs break-all max-w-xs'>{c.reason || '—'}</td>
								<td className='p-3 whitespace-nowrap'>{fmt(c.inactive_since)}</td>
								<td className='p-3 whitespace-nowrap'>{fmt(c.last_check_ok_at)}</td>
								<td className='p-3'>
									<button disabled={busy === c.id} onClick={() => remove(c)}
										className={`px-3 py-1.5 rounded-lg text-xs font-semibold text-white ${c.blockers?.length ? 'bg-gray-400' : 'bg-red-500 hover:bg-red-600'}`}>
										Зняти з біржі
									</button>
									{c.blockers?.length > 0 && <div className='text-xs text-amber-600 mt-1'>{c.blockers.join('; ')}</div>}
								</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	);
};

export default InactiveChannelsPanel;
