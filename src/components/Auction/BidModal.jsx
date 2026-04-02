import { useState, useEffect } from 'react';
import { auctionsAPI } from '../../services/api';
import { useAuth } from '../../context/AppContext';

const BidModal = ({ auction, onClose, onSuccess }) => {
	const { isAuthenticated } = useAuth();
	const [visible, setVisible] = useState(false);
	const [amount, setAmount] = useState('');
	const [error, setError] = useState('');
	const [loading, setLoading] = useState(false);

	const minBid = auction.current_price + auction.bid_step;

	useEffect(() => {
		requestAnimationFrame(() => setVisible(true));
		setAmount(String(minBid));
	}, []);

	const handleClose = () => {
		setVisible(false);
		setTimeout(onClose, 250);
	};

	const handleBid = async () => {
		if (!isAuthenticated) {
			setError('Увійдіть для ставки');
			return;
		}
		const val = parseFloat(amount);
		if (!val || val < minBid) {
			setError(`Мінімальна ставка: ${minBid} USDT`);
			return;
		}
		setError('');
		setLoading(true);
		try {
			await auctionsAPI.bid(auction.id, { amount: val });
			setVisible(false);
			setTimeout(onSuccess, 250);
		} catch (err) {
			setError(err.response?.data?.detail || 'Помилка ставки');
		} finally {
			setLoading(false);
		}
	};

	const quickSteps = [1, 2, 5].map((mult) => ({
		label: `+${mult * auction.bid_step}`,
		value: minBid + (mult - 1) * auction.bid_step,
	}));

	return (
		<div
			className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-300 ${
				visible ? 'bg-black/50 backdrop-blur-sm' : 'bg-black/0'
			}`}
			onClick={handleClose}
		>
			<div
				className={`bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full overflow-hidden transition-all duration-300 ${
					visible ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-4'
				}`}
				onClick={(e) => e.stopPropagation()}
			>
				{/* Header */}
				<div className='bg-gradient-to-r from-orange-500 to-red-500 px-6 py-5 text-white'>
					<h3 className='text-lg font-bold'>Зробити ставку</h3>
					<p className='text-sm text-white/80 mt-1'>
						{auction.channel_name || 'Канал'}
					</p>
				</div>

				<div className='p-6'>
					{/* Current price info */}
					<div className='flex items-center justify-between mb-5'>
						<div>
							<div className='text-xs text-gray-500 dark:text-gray-400'>Поточна ціна</div>
							<div className='text-xl font-bold text-gray-900 dark:text-white'>
								{auction.current_price.toLocaleString()} USDT
							</div>
						</div>
						<div className='text-right'>
							<div className='text-xs text-gray-500 dark:text-gray-400'>Мін. ставка</div>
							<div className='text-xl font-bold text-orange-500'>
								{minBid.toLocaleString()} USDT
							</div>
						</div>
					</div>

					{/* Quick buttons */}
					<div className='grid grid-cols-3 gap-2 mb-4'>
						{quickSteps.map((qs) => (
							<button
								key={qs.label}
								type='button'
								onClick={() => setAmount(String(qs.value))}
								className={`py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
									parseFloat(amount) === qs.value
										? 'bg-orange-500 text-white shadow-md'
										: 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300 hover:bg-orange-100 dark:hover:bg-orange-900/20'
								}`}
							>
								{qs.label} USDT
							</button>
						))}
					</div>

					{/* Custom amount */}
					<div className='relative mb-4'>
						<input
							type='number'
							value={amount}
							onChange={(e) => setAmount(e.target.value)}
							className='w-full border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-3.5 text-lg font-semibold bg-gray-50/50 dark:bg-slate-700/50 dark:text-white focus:border-orange-400 focus:ring-4 focus:ring-orange-50 dark:focus:ring-orange-900/30 transition-all'
							placeholder={String(minBid)}
							min={minBid}
							step={auction.bid_step}
						/>
						<span className='absolute right-4 top-1/2 -translate-y-1/2 text-sm font-medium text-gray-400'>
							USDT
						</span>
					</div>

					{error && (
						<div className='flex items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800 text-red-600 dark:text-red-400 text-sm px-4 py-3 rounded-xl mb-4'>
							<svg className='w-4 h-4 flex-shrink-0' fill='currentColor' viewBox='0 0 20 20'>
								<path fillRule='evenodd' d='M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z' clipRule='evenodd' />
							</svg>
							{error}
						</div>
					)}

					{/* Actions */}
					<div className='flex gap-3'>
						<button
							type='button'
							onClick={handleClose}
							className='flex-1 py-3.5 rounded-xl text-sm font-semibold text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 transition-all'
						>
							Скасувати
						</button>
						<button
							type='button'
							onClick={handleBid}
							disabled={loading}
							className='flex-[2] py-3.5 rounded-xl text-sm font-semibold bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white shadow-md hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2'
						>
							{loading ? (
								<svg className='animate-spin w-5 h-5' fill='none' viewBox='0 0 24 24'>
									<circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4' />
									<path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z' />
								</svg>
							) : (
								<>🔥 Підтвердити ставку</>
							)}
						</button>
					</div>
				</div>
			</div>
		</div>
	);
};

export default BidModal;
