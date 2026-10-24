import { useEffect, useState } from 'react';
import { servicesAPI } from '../../services/api';

const KINDS = [{ v: '', t: 'Всі' }, { v: 'top', t: 'Топ' }, { v: 'post', t: 'Пост у каналі' }, { v: 'verified', t: 'Перевірено TgSell' }];
const NEXT_LABEL = { in_review: 'В роботу', published: 'Опубліковано', verified: 'Поставити значок', rejected: 'Відмовити' };
const SETTINGS = [
	['service_price_top', 'Топ, USDT'], ['service_price_post', 'Пост, USDT'], ['service_price_verified', 'Перевірено, USDT'],
	['service_top_days', 'Топ, днів'], ['service_top_max_slots', 'Топ, місць'], ['service_payment_hours', 'Час на оплату, год'],
];
const box = 'bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-4';

const ServicesPanel = ({ isAdmin }) => {
	const [kind, setKind] = useState('');
	const [items, setItems] = useState([]);
	const [cfg, setCfg] = useState(null);
	const [err, setErr] = useState('');
	const load = async () => {
		try {
			const [o, s] = await Promise.all([servicesAPI.adminOrders({ kind: kind || undefined }), servicesAPI.adminSettings()]);
			setItems(o.data.items || []); setCfg(s.data); setErr('');
		} catch (e) { setErr(e?.response?.data?.detail || 'Помилка завантаження'); }
	};
	useEffect(() => { load(); }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps
	const move = async (id, status) => {
		const note = status === 'rejected' ? window.prompt('Причина відмови (бачить продавець)', '') : null;
		if (status === 'rejected' && note === null) return;
		try { await servicesAPI.adminSetStatus(id, status, note || null); load(); } catch (e) { alert(e?.response?.data?.detail || 'Помилка'); }
	};
	const save = async () => {
		try { const r = await servicesAPI.adminSaveSettings(cfg); setCfg(r.data); alert('Збережено'); } catch (e) { alert(e?.response?.data?.detail || 'Помилка'); }
	};
	return (
		<div className='space-y-6'>
			<h1 className='text-2xl font-bold text-gray-800 dark:text-white'>Платні послуги</h1>
			{err && <p className='text-red-500 text-sm'>{err}</p>}
			{cfg && (
				<div className={box}>
					<h2 className='font-bold text-gray-800 dark:text-white mb-3'>Ціни та ліміти</h2>
					<div className='grid grid-cols-2 lg:grid-cols-6 gap-3'>
						{SETTINGS.map(([k, l]) => (
							<label key={k} className='text-xs text-gray-400'>{l}
								<input type='number' step='any' disabled={!isAdmin} value={cfg[k] ?? ''} onChange={(e) => setCfg({ ...cfg, [k]: e.target.value === '' ? '' : Number(e.target.value) })}
									className='mt-1 w-full rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-800 dark:text-gray-100' />
							</label>
						))}
					</div>
					{isAdmin && <button onClick={save} className='mt-3 bg-[#3498db] text-white rounded-xl px-4 py-2 text-sm font-semibold'>Зберегти</button>}
				</div>
			)}
			<div className='flex flex-wrap gap-2'>
				{KINDS.map((k) => <button key={k.v} onClick={() => setKind(k.v)} className={`px-3 py-1.5 rounded-xl text-sm ${kind === k.v ? 'bg-[#3498db] text-white' : 'bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-gray-300'}`}>{k.t}</button>)}
			</div>
			<div className='space-y-3'>
				{items.length === 0 && <p className='text-gray-400 text-sm'>Заявок немає</p>}
				{items.map((o) => (
					<div key={o.id} className={`${box} flex flex-col md:flex-row md:items-center gap-3 justify-between`}>
						<div className='min-w-0'>
							<div className='font-semibold text-gray-800 dark:text-gray-100'>#{o.id} · {o.title}</div>
							<div className='text-sm text-gray-500 dark:text-gray-400'><a className='text-[#3498db]' href={`/channel/${o.channel_id}`} target='_blank' rel='noreferrer'>{o.channel_name}</a> · {o.price_usdt} USDT · {o.status_label}{o.active_until ? ` · до ${new Date(o.active_until + 'Z').toLocaleDateString('uk-UA')}` : ''}</div>
							{o.admin_note && <div className='text-xs text-gray-400 mt-1'>Примітка: {o.admin_note}</div>}
						</div>
						<div className='flex flex-wrap gap-2'>
							{(o.next || []).map((s) => (
								<button key={s} onClick={() => move(o.id, s)} className={`px-3 py-2 rounded-xl text-sm font-semibold ${s === 'rejected' ? 'bg-red-500/10 text-red-500' : 'bg-green-500/10 text-green-600'}`}>{NEXT_LABEL[s] || s}</button>
							))}
						</div>
					</div>
				))}
			</div>
		</div>
	);
};

export default ServicesPanel;
