import { useEffect, useState } from 'react';
import { servicesAPI } from '../../services/api';
import { btnPrimary, btnSecondary } from '../Cabinet/ui';

let catalogCache = null;
export const loadCatalog = () => {
	if (!catalogCache) catalogCache = servicesAPI.catalog().then((r) => r.data).catch(() => { catalogCache = null; return null; });
	return catalogCache;
};
export const useServicesCatalog = () => {
	const [cat, setCat] = useState(null);
	useEffect(() => { let on = true; loadCatalog().then((c) => on && setCat(c)); return () => { on = false; }; }, []);
	return cat;
};
export const SERVICE_ICON = { top: '🚀', post: '📣', verified: '✅' };
const errText = (ex) => { const d = ex?.response?.data?.detail; return typeof d === 'string' ? d : 'Не вдалося створити заявку'; };

/** Items still available for this lot (hide Top if already in Top, Verified if already verified). */
export const availableServices = (cat, channel) => (cat?.items || []).filter(
	(i) => !(i.kind === 'top' && channel?.is_top) && !(i.kind === 'verified' && channel?.tgsell_verified));

/**
 * Service picker + existing order flow (POST /services/orders → USDT TRC-20 address).
 * `initialKind` jumps straight to a service; otherwise the user picks from the list.
 */
const PromoteDialog = ({ channel, initialKind = null, onClose, onCabinet }) => {
	const cat = useServicesCatalog();
	const items = availableServices(cat, channel);
	const [kind, setKind] = useState(initialKind);
	const [order, setOrder] = useState(null);
	const [err, setErr] = useState('');
	const [busy, setBusy] = useState(false);
	const pick = items.find((i) => i.kind === kind) || null;
	const published = channel?.status === 'approved';

	useEffect(() => {
		const onKey = (e) => e.key === 'Escape' && onClose?.();
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	}, [onClose]);

	const buy = async () => {
		setBusy(true); setErr('');
		try { const r = await servicesAPI.order({ channel_id: channel.id, kind: pick.kind }); setOrder(r.data); }
		catch (ex) { setErr(errText(ex)); } finally { setBusy(false); }
	};

	return (
		<div className='fixed inset-0 z-[60] bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4' onClick={onClose}>
			<div role='dialog' aria-modal='true' aria-label='Просунути лот'
				className='bg-white dark:bg-card w-full sm:max-w-md max-h-[92vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl p-5 sm:p-6 space-y-4 border border-gray-200 dark:border-card-border text-left'
				onClick={(e) => e.stopPropagation()}>
				<div className='flex items-start justify-between gap-3'>
					<div className='min-w-0'>
						<h3 className='text-lg font-bold text-gray-900 dark:text-white'>{pick ? `${SERVICE_ICON[pick.kind]} ${pick.title}` : '🚀 Просунути лот'}</h3>
						<p className='text-sm text-gray-500 dark:text-gray-400 mt-0.5 truncate'>Лот: <b className='text-gray-800 dark:text-gray-200'>{channel?.channel_name}</b></p>
					</div>
					<button type='button' onClick={onClose} aria-label='Закрити' className='w-9 h-9 shrink-0 rounded-lg text-gray-400 hover:text-white hover:bg-white/5 text-xl leading-none'>×</button>
				</div>

				{!cat ? (
					<p className='text-sm text-gray-400'>Завантажуємо послуги…</p>
				) : !pick ? (
					<div className='space-y-2'>
						{items.map((i) => (
							<button key={i.kind} type='button' onClick={() => setKind(i.kind)}
								className='w-full flex items-center gap-3 p-3.5 rounded-xl border border-gray-200 dark:border-card-border bg-gray-50 dark:bg-card-inner hover:border-accent transition-colors text-left'>
								<span className='text-2xl'>{SERVICE_ICON[i.kind]}</span>
								<span className='flex-1 min-w-0'>
									<span className='block font-semibold text-gray-900 dark:text-white text-sm'>{i.title}</span>
									<span className='block text-xs text-gray-500 dark:text-gray-400 line-clamp-2'>{i.terms}</span>
								</span>
								<span className='font-bold text-accent whitespace-nowrap tabular-nums'>{i.price_usdt} USDT</span>
							</button>
						))}
						{items.length === 0 && <p className='text-sm text-gray-400'>Усі послуги для цього лота вже активні.</p>}
					</div>
				) : (
					<>
						<p className='text-sm text-gray-600 dark:text-gray-300'>{pick.terms}</p>
						{pick.kind === 'top' && !order && <p className='text-xs text-gray-400'>Вільних місць у Топі: {cat.top_slots_free}</p>}
						{!pick.refundable && <p className='text-xs font-semibold text-amber-600 dark:text-amber-400'>Оплата не повертається у разі відмови.</p>}
						<p className='text-2xl font-bold text-gray-900 dark:text-white'>{pick.price_usdt} <span className='text-accent'>USDT</span></p>
						{order ? (
							<div className='space-y-2'>
								<p className='text-sm text-gray-600 dark:text-gray-300'>Надішліть рівно <b>{order.price_usdt} USDT</b> (мережа TRC-20) на адресу:</p>
								<input readOnly value={order.escrow_wallet_address} onFocus={(e) => e.target.select()} className='w-full text-xs bg-gray-50 dark:bg-slate-900 border border-gray-200 dark:border-card-border rounded-xl px-3 py-2.5 text-gray-800 dark:text-gray-100' />
								<p className='text-xs text-gray-400'>Оплату буде зараховано автоматично протягом кількох хвилин. Неоплачена заявка скасовується через 24 год.</p>
							</div>
						) : !published ? (
							<p className='text-sm text-amber-600 dark:text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2.5'>
								Оплатити послугу можна одразу після модерації лота. Ми повідомимо, коли його схвалять, — кнопка «Просунути» буде на картці лота в кабінеті.
							</p>
						) : err ? <p className='text-sm text-red-500'>{err}</p> : null}
					</>
				)}

				<div className='flex flex-col-reverse sm:flex-row gap-2 sm:justify-end'>
					{pick && !order && !initialKind && <button type='button' className={btnSecondary} onClick={() => { setKind(null); setErr(''); }}>← Інші послуги</button>}
					<button type='button' className={btnSecondary} onClick={onClose}>{order ? 'Готово' : 'Закрити'}</button>
					{pick && !order && published && <button type='button' className={btnPrimary} onClick={buy} disabled={busy}>{busy ? 'Створюємо…' : 'Оплатити USDT'}</button>}
					{pick && !order && !published && onCabinet && <button type='button' className={btnPrimary} onClick={onCabinet}>До кабінету</button>}
				</div>
			</div>
		</div>
	);
};

export default PromoteDialog;
