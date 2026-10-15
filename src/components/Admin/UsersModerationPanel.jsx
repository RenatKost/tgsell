import { fmtUsdt } from '../../utils/money';
import { useEffect, useState } from 'react';
import { adminAPI } from '../../services/api';

const errMsg = (e) => e?.response?.data?.detail || e?.message || 'Помилка';

const UsersModerationPanel = () => {
	const [q, setQ] = useState('');
	const [blocked, setBlocked] = useState('');
	const [role, setRole] = useState('');
	const [page, setPage] = useState(1);
	const [data, setData] = useState({ items: [], total: 0, limit: 50 });
	const [selected, setSelected] = useState(null);
	const [reason, setReason] = useState('');
	const [msg, setMsg] = useState('');
	const [busy, setBusy] = useState(false);

	const load = async () => {
		try {
			const params = { q, page };
			if (blocked !== '') params.blocked = blocked;
			if (role) params.role = role;
			const { data } = await adminAPI.listUsers(params);
			setData(data);
		} catch (e) { setMsg(errMsg(e)); }
	};
	useEffect(() => { load(); }, [page, blocked, role]); // eslint-disable-line react-hooks/exhaustive-deps

	const open = async (id) => {
		setMsg(''); setReason('');
		try { const { data } = await adminAPI.getUser(id); setSelected(data); } catch (e) { setMsg(errMsg(e)); }
	};
	const act = async (fn) => {
		setBusy(true); setMsg('');
		try { await fn(); await open(selected.id); await load(); } catch (e) { setMsg(errMsg(e)); }
		setBusy(false);
	};
	const block = () => {
		if (reason.trim().length < 3) { setMsg('Вкажіть причину (мін. 3 символи)'); return; }
		if (!window.confirm(`Заблокувати користувача #${selected.id}? Угоди не змінюються автоматично.`)) return;
		act(() => adminAPI.blockUser(selected.id, reason.trim()));
	};
	const dealAction = (dealId, action) => {
		const labels = { allow: 'дозволити дії по угоді', disallow: 'заборонити дії по угоді', dispute: 'перевести угоду у спір' };
		if (!window.confirm(`Угода #${dealId}: ${labels[action]}?`)) return;
		act(() => adminAPI.dealBlockedParty(dealId, action, action === 'dispute' ? `Заблокований учасник: ${selected.blocked_reason || ''}` : undefined));
	};
	const pages = Math.max(1, Math.ceil((data.total || 0) / (data.limit || 50)));

	return (
		<div className='space-y-4'>
			<h2 className='text-2xl font-bold text-gray-800 dark:text-gray-100'>Користувачі</h2>
			<div className='flex flex-wrap gap-2'>
				<input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && (setPage(1), load())}
					placeholder='Пошук: id, @username, ім’я, email, telegram id' className='flex-1 min-w-[240px] border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2 text-sm bg-white dark:bg-slate-700 dark:text-gray-200' />
				<select value={blocked} onChange={e => { setBlocked(e.target.value); setPage(1); }} className='border rounded-xl px-3 py-2 text-sm bg-white dark:bg-slate-700 dark:text-gray-200 dark:border-slate-600'>
					<option value=''>Усі</option><option value='true'>Заблоковані</option><option value='false'>Активні</option>
				</select>
				<select value={role} onChange={e => { setRole(e.target.value); setPage(1); }} className='border rounded-xl px-3 py-2 text-sm bg-white dark:bg-slate-700 dark:text-gray-200 dark:border-slate-600'>
					<option value=''>Усі ролі</option><option value='user'>user</option><option value='moderator'>moderator</option><option value='admin'>admin</option>
				</select>
				<button onClick={() => { setPage(1); load(); }} className='bg-[#3498db] text-white px-4 py-2 rounded-xl text-sm font-semibold'>Знайти</button>
			</div>
			{msg && <div className='text-sm text-red-600'>{msg}</div>}
			<div className='grid lg:grid-cols-2 gap-4'>
				<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 divide-y dark:divide-slate-700'>
					{data.items.map(u => (
						<button key={u.id} onClick={() => open(u.id)} className={`w-full text-left px-4 py-3 text-sm hover:bg-gray-50 dark:hover:bg-slate-700 ${selected?.id === u.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}>
							<span className='font-semibold text-gray-800 dark:text-gray-100'>#{u.id} {u.first_name}</span>
							{u.username && <span className='text-gray-500'> @{u.username}</span>}
							<span className='ml-2 text-xs text-gray-400'>{u.role}</span>
							{u.is_blocked && <span className='ml-2 text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded'>заблоковано</span>}
						</button>
					))}
					{!data.items.length && <div className='p-4 text-sm text-gray-400'>Нічого не знайдено</div>}
					<div className='flex justify-between items-center px-4 py-2 text-sm text-gray-500'>
						<button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className='disabled:opacity-40'>←</button>
						<span>{page} / {pages} · {data.total}</span>
						<button disabled={page >= pages} onClick={() => setPage(p => p + 1)} className='disabled:opacity-40'>→</button>
					</div>
				</div>
				{selected && (
					<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-5 space-y-3 text-sm text-gray-700 dark:text-gray-300'>
						<div className='text-lg font-bold text-gray-800 dark:text-gray-100'>#{selected.id} {selected.first_name} {selected.username && `@${selected.username}`}</div>
						<div>Роль: {selected.role} · TG: {selected.telegram_id || '—'} · {selected.email || ''}</div>
						{selected.is_blocked ? (
							<div className='rounded-xl bg-red-50 dark:bg-red-900/20 p-3'>
								<div><b>Заблоковано</b> {selected.blocked_at && new Date(selected.blocked_at + 'Z').toLocaleString()}</div>
								<div>Причина: {selected.blocked_reason}</div>
								<button disabled={busy} onClick={() => window.confirm('Розблокувати?') && act(() => adminAPI.unblockUser(selected.id))} className='mt-2 bg-[#27ae60] text-white px-4 py-2 rounded-xl font-semibold disabled:opacity-50'>Розблокувати</button>
							</div>
						) : (
							<div className='flex gap-2'>
								<input value={reason} onChange={e => setReason(e.target.value)} placeholder='Причина блокування (обов’язково)' className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-3 py-2 bg-white dark:bg-slate-700' />
								<button disabled={busy} onClick={block} className='bg-red-500 text-white px-4 py-2 rounded-xl font-semibold disabled:opacity-50'>Заблокувати</button>
							</div>
						)}
						<div>
							<div className='font-semibold mb-1'>Активні угоди ({selected.active_deals?.length || 0})</div>
							{(selected.active_deals || []).map(d => (
								<div key={d.deal_id} className='border border-gray-100 dark:border-slate-700 rounded-xl p-3 mb-2'>
									<div>
										<a href={'/deal/' + d.deal_id} target='_blank' rel='noopener noreferrer' className='text-[#3498db] font-semibold'>#{d.deal_id}</a>
										{' '}{d.role === 'buyer' ? 'покупець' : 'продавець'} · {d.status} · {fmtUsdt(d.amount_usdt)} USDT{d.funded ? ' (в ескроу)' : ''}
										{d.blocked_party_allowed && <span className='ml-2 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded'>дії дозволено</span>}
									</div>
									{d.status === 'payout_in_progress' && <div className='text-xs text-gray-500 mt-1'>Виплата в процесі — не переривається.</div>}
									{selected.is_blocked && d.status !== 'payout_in_progress' && (
										<div className='flex flex-wrap gap-2 mt-2'>
											{d.blocked_party_allowed
												? <button disabled={busy} onClick={() => dealAction(d.deal_id, 'disallow')} className='bg-gray-200 dark:bg-slate-600 px-3 py-1.5 rounded-lg text-xs font-semibold'>Заборонити дії</button>
												: <button disabled={busy} onClick={() => dealAction(d.deal_id, 'allow')} className='bg-[#27ae60] text-white px-3 py-1.5 rounded-lg text-xs font-semibold'>Дозволити завершити угоду</button>}
											{['paid', 'channel_transferring', 'awaiting_payout'].includes(d.status) && (
												<button disabled={busy} onClick={() => dealAction(d.deal_id, 'dispute')} className='bg-orange-500 text-white px-3 py-1.5 rounded-lg text-xs font-semibold'>У спір (рішення адміна)</button>
											)}
											{!d.funded && <span className='text-xs text-gray-500 self-center'>Не оплачена — скасуйте в розділі «Угоди».</span>}
										</div>
									)}
								</div>
							))}
						</div>
					</div>
				)}
			</div>
		</div>
	);
};

export default UsersModerationPanel;
