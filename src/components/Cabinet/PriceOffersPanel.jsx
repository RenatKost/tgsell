import { useCallback, useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { priceOffersAPI } from '../../services/api';
import { fmtUsdt } from '../../utils/money';
import { formatKyivDateTime } from '../../utils/topFunnel';
import { btnPrimary, btnSecondary, btnDanger, Badge, surface } from './ui';

const STATUS_UA = {
	pending: { text: 'Очікує', tone: 'blue' },
	accepted: { text: 'Прийнята', tone: 'green' },
	declined: { text: 'Відхилена', tone: 'gray' },
	expired: { text: 'Закінчилась', tone: 'gray' },
	closed: { text: 'Закрита', tone: 'gray' },
};

const PriceOffersPanel = ({ role, highlight, onChanged }) => {
	const [items, setItems] = useState([]);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState(null);
	const [busyId, setBusyId] = useState(null);

	const load = useCallback(async () => {
		setError(null);
		try {
			const { data } = role === 'seller'
				? await priceOffersAPI.inbox()
				: await priceOffersAPI.mine();
			setItems(data || []);
		} catch (err) {
			setError(err.response?.data?.detail || 'Не вдалося завантажити пропозиції');
		} finally {
			setLoading(false);
		}
	}, [role]);

	useEffect(() => { load(); }, [load]);

	const act = async (id, fn) => {
		setBusyId(id);
		try {
			await fn(id);
			await load();
			onChanged?.();
		} catch (err) {
			setError(err.response?.data?.detail || 'Помилка');
		} finally {
			setBusyId(null);
		}
	};

	const pending = items.filter((o) => o.status === 'pending');
	const rest = items.filter((o) => o.status !== 'pending');
	const show = role === 'seller' ? [...pending, ...rest.slice(0, 8)] : items.slice(0, 12);
	if (loading) return null;
	if (!show.length && !highlight) return null;

	return (
		<div id='price-offers' className={`${surface} esc-card p-4 sm:p-5 mb-6 ${highlight ? 'ring-2 ring-accent/40' : ''}`}>
			<div className='flex items-start justify-between gap-3 mb-3'>
				<div>
					<p className='text-[11px] font-semibold uppercase tracking-wider text-accent'>Пропозиції ціни</p>
					<h2 className='text-lg font-bold text-gray-900 dark:text-white'>
						{role === 'seller' ? 'Запропоновані вам суми' : 'Мої пропозиції'}
					</h2>
					<p className='text-sm text-gray-500 dark:text-gray-400 mt-0.5'>
						{role === 'seller'
							? 'Чужі пропозиції бачите лише ви. Прийняття не змінює публічну ціну лота. Перша підтверджена покупцем угода забирає лот; інші пропозиції закриються автоматично.'
							: 'Якщо продавець прийме пропозицію, угоду потрібно підтвердити окремо протягом 48 годин.'}
					</p>
				</div>
				{pending.length > 0 && <Badge tone='blue'>{pending.length}</Badge>}
			</div>
			{error && <p className='text-sm text-red-600 dark:text-red-400 mb-3'>{error}</p>}
			{!show.length ? (
				<p className='text-sm text-gray-500'>Поки немає пропозицій.</p>
			) : (
				<ul className='space-y-3'>
					{show.map((o) => {
						const st = STATUS_UA[o.status] || { text: o.status, tone: 'gray' };
						return (
							<li key={o.id} className='rounded-xl border border-gray-100 dark:border-slate-700 p-3 sm:p-4'>
								<div className='flex flex-col sm:flex-row sm:items-start justify-between gap-2'>
									<div className='min-w-0'>
										<p className='font-semibold text-gray-900 dark:text-white truncate'>
											{o.channel_name || `Лот #${o.channel_id}`}
										</p>
										<p className='text-sm text-gray-500 mt-0.5'>
											{role === 'seller' && o.buyer_name ? `${o.buyer_name} · ` : ''}
											<span className='font-bold tabular-nums text-gray-900 dark:text-accent'>{fmtUsdt(o.amount_usdt)} USDT</span>
											{o.lot_price_usdt != null && (
												<span> з {fmtUsdt(o.lot_price_usdt)} USDT</span>
											)}
										</p>
										{o.comment && (
											<p className='text-sm text-gray-600 dark:text-gray-300 mt-1 break-words'>«{o.comment}»</p>
										)}
										<p className='text-xs text-gray-400 mt-1'>
											до {formatKyivDateTime(o.expires_at) || '—'}
										</p>
									</div>
									<Badge tone={st.tone}>{st.text}</Badge>
								</div>
								<div className='mt-3 flex flex-col sm:flex-row gap-2'>
									{role === 'seller' && o.status === 'pending' && (
										<>
											<button type='button' disabled={busyId === o.id} className={`${btnPrimary} w-full sm:w-auto`}
												onClick={() => act(o.id, priceOffersAPI.accept)}>
												{busyId === o.id ? '…' : 'Прийняти'}
											</button>
											<button type='button' disabled={busyId === o.id} className={`${btnDanger} w-full sm:w-auto`}
												onClick={() => act(o.id, priceOffersAPI.decline)}>
												Відхилити
											</button>
										</>
									)}
									{role === 'buyer' && o.can_create_deal && (
										<NavLink to={`/channel/${o.channel_id}?offer=${o.id}`} className={`${btnPrimary} w-full sm:w-auto text-center`}>
											Підтвердити угоду
										</NavLink>
									)}
									<NavLink to={`/channel/${o.channel_id}`} className={`${btnSecondary} w-full sm:w-auto text-center`}>
										До лота
									</NavLink>
								</div>
							</li>
						);
					})}
				</ul>
			)}
		</div>
	);
};

export default PriceOffersPanel;
