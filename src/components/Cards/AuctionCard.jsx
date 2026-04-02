import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const AuctionCard = ({ auction, onBid }) => {
	const navigate = useNavigate();
	const [timeLeft, setTimeLeft] = useState('');
	const [urgent, setUrgent] = useState(false);

	useEffect(() => {
		const update = () => {
			const end = new Date(auction.ends_at).getTime();
			const now = Date.now();
			const diff = end - now;

			if (diff <= 0) {
				setTimeLeft('Завершено');
				setUrgent(false);
				return;
			}

			setUrgent(diff < 3600000); // < 1 hour

			const hours = Math.floor(diff / 3600000);
			const mins = Math.floor((diff % 3600000) / 60000);
			const secs = Math.floor((diff % 60000) / 1000);

			if (hours > 0) {
				setTimeLeft(`${hours}г ${mins}хв`);
			} else {
				setTimeLeft(`${mins}:${secs.toString().padStart(2, '0')}`);
			}
		};

		update();
		const interval = setInterval(update, 1000);
		return () => clearInterval(interval);
	}, [auction.ends_at]);

	return (
		<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 overflow-hidden hover:shadow-lg hover:border-orange-200 dark:hover:border-orange-800 transition-all duration-300 group'>
			{/* Header */}
			<div className='p-5 pb-3'>
				<div className='flex items-start gap-3'>
					{auction.channel_avatar ? (
						<img
							src={auction.channel_avatar}
							alt=''
							className='w-12 h-12 rounded-xl object-cover'
						/>
					) : (
						<div className='w-12 h-12 rounded-xl bg-gradient-to-br from-orange-400 to-red-500 flex items-center justify-center'>
							<span className='text-white font-bold text-lg'>
								{(auction.channel_name || '?')[0]}
							</span>
						</div>
					)}
					<div className='flex-1 min-w-0'>
						<h3
							className='font-bold text-gray-900 dark:text-white truncate cursor-pointer hover:text-orange-500 transition-colors'
							onClick={() => navigate(`/channel/${auction.channel_id}`)}
						>
							{auction.channel_name || 'Канал'}
						</h3>
						<div className='flex items-center gap-2 mt-0.5'>
							{auction.category && (
								<span className='text-xs text-gray-500 dark:text-gray-400'>
									{auction.category}
								</span>
							)}
							{auction.subscribers_count > 0 && (
								<span className='text-xs text-gray-400 dark:text-gray-500'>
									• {(auction.subscribers_count / 1000).toFixed(1)}K підписників
								</span>
							)}
						</div>
					</div>
				</div>
			</div>

			{/* Price section */}
			<div className='px-5 py-3'>
				<div className='flex items-end justify-between'>
					<div>
						<div className='text-xs text-gray-500 dark:text-gray-400 mb-0.5'>
							Поточна ціна
						</div>
						<div className='text-2xl font-bold text-orange-500'>
							{auction.current_price.toLocaleString()} <span className='text-sm font-normal'>USDT</span>
						</div>
					</div>
				</div>
			</div>

			{/* Timer + Bids */}
			<div className='px-5 py-3 flex items-center justify-between'>
				<div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium ${
					urgent
						? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 animate-pulse'
						: 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300'
				}`}>
					<svg className='w-4 h-4' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
						<path strokeLinecap='round' strokeLinejoin='round' d='M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' />
					</svg>
					{timeLeft}
				</div>
				<div className='flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400'>
					<svg className='w-4 h-4' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
						<path strokeLinecap='round' strokeLinejoin='round' d='M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' />
					</svg>
					{auction.bid_count} ставок
				</div>
			</div>

			{/* Bid Button */}
			<div className='p-5 pt-2'>
				<button
					onClick={onBid}
					className='w-full bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white font-semibold py-3 rounded-xl transition-all duration-200 hover:shadow-lg hover:shadow-orange-200 dark:hover:shadow-orange-900/30 flex items-center justify-center gap-2'
				>
					<span>🔥</span>
					Зробити ставку
				</button>
			</div>
		</div>
	);
};

export default AuctionCard;
