import { useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { adminAPI } from '../../services/api';

const err = (e) => e?.response?.data?.detail || e?.message || 'Помилка';
const fmt = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));
const when = (iso) => (iso ? new Date(iso).toLocaleString() : '—');
const card = 'bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-5 text-sm text-gray-700 dark:text-gray-300';
const short = (h) => (h ? `${h.slice(0, 8)}…${h.slice(-6)}` : '—');

const LEVEL = {
	ok: { text: 'OK', cls: 'bg-green-100 text-green-700' },
	warning: { text: 'Мало газу', cls: 'bg-yellow-100 text-yellow-800' },
	critical: { text: 'КРИТИЧНО', cls: 'bg-red-100 text-red-700' },
	unknown: { text: 'Невідомо', cls: 'bg-gray-200 text-gray-700' },
};

const Sparkline = ({ points }) => {
	const vals = points.filter(p => p.trx !== null);
	if (vals.length < 2) return <div className='text-xs text-gray-400'>Історія ще збирається (знімок раз на 15 хв)</div>;
	const W = 320, H = 60;
	const t0 = new Date(vals[0].at).getTime(), t1 = new Date(vals[vals.length - 1].at).getTime() || t0 + 1;
	const max = Math.max(...vals.map(p => p.trx)), min = Math.min(...vals.map(p => p.trx));
	const span = max - min || 1;
	const d = vals.map((p, i) => {
		const x = ((new Date(p.at).getTime() - t0) / (t1 - t0 || 1)) * W;
		const y = H - ((p.trx - min) / span) * (H - 4) - 2;
		return `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
	}).join(' ');
	return (
		<div>
			<svg viewBox={`0 0 ${W} ${H}`} className='w-full h-16'><path d={d} fill='none' stroke='#3498db' strokeWidth='2' /></svg>
			<div className='flex justify-between text-xs text-gray-400'><span>{fmt(min)} TRX</span><span>{fmt(max)} TRX</span></div>
		</div>
	);
};

export const GasCard = () => {
	const [st, setSt] = useState(null);
	const [days, setDays] = useState(7);
	const [e, setE] = useState('');
	const load = async (refresh = false) => {
		try { const { data } = await adminAPI.gas({ days, refresh }); setSt(data); setE(''); } catch (x) { setE(err(x)); }
	};
	useEffect(() => { load(); }, [days]); // eslint-disable-line react-hooks/exhaustive-deps
	if (!st) return <div className={card}>⛽ Газ master… {e && <span className='text-red-600'>{e}</span>}</div>;
	const lv = LEVEL[st.level] || LEVEL.unknown;
	return (
		<div className={card}>
			<div className='flex items-center justify-between mb-3'>
				<div className='font-bold text-gray-800 dark:text-gray-100'>⛽ Газ master-гаманця</div>
				<span className={`text-xs px-2 py-0.5 rounded font-semibold ${lv.cls}`}>{lv.text}</span>
			</div>
			<div className='flex gap-4'>
				{st.address && <div className='bg-white p-2 rounded-lg shrink-0'><QRCodeSVG value={st.address} size={96} /></div>}
				<div className='space-y-1 min-w-0'>
					<div className='font-mono text-xs break-all'>{st.address || 'адреса не налаштована'}
						{st.address && <button onClick={() => navigator.clipboard?.writeText(st.address)} className='ml-2 text-[#3498db]'>копіювати</button>}
					</div>
					<div><b className='text-lg'>{fmt(st.trx)} TRX</b> · енергія {st.energy_available ?? '—'} · bandwidth {st.bandwidth_available ?? '—'}</div>
					<div>Вистачить на ~<b>{st.payouts_covered_new ?? '—'}</b> виплат новому отримувачу (≈{fmt(st.cost_trx?.new_receiver, 1)} TRX), ~{st.payouts_covered_existing ?? '—'} існуючому (≈{fmt(st.cost_trx?.existing_holder, 1)} TRX)</div>
					{st.suggested_topup_trx > 0 && <div className='text-orange-600'>Рекомендовано поповнити ~{fmt(st.suggested_topup_trx, 0)} TRX (ціль {fmt(st.target_trx, 0)} TRX ≈ 10 виплат)</div>}
					<div className='text-xs text-gray-400'>Попередження &lt; {fmt(st.warning_threshold_trx, 0)} TRX, критично &lt; {fmt(st.critical_threshold_trx, 0)} TRX · відмов через газ за 24 год: {st.refused_prechecks_24h} · перевірено {when(st.checked_at)}</div>
				</div>
			</div>
			<div className='mt-3'>
				<div className='flex gap-2 mb-1 text-xs'>
					{[7, 30].map(d => <button key={d} onClick={() => setDays(d)} className={days === d ? 'font-bold text-[#3498db]' : 'text-gray-400'}>{d} днів</button>)}
					<button onClick={() => load(true)} className='ml-auto text-[#3498db]'>оновити</button>
				</div>
				<Sparkline points={st.history || []} />
			</div>
			<div className='text-xs text-gray-400 mt-2'>{st.note}</div>
		</div>
	);
};

export const SummaryCard = () => {
	const [s, setS] = useState(null);
	const [date, setDate] = useState('');
	const [e, setE] = useState('');
	const load = async () => { try { const { data } = await adminAPI.summary(date || undefined); setS(data); setE(''); } catch (x) { setE(err(x)); } };
	useEffect(() => { load(); }, [date]); // eslint-disable-line react-hooks/exhaustive-deps
	return (
		<div className={card}>
			<div className='flex items-center justify-between mb-3'>
				<div className='font-bold text-gray-800 dark:text-gray-100'>📊 Звіт за день {s && s.date}</div>
				<input type='date' value={date} onChange={ev => setDate(ev.target.value)} className='border rounded-lg px-2 py-1 text-xs bg-white dark:bg-slate-700 dark:border-slate-600' />
			</div>
			{e && <div className='text-red-600'>{e}</div>}
			{s && (
				<div className='space-y-1'>
					<div>Угоди: створено {s.deals.created}, оплачено {s.deals.paid}, завершено {s.deals.completed}, скасовано {s.deals.cancelled}</div>
					<div>Комісія: нарахована {fmt(s.fee_accrued_usdt)} USDT, зібрана {fmt(s.fee_collected_usdt)} USDT</div>
					{Object.entries(s.outgoing).map(([k, v]) => <div key={k}>{k}: {v.confirmed} ({fmt(v.amount_usdt)} USDT), невдалих {v.failed}</div>)}
					<div className='text-xs text-gray-400'>Зараз: pending tx {s.pending_outgoing_now}, payout_in_progress {s.payout_in_progress_now}, спорів {s.disputes_open_now}, заблокованих {s.blocked_users_now}. Автозвіт у Telegram щодня о 09:00 (Кишинів).</div>
				</div>
			)}
		</div>
	);
};

const TxLink = ({ tx }) => (tx.tronscan_url
	? <a href={tx.tronscan_url} target='_blank' rel='noopener noreferrer' className='font-mono text-[#3498db]'>{short(tx.tx_hash)}</a>
	: <span className='text-gray-400'>—</span>);

export const TransactionsPanel = () => {
	const [f, setF] = useState({ type: '', status: '', deal_id: '', address: '', date_from: '', date_to: '', receipt_status: '' });
	const [page, setPage] = useState(1);
	const [data, setData] = useState({ items: [], total: 0, limit: 50 });
	const [e, setE] = useState('');
	const params = () => Object.fromEntries(Object.entries({ ...f, page }).filter(([, v]) => v !== '' && v !== null));
	const load = async () => { try { const { data } = await adminAPI.transactions(params()); setData(data); setE(''); } catch (x) { setE(err(x)); } };
	useEffect(() => { load(); }, [page]); // eslint-disable-line react-hooks/exhaustive-deps
	const exportCsv = async () => {
		try {
			const { data } = await adminAPI.transactionsCsv(params());
			const url = URL.createObjectURL(data);
			const a = document.createElement('a'); a.href = url; a.download = 'transactions.csv'; a.click(); URL.revokeObjectURL(url);
		} catch (x) { setE(err(x)); }
	};
	const inp = 'border border-gray-200 dark:border-slate-600 rounded-xl px-3 py-2 text-sm bg-white dark:bg-slate-700 dark:text-gray-200';
	const set = (k) => (ev) => setF(p => ({ ...p, [k]: ev.target.value }));
	const pages = Math.max(1, Math.ceil((data.total || 0) / (data.limit || 50)));
	return (
		<div className='space-y-4'>
			<h2 className='text-2xl font-bold text-gray-800 dark:text-gray-100'>Транзакції</h2>
			<div className='flex flex-wrap gap-2'>
				<select value={f.type} onChange={set('type')} className={inp}><option value=''>Усі типи</option>{['deposit', 'release', 'refund', 'fee_collection', 'sweep', 'overpay_refund'].map(t => <option key={t}>{t}</option>)}</select>
				<select value={f.status} onChange={set('status')} className={inp}><option value=''>Усі статуси</option>{['pending', 'confirmed', 'failed'].map(t => <option key={t}>{t}</option>)}</select>
				<input value={f.deal_id} onChange={set('deal_id')} placeholder='Угода #' className={inp + ' w-24'} />
				<input value={f.address} onChange={set('address')} placeholder='Адреса або tx hash' className={inp + ' flex-1 min-w-[200px]'} />
				<input value={f.receipt_status} onChange={set('receipt_status')} placeholder='receipt (SUCCESS…)' className={inp + ' w-36'} />
				<input type='date' value={f.date_from} onChange={set('date_from')} className={inp} />
				<input type='date' value={f.date_to} onChange={set('date_to')} className={inp} />
				<button onClick={() => { setPage(1); load(); }} className='bg-[#3498db] text-white px-4 py-2 rounded-xl text-sm font-semibold'>Фільтр</button>
				<button onClick={exportCsv} className='bg-gray-100 dark:bg-slate-700 px-4 py-2 rounded-xl text-sm font-semibold'>CSV</button>
			</div>
			{e && <div className='text-sm text-red-600'>{e}</div>}
			<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 overflow-x-auto'>
				<table className='w-full text-sm text-gray-700 dark:text-gray-300'>
					<thead><tr className='text-left text-xs text-gray-400 uppercase'>
						<th className='p-3'>#</th><th className='p-3'>Угода</th><th className='p-3'>Тип</th><th className='p-3'>Статус</th><th className='p-3'>Сума</th><th className='p-3'>Куди</th><th className='p-3'>TX</th><th className='p-3'>Квитанція</th><th className='p-3'>Створено</th>
					</tr></thead>
					<tbody>{data.items.map(t => (
						<tr key={t.id} className='border-t border-gray-100 dark:border-slate-700'>
							<td className='p-3'>{t.id}</td>
							<td className='p-3'><a href={'/deal/' + t.deal_id} target='_blank' rel='noopener noreferrer' className='text-[#3498db]'>#{t.deal_id}</a></td>
							<td className='p-3'>{t.type}</td><td className='p-3'>{t.status}{t.stage ? ` · ${t.stage}` : ''}</td>
							<td className='p-3'>{fmt(t.amount, 6)}</td>
							<td className='p-3 font-mono text-xs'>{short(t.to_address)}</td>
							<td className='p-3'><TxLink tx={t} /></td>
							<td className='p-3 text-xs'>{t.receipt_status || '—'}{t.receipt_reason ? ` (${t.receipt_reason})` : ''}</td>
							<td className='p-3 whitespace-nowrap text-xs'>{when(t.created_at)}</td>
						</tr>))}</tbody>
				</table>
				{!data.items.length && <div className='p-4 text-sm text-gray-400'>Нічого не знайдено</div>}
			</div>
			<div className='flex justify-between text-sm text-gray-500'>
				<button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className='disabled:opacity-40'>←</button>
				<span>{page} / {pages} · {data.total}</span>
				<button disabled={page >= pages} onClick={() => setPage(p => p + 1)} className='disabled:opacity-40'>→</button>
			</div>
		</div>
	);
};

export const PayoutQueuePanel = () => {
	const [q, setQ] = useState(null);
	const [msg, setMsg] = useState('');
	const [busy, setBusy] = useState(null);
	const load = async () => { try { const { data } = await adminAPI.payoutQueue(); setQ(data); } catch (x) { setMsg(err(x)); } };
	useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);
	const recheck = async (id) => {
		setBusy(id); setMsg('');
		try { const { data } = await adminAPI.recheckTx(id); setMsg(`TX #${id}: квитанція ${data.receipt}, результат ${data.outcome}`); } catch (x) { setMsg(err(x)); }
		setBusy(null); load();
	};
	const markFailed = async (id) => {
		const note = window.prompt(`TX #${id}: позначити як failed (не знайдено в мережі)? Повтор виплати НЕ відправляється. Вкажіть причину:`);
		if (!note || note.trim().length < 3) return;
		setBusy(id); setMsg('');
		try { const { data } = await adminAPI.markTxFailed(id, note.trim()); setMsg(`TX #${id}: ${data.outcome}, угода → ${data.deal_status}`); } catch (x) { setMsg(err(x)); }
		setBusy(null); load();
	};
	const Group = ({ title, rows, actions }) => (
		<div className={card}>
			<div className='font-bold mb-2 text-gray-800 dark:text-gray-100'>{title} ({rows.length})</div>
			{!rows.length && <div className='text-gray-400'>—</div>}
			{rows.map(t => (
				<div key={t.id} className='flex flex-wrap items-center gap-3 py-2 border-t border-gray-100 dark:border-slate-700'>
					<span>#{t.id}</span>
					<a href={'/deal/' + t.deal_id} target='_blank' rel='noopener noreferrer' className='text-[#3498db]'>угода #{t.deal_id}</a>
					<span>{t.type}</span><span>{fmt(t.amount, 6)} USDT</span><TxLink tx={t} />
					<span className='text-xs text-gray-400'>{t.receipt_status || ''} {t.receipt_reason || ''} · {when(t.broadcast_at || t.created_at)}</span>
					{actions && (
						<span className='ml-auto flex gap-2'>
							<button disabled={busy === t.id} onClick={() => recheck(t.id)} className='bg-[#3498db] text-white px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50'>Перевірити квитанцію</button>
							{t.stage === 'stale' && <button disabled={busy === t.id} onClick={() => markFailed(t.id)} className='bg-red-500 text-white px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50'>Позначити failed</button>}
						</span>
					)}
				</div>
			))}
		</div>
	);
	return (
		<div className='space-y-4'>
			<h2 className='text-2xl font-bold text-gray-800 dark:text-gray-100'>Черга виплат</h2>
			<div className='text-xs text-gray-500'>Повторна відправка недоступна навмисно. «Позначити failed» дозволено лише для застарілих транзакцій, яких немає в мережі, і лише якщо escrow досі містить усю суму.</div>
			{msg && <div className='text-sm text-gray-700 dark:text-gray-300'>{msg}</div>}
			{q ? (
				<>
					<Group title='У черзі' rows={q.queued} />
					<Group title='Відправлені (очікують квитанцію)' rows={q.broadcast} actions />
					<Group title='Застарілі > 10 хв' rows={q.stale} actions />
					<Group title='Нещодавно невдалі' rows={q.recent_failed} />
				</>
			) : <div className='text-gray-400'>Завантаження…</div>}
		</div>
	);
};

export const EscrowOverview = () => {
	const [d, setD] = useState(null);
	const [e, setE] = useState('');
	const load = async (refresh = false) => { try { const { data } = await adminAPI.escrowOverview(refresh); setD(data); setE(''); } catch (x) { setE(err(x)); } };
	useEffect(() => { load(); }, []);
	const OP = { awaiting_address: 'чекає адресу', queued: 'в черзі', failed: 'НЕ ВИКОНАНО', done: 'повернено' };
	const retryOverpay = async (i) => {
		if (!window.confirm(`Повторити повернення переплати ${fmt(i.overpay_usdt, 6)} USDT по угоді #${i.deal_id} на адресу ${i.overpay_refund_address}?\n\nПереказ буде поставлено в чергу worker-а (одна спроба, без автоповторів).`)) return;
		try { const { data } = await adminAPI.retryOverpayRefund(i.deal_id); alert(`Повернення ${data.amount_usdt} USDT поставлено в чергу (tx #${data.transaction_id}).`); load(); }
		catch (x) { alert(err(x)); load(); }
	};
	const FEE = { collectable: 'можна зібрати', collecting: 'збирається', collected: 'зібрано', not_collectable: 'не збирається (до 0026)' };
	return (
		<div className={card + ' mb-6'}>
			<div className='flex items-center justify-between mb-3'>
				<div className='font-bold text-gray-800 dark:text-gray-100'>Звірка ескроу</div>
				<button onClick={() => load(true)} className='text-[#3498db] text-xs'>оновити</button>
			</div>
			{e && <div className='text-red-600'>{e}</div>}
			{d && (
				<>
					<div className='grid grid-cols-2 lg:grid-cols-4 gap-2 mb-3'>
						<div>Нараховано: <b>{fmt(d.totals.accrued)}</b></div>
						<div>Зібрано: <b>{fmt(d.totals.collected)}</b></div>
						<div>Можна зібрати: <b>{fmt(d.totals.collectable)}</b></div>
						<div>Legacy (не збирається): <b>{fmt(d.totals.not_collectable_legacy)}</b></div>
						<div>В активних ескроу: <b>{fmt(d.totals.held_active)}</b></div>
						<div>Залишки на скасованих: <b>{fmt(d.totals.stray_cancelled)}</b></div>
						<div>Невідомий баланс: <b>{d.totals.unknown_wallets}</b></div>
						<div>Переплати повернено: <b>{fmt(d.totals.overpay_refunded)}</b></div>
						<div>Переплати до повернення: <b>{fmt(d.totals.overpay_open)}</b>{d.totals.overpay_failed ? <span className='text-red-600'> (невдалих: {d.totals.overpay_failed})</span> : null}</div>
						<div className='text-xs text-gray-400'>баланси: {when(d.balances_checked_at)}</div>
					</div>
					<div className='overflow-x-auto'>
						<table className='w-full text-xs'>
							<thead><tr className='text-left text-gray-400 uppercase'><th className='p-2'>Угода</th><th className='p-2'>Статус</th><th className='p-2'>Факт USDT</th><th className='p-2'>Очікувано</th><th className='p-2'>Комісія</th><th className='p-2'>Переплата</th><th className='p-2'></th></tr></thead>
							<tbody>{d.items.map(i => (
								<tr key={i.deal_id} className={`border-t border-gray-100 dark:border-slate-700 ${i.mismatch ? 'bg-red-50 dark:bg-red-900/20' : ''}`}>
									<td className='p-2'><a href={'/deal/' + i.deal_id} target='_blank' rel='noopener noreferrer' className='text-[#3498db]'>#{i.deal_id}</a></td>
									<td className='p-2'>{i.status}</td>
									<td className='p-2'>{i.live_usdt === null ? 'невідомо' : fmt(i.live_usdt, 6)}</td>
									<td className='p-2'>{i.expected_usdt === null ? '—' : fmt(i.expected_usdt, 6)}</td>
									<td className='p-2'>{i.fee_state ? `${fmt(i.service_fee)} · ${FEE[i.fee_state] || i.fee_state}` : '—'}</td>
									<td className='p-2'>{i.overpay_usdt ? (<>
										{fmt(i.overpay_usdt, 6)} · <span className={i.overpay_status === 'failed' ? 'text-red-600 font-semibold' : ''}>{OP[i.overpay_status] || i.overpay_status}</span>
										{i.overpay_tx?.tronscan_url && <> · <a href={i.overpay_tx.tronscan_url} target='_blank' rel='noopener noreferrer' className='text-[#3498db]'>{short(i.overpay_tx.tx_hash)}</a></>}
										{i.overpay_retry_allowed && <button onClick={() => retryOverpay(i)} className='ml-2 px-2 py-0.5 rounded bg-orange-500 text-white'>Повторити</button>}
									</>) : '—'}</td>
									<td className='p-2'>{i.mismatch && <span className='text-red-600 font-semibold'>розбіжність</span>}{i.stray && <span className='text-orange-600'>залишок (лише перегляд)</span>}</td>
								</tr>))}</tbody>
						</table>
					</div>
				</>
			)}
		</div>
	);
};
