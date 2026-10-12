import { useEffect, useState } from 'react';
import { adminAPI } from '../../services/api';

const AuditLogPanel = () => {
	const [action, setAction] = useState('');
	const [page, setPage] = useState(1);
	const [data, setData] = useState({ items: [], total: 0, limit: 50 });
	const [err, setErr] = useState('');

	const load = async () => {
		try {
			const { data } = await adminAPI.auditLog({ action: action || undefined, page });
			setData(data); setErr('');
		} catch (e) { setErr(e?.response?.data?.detail || 'Помилка'); }
	};
	useEffect(() => { load(); }, [page]); // eslint-disable-line react-hooks/exhaustive-deps
	const pages = Math.max(1, Math.ceil((data.total || 0) / (data.limit || 50)));

	return (
		<div className='space-y-4'>
			<h2 className='text-2xl font-bold text-gray-800 dark:text-gray-100'>Журнал дій адміністраторів</h2>
			<div className='flex gap-2'>
				<input value={action} onChange={e => setAction(e.target.value)} onKeyDown={e => e.key === 'Enter' && (setPage(1), load())}
					placeholder='Фільтр дії: user. / deal. / channel. / escrow.' className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2 text-sm bg-white dark:bg-slate-700 dark:text-gray-200' />
				<button onClick={() => { setPage(1); load(); }} className='bg-[#3498db] text-white px-4 py-2 rounded-xl text-sm font-semibold'>Фільтр</button>
			</div>
			{err && <div className='text-sm text-red-600'>{err}</div>}
			<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 overflow-x-auto'>
				<table className='w-full text-sm text-gray-700 dark:text-gray-300'>
					<thead><tr className='text-left text-xs text-gray-400 uppercase'>
						<th className='p-3'>Час</th><th className='p-3'>Хто</th><th className='p-3'>Дія</th><th className='p-3'>Об’єкт</th><th className='p-3'>Деталі</th>
					</tr></thead>
					<tbody>
						{data.items.map(r => (
							<tr key={r.id} className='border-t border-gray-100 dark:border-slate-700 align-top'>
								<td className='p-3 whitespace-nowrap'>{r.created_at ? new Date(r.created_at + 'Z').toLocaleString() : ''}</td>
								<td className='p-3'>{r.actor_id ? `#${r.actor_id} ${r.actor || ''}` : 'system'}</td>
								<td className='p-3 font-mono'>{r.action}</td>
								<td className='p-3'>{r.target_type} #{r.target_id}</td>
								<td className='p-3 font-mono text-xs break-all'>{r.details ? JSON.stringify(r.details) : ''}</td>
							</tr>
						))}
					</tbody>
				</table>
				{!data.items.length && <div className='p-4 text-sm text-gray-400'>Записів немає</div>}
			</div>
			<div className='flex justify-between text-sm text-gray-500'>
				<button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className='disabled:opacity-40'>←</button>
				<span>{page} / {pages} · {data.total}</span>
				<button disabled={page >= pages} onClick={() => setPage(p => p + 1)} className='disabled:opacity-40'>→</button>
			</div>
		</div>
	);
};

export default AuditLogPanel;
