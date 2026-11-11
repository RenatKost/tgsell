import { fmtUsdt } from '../../utils/money';
import '../Services/topGlow.css';

/**
 * Premium confirmation before POST /api/deals. The deal is created only when
 * the buyer presses «Підтвердити покупку» — never silently after login.
 */
const BuyConfirmModal = ({ channel, open, onClose, onConfirm, busy, error, amount, note }) => {
	if (!open || !channel) return null;
	return (
		<div
			onClick={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}
			className='fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm z-50 p-4'
			role='dialog'
			aria-modal='true'
			aria-labelledby='buy-confirm-title'
		>
			<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-2xl z-[51] mx-auto max-w-[420px] w-full overflow-hidden lot-top-glow'>
				<div className='p-6 sm:p-7'>
					<p className='text-[11px] font-semibold uppercase tracking-wider text-accent mb-2'>Підтвердження покупки</p>
					<h2 id='buy-confirm-title' className='text-xl font-bold text-gray-900 dark:text-white leading-snug'>
						{channel.channel_name || 'Канал'}
					</h2>
					<p className='text-sm text-gray-500 dark:text-gray-400 mt-2'>
						{note || 'Угода створюється на суму лота. Кошти підуть на адресу гаранта (ескроу) лише після підтвердження готовності обома сторонами.'}
					</p>
					<p className='mt-4 text-2xl font-bold text-gray-900 dark:text-white tabular-nums'>
						{fmtUsdt(amount != null ? amount : channel.price)} <span className='text-base font-semibold text-accent'>USDT</span>
					</p>
					{error && (
						<p className='mt-3 text-sm text-red-600 dark:text-red-400'>{error}</p>
					)}
					<div className='mt-6 flex flex-col sm:flex-row gap-2'>
						<button
							type='button'
							disabled={busy}
							onClick={onConfirm}
							className='flex-1 font-bold bg-accent text-black py-3 rounded-xl shadow-lg shadow-accent/30 hover:brightness-110 transition-all disabled:opacity-50'
						>
							{busy ? 'Створюємо угоду…' : 'Підтвердити покупку'}
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
				</div>
			</div>
		</div>
	);
};

export default BuyConfirmModal;
