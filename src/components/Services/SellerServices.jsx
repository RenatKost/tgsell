import { useEffect, useState } from 'react';
import { servicesAPI } from '../../services/api';
import { btnPrimary, btnSecondary } from '../Cabinet/ui';

let catalogCache = null;
const loadCatalog = () => {
	if (!catalogCache) catalogCache = servicesAPI.catalog().then((r) => r.data).catch(() => { catalogCache = null; return null; });
	return catalogCache;
};
const ICON = { top: '🚀', post: '📣', verified: '✅' };
const errText = (ex) => { const d = ex?.response?.data?.detail; return typeof d === 'string' ? d : 'Не вдалося створити заявку'; };

/** Paid services buttons for a seller's published lot (cabinet card). */
const SellerServices = ({ channel }) => {
	const [cat, setCat] = useState(null);
	const [pick, setPick] = useState(null);
	const [order, setOrder] = useState(null);
	const [err, setErr] = useState('');
	const [busy, setBusy] = useState(false);
	useEffect(() => { loadCatalog().then(setCat); }, []);
	if (channel.status !== 'approved' || !cat) return null;
	const items = cat.items.filter((i) => !(i.kind === 'top' && channel.is_top) && !(i.kind === 'verified' && channel.tgsell_verified));
	const close = () => { setPick(null); setOrder(null); setErr(''); };
	const buy = async () => {
		setBusy(true); setErr('');
		try { const r = await servicesAPI.order({ channel_id: channel.id, kind: pick.kind }); setOrder(r.data); }
		catch (ex) { setErr(errText(ex)); } finally { setBusy(false); }
	};
	return (
		<div className='px-4 sm:px-5 pb-4 sm:pb-5'>
			<p className='text-xs text-gray-500 dark:text-gray-400 mb-2'>Просування лота</p>
			<div className='flex flex-wrap gap-2'>
				{items.map((i) => (
					<button key={i.kind} type='button' onClick={() => setPick(i)} className={`${btnSecondary} text-xs`}>
						{ICON[i.kind]} {i.title} · {i.price_usdt} USDT
					</button>
				))}
			</div>
			{pick && (
				<div className='fixed inset-0 z-50 bg-black/60 flex items-end sm:items-center justify-center p-0 sm:p-4' onClick={close}>
					<div role='dialog' aria-modal='true' className='bg-white dark:bg-card w-full sm:max-w-md rounded-t-2xl sm:rounded-2xl p-5 space-y-3 border border-gray-200 dark:border-card-border' onClick={(e) => e.stopPropagation()}>
						<h3 className='text-lg font-bold text-gray-900 dark:text-white'>{ICON[pick.kind]} {pick.title}</h3>
						<p className='text-sm text-gray-600 dark:text-gray-300'>Лот: <b>{channel.channel_name}</b></p>
						<p className='text-sm text-gray-600 dark:text-gray-300'>{pick.terms}</p>
						{pick.kind === 'top' && !order && <p className='text-xs text-gray-400'>Вільних місць у Топі: {cat.top_slots_free}</p>}
						{!pick.refundable && <p className='text-xs font-semibold text-amber-600 dark:text-amber-400'>Оплата не повертається у разі відмови.</p>}
						<p className='text-2xl font-bold text-gray-900 dark:text-white'>{pick.price_usdt} USDT</p>
						{order ? (
							<div className='space-y-2'>
								<p className='text-sm text-gray-600 dark:text-gray-300'>Надішліть рівно <b>{order.price_usdt} USDT</b> (мережа TRC-20) на адресу:</p>
								<input readOnly value={order.escrow_wallet_address} onFocus={(e) => e.target.select()} className='w-full text-xs bg-gray-50 dark:bg-slate-900 border border-gray-200 dark:border-card-border rounded-xl px-3 py-2.5 text-gray-800 dark:text-gray-100' />
								<p className='text-xs text-gray-400'>Оплату буде зараховано автоматично протягом кількох хвилин. Неоплачена заявка скасовується через 24 год.</p>
							</div>
						) : err ? <p className='text-sm text-red-500'>{err}</p> : null}
						<div className='flex gap-2 justify-end'>
							<button type='button' className={btnSecondary} onClick={close}>{order ? 'Готово' : 'Скасувати'}</button>
							{!order && <button type='button' className={btnPrimary} onClick={buy} disabled={busy}>{busy ? 'Створюємо…' : 'Оплатити USDT'}</button>}
						</div>
					</div>
				</div>
			)}
		</div>
	);
};

export default SellerServices;
