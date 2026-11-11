import { useEffect, useState } from 'react';
import { fmtUsdt } from '../../utils/money';
import { offerBounds, validateOfferAmount } from '../../utils/offerAmount';
import '../Services/topGlow.css';

const PriceOfferModal = ({ channel, open, onClose, onSubmit, busy, error }) => {
	const bounds = channel ? offerBounds(channel.price) : null;
	const [amount, setAmount] = useState('');
	const [comment, setComment] = useState('');
	const [localError, setLocalError] = useState(null);

	useEffect(() => {
		if (open) {
			setAmount('');
			setComment('');
			setLocalError(null);
		}
	}, [open, channel?.id]);

	if (!open || !channel) return null;

	const submit = (e) => {
		e?.preventDefault?.();
		const msg = validateOfferAmount(amount, channel.price);
		if (msg) { setLocalError(msg); return; }
		setLocalError(null);
		onSubmit({ amount_usdt: Number(amount), comment: comment.trim() || undefined });
	};

	return (
		<div
			onClick={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}
			className='fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm z-50 p-4'
			role='dialog'
			aria-modal='true'
			aria-labelledby='price-offer-title'
		>
			<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-2xl z-[51] mx-auto max-w-[420px] w-full overflow-hidden lot-top-glow'>
				<form onSubmit={submit} className='p-6 sm:p-7'>
					<p className='text-[11px] font-semibold uppercase tracking-wider text-accent mb-2'>Ваша пропозиція</p>
					<h2 id='price-offer-title' className='text-xl font-bold text-gray-900 dark:text-white leading-snug'>
						Запропонувати свою ціну
					</h2>
					<p className='text-sm text-gray-500 dark:text-gray-400 mt-2'>
						{channel.channel_name || 'Канал'} · ціна лота{' '}
						<span className='font-semibold text-gray-800 dark:text-white tabular-nums'>{fmtUsdt(channel.price)} USDT</span>.
						Сума має бути нижчою за ціну лота і не менше 50%. Продавець отримає пропозицію в боті та кабінеті. Публічна ціна не зміниться.
					</p>
					<label className='block mt-5 text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-1.5'>Сума, USDT</label>
					<input
						type='number'
						inputMode='decimal'
						step='0.01'
						min={bounds ? bounds.min : undefined}
						max={bounds ? bounds.max : undefined}
						value={amount}
						onChange={(e) => setAmount(e.target.value)}
						placeholder={bounds ? `від ${fmtUsdt(bounds.min)} до ${fmtUsdt(bounds.max)}` : ''}
						className='w-full border border-gray-200 dark:border-slate-600 dark:bg-slate-700 rounded-xl px-3 py-3 font-mono text-base tabular-nums text-gray-900 dark:text-white'
						autoFocus
						disabled={busy}
					/>
					<label className='block mt-4 text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-1.5'>Коментар (необовʼязково)</label>
					<textarea
						value={comment}
						onChange={(e) => setComment(e.target.value.slice(0, 300))}
						rows={3}
						maxLength={300}
						placeholder='Коротко, чому саме ця сума'
						className='w-full border border-gray-200 dark:border-slate-600 dark:bg-slate-700 rounded-xl px-3 py-2 text-sm text-gray-900 dark:text-white resize-none'
						disabled={busy}
					/>
					<p className='text-[11px] text-gray-400 mt-1 text-right'>{comment.length}/300</p>
					{(localError || error) && (
						<p className='mt-3 text-sm text-red-600 dark:text-red-400'>{localError || error}</p>
					)}
					<div className='mt-5 flex flex-col sm:flex-row gap-2'>
						<button
							type='submit'
							disabled={busy || !bounds}
							className='flex-1 font-bold bg-accent text-black py-3 rounded-xl shadow-lg shadow-accent/30 hover:brightness-110 transition-all disabled:opacity-50'
						>
							{busy ? 'Надсилаємо…' : 'Надіслати пропозицію'}
						</button>
						<button
							type='button'
							disabled={busy}
							onClick={onClose}
							className='sm:w-36 font-semibold py-3 rounded-xl border border-gray-200 dark:border-slate-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-slate-700 disabled:opacity-50'
						>
							Скасувати
						</button>
					</div>
				</form>
			</div>
		</div>
	);
};

export default PriceOfferModal;
