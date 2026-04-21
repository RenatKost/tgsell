import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';

const AuctionCard = ({ auction, onBid }) => {
	const navigate = useNavigate();
	const [timeLeft, setTimeLeft] = useState('');
	const [urgent, setUrgent] = useState(false);      // < 1 hour
	const [veryUrgent, setVeryUrgent] = useState(false); // < 5 min
	const [progress, setProgress] = useState(0);

	// Heartbeat every 30s
	const [beat, setBeat] = useState(false);

	// Flash states for live updates
	const [priceFlash, setPriceFlash] = useState(false);
	const [bidFlash, setBidFlash] = useState(false);
	const prevPrice = useRef(auction.current_price);
	const prevBids  = useRef(auction.bid_count);

	/* Countdown + progress */
	useEffect(() => {
		const update = () => {
			const end   = new Date(auction.ends_at).getTime();
			const start = auction.starts_at
				? new Date(auction.starts_at).getTime()
				: end - 7 * 86_400_000;
			const now  = Date.now();
			const diff = end - now;
			const total = end - start;
			setProgress(total > 0 ? Math.min(1, (now - start) / total) : 0);
			if (diff <= 0) { setTimeLeft('Завершено'); setUrgent(false); setVeryUrgent(false); return; }
			setVeryUrgent(diff < 5 * 60_000);
			setUrgent(diff < 3_600_000);
			const h = Math.floor(diff / 3_600_000);
			const m = Math.floor((diff % 3_600_000) / 60_000);
			const s = Math.floor((diff % 60_000) / 1_000);
			setTimeLeft(h > 0 ? `${h}г ${m}хв` : `${m}:${s.toString().padStart(2, '0')}`);
		};
		update();
		const iv = setInterval(update, 1000);
		return () => clearInterval(iv);
	}, [auction.ends_at, auction.starts_at]);

	/* Price flash on external update */
	useEffect(() => {
		if (prevPrice.current !== auction.current_price) {
			setPriceFlash(true);
			const t = setTimeout(() => setPriceFlash(false), 900);
			prevPrice.current = auction.current_price;
			return () => clearTimeout(t);
		}
	}, [auction.current_price]);

	/* Bid count flash */
	useEffect(() => {
		if (prevBids.current !== auction.bid_count) {
			setBidFlash(true);
			const t = setTimeout(() => setBidFlash(false), 700);
			prevBids.current = auction.bid_count;
			return () => clearTimeout(t);
		}
	}, [auction.bid_count]);

	/* Heartbeat every 30s */
	useEffect(() => {
		const iv = setInterval(() => {
			setBeat(true);
			const t = setTimeout(() => setBeat(false), 800);
			return () => clearTimeout(t);
		}, 30_000);
		return () => clearInterval(iv);
	}, []);

	const isHot  = (auction.bid_count ?? 0) >= 5;
	const uplift = auction.current_price && auction.start_price && auction.start_price > 0
		? Math.round(((auction.current_price - auction.start_price) / auction.start_price) * 100)
		: null;

	return (
		<motion.div
			initial={{ opacity: 0, y: 28 }}
			whileInView={{ opacity: 1, y: 0 }}
			viewport={{ once: true, amount: 0.15 }}
			transition={{ duration: 0.42, ease: 'easeOut' }}
			whileHover={{ y: -5, transition: { duration: 0.2 } }}
			className={`relative overflow-hidden bg-white dark:bg-card rounded-xl
				border border-gray-100 dark:border-card-border
				border-l-4 ${veryUrgent ? 'border-l-red-500' : 'border-l-orange-500'}
				shadow-sm dark:shadow-neon flex flex-col`}
		>
			{/* Top shimmer bar */}
			<div className='absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-orange-500 via-amber-400 to-transparent opacity-70 pointer-events-none' />

			{/* Urgent ambient glow */}
			{urgent && (
				<motion.div
					className='absolute inset-0 pointer-events-none rounded-xl'
					animate={{ opacity: [0, 0.07, 0] }}
					transition={{ repeat: Infinity, duration: 2.8, ease: 'easeInOut' }}
					style={{
						background: veryUrgent
							? 'radial-gradient(ellipse at 50% 0%, #ef4444 0%, transparent 60%)'
							: 'radial-gradient(ellipse at 50% 0%, #f97316 0%, transparent 60%)',
					}}
				/>
			)}

			{/* HOT badge */}
			{isHot && (
				<motion.div
					className='absolute top-3 right-3 z-10'
					animate={{ scale: [1, 1.13, 1] }}
					transition={{ repeat: Infinity, duration: 1.9, ease: 'easeInOut' }}
				>
					<span className='inline-flex items-center gap-1 bg-red-500 text-white text-[10px] font-black px-2 py-0.5 rounded-full shadow shadow-red-500/50'>
						🔥 HOT
					</span>
				</motion.div>
			)}

			{/* Header */}
			<div className='p-4 pb-3'>
				<div className='flex items-center gap-3'>
					{auction.channel_avatar ? (
						<img
							src={auction.channel_avatar}
							alt={auction.channel_name}
							className='w-11 h-11 rounded-lg object-cover flex-shrink-0 ring-2 ring-orange-500/30'
						/>
					) : (
						<div className='w-11 h-11 rounded-lg bg-gradient-to-br from-orange-400 to-red-500 flex items-center justify-center text-white font-black text-sm flex-shrink-0 ring-2 ring-orange-500/30'>
							{(auction.channel_name || '?')[0]}
						</div>
					)}
					<div className={`flex-1 min-w-0 ${isHot ? 'pr-14' : ''}`}>
						<h3
							className='font-bold text-gray-900 dark:text-white text-sm truncate cursor-pointer hover:text-orange-500 dark:hover:text-orange-400 transition-colors leading-tight'
							onClick={() => navigate(`/channel/${auction.channel_id}`)}
						>
							{auction.channel_name || 'Канал'}
						</h3>
						<div className='flex items-center gap-1.5 mt-0.5 flex-wrap'>
							{auction.category && (
								<span className='text-[11px] bg-gray-50 dark:bg-card-inner text-gray-500 dark:text-gray-400 px-2 py-0.5 rounded-md'>
									{auction.category}
								</span>
							)}
							{auction.subscribers_count > 0 && (
								<span className='text-[11px] text-gray-400 dark:text-gray-500'>
									{(auction.subscribers_count / 1000).toFixed(1)}K підп.
								</span>
							)}
						</div>
					</div>
				</div>
			</div>

			{/* Key Metrics */}
			<div className='px-4 pb-3 flex-1'>
				<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>Метрики</p>
				<div className='grid grid-cols-2 gap-2'>
					{/* Current price — flashes on update */}
					<motion.div
						animate={priceFlash ? { borderLeftColor: ['#fb923c', '#f97316', '#fb923c'] } : {}}
						transition={{ duration: 0.6 }}
						className='border-l-2 border-orange-400 bg-gray-50 dark:bg-card-inner rounded-r-lg pl-3 pr-2 py-2 col-span-2'
					>
						<p className='text-gray-400 text-[10px]'>Поточна ставка</p>
						<motion.p
							animate={priceFlash ? { color: ['#f97316', '#fb923c', '#f97316'] } : {}}
							transition={{ duration: 0.7 }}
							className='font-extrabold text-xl text-orange-500 leading-tight'
						>
							{auction.current_price?.toLocaleString('uk-UA')}
							<span className='text-xs font-semibold text-gray-400 ml-1'>USDT</span>
							{uplift !== null && uplift > 0 && (
								<span className='ml-2 text-[10px] font-bold text-emerald-500'>+{uplift}%</span>
							)}
						</motion.p>
					</motion.div>

					<div className='border-l-2 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-card-inner rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>Стартова</p>
						<p className='font-bold text-sm text-gray-500 dark:text-gray-300'>
							{auction.start_price?.toLocaleString('uk-UA')} <span className='text-[10px]'>USDT</span>
						</p>
					</div>

					<div className='border-l-2 border-emerald-400 bg-gray-50 dark:bg-card-inner rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>ER каналу</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>
							{auction.er != null ? `${Number(auction.er).toFixed(1)}%` : '—'}
						</p>
					</div>

					<div className='border-l-2 border-cyan-400 bg-gray-50 dark:bg-card-inner rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>Переглядів</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>
							{auction.views_hidden
								? <span className='text-amber-500 text-xs'>🔒</span>
								: (auction.avg_views ? auction.avg_views.toLocaleString('uk-UA') : '—')}
						</p>
					</div>

					<div className='border-l-2 border-violet-400 bg-gray-50 dark:bg-card-inner rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>Прибуток / міс.</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>
							{auction.monthly_income
								? `${auction.monthly_income.toLocaleString('uk-UA')} USDT`
								: '—'}
						</p>
					</div>
				</div>
			</div>

			{/* Auction progress bar */}
			<div className='px-4 pb-3'>
				<div className='flex items-center justify-between mb-1.5'>
					<span className='text-[10px] text-gray-400'>Прогрес аукціону</span>
					<span className='text-[10px] text-gray-400 tabular-nums'>{Math.round(progress * 100)}%</span>
				</div>
				<div className='h-1.5 bg-gray-100 dark:bg-card-inner rounded-full overflow-hidden'>
					<motion.div
						className={`h-full rounded-full ${veryUrgent ? 'bg-red-500' : urgent ? 'bg-amber-400' : 'bg-orange-500'}`}
						initial={{ width: 0 }}
						animate={{ width: `${progress * 100}%` }}
						transition={{ duration: 1, ease: 'easeOut' }}
					/>
				</div>
			</div>

			{/* Timer + Bid count */}
			<div className='px-4 pb-3 flex items-center justify-between'>
				<motion.div
					className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold ${
						veryUrgent
							? 'bg-red-500/15 text-red-500'
							: urgent
							? 'bg-amber-500/15 text-amber-500'
							: 'bg-orange-500/10 text-orange-500 dark:text-orange-400'
					}`}
					animate={veryUrgent ? { scale: [1, 1.05, 1] } : {}}
					transition={{ repeat: Infinity, duration: 0.85 }}
				>
					<svg className='w-3.5 h-3.5 flex-shrink-0' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2.5}>
						<path strokeLinecap='round' strokeLinejoin='round' d='M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' />
					</svg>
					<span className='tabular-nums'>{timeLeft}</span>
				</motion.div>

				<motion.div
					animate={bidFlash ? { scale: [1, 1.3, 1] } : {}}
					transition={{ duration: 0.45 }}
					className={`flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1.5 rounded-lg transition-colors ${
						bidFlash
							? 'bg-orange-500/20 text-orange-400'
							: 'bg-gray-50 dark:bg-card-inner text-gray-500 dark:text-gray-400'
					}`}
				>
					<svg className='w-3.5 h-3.5' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
						<path strokeLinecap='round' strokeLinejoin='round' d='M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' />
					</svg>
					{auction.bid_count ?? 0} ставок
				</motion.div>
			</div>

			{/* Bid button with 30s heartbeat */}
			<div className='px-4 pb-4'>
				<motion.button
					onClick={onBid}
					animate={beat
						? {
							scale: [1, 1.07, 0.96, 1.05, 1],
							boxShadow: [
								'0 4px 14px rgba(249,115,22,0.30)',
								'0 4px 32px rgba(249,115,22,0.70)',
								'0 4px 14px rgba(249,115,22,0.30)',
							],
						}
						: {}
					}
					transition={{ duration: 0.65, ease: 'easeOut' }}
					whileHover={{ scale: 1.03, boxShadow: '0 6px 26px rgba(249,115,22,0.55)' }}
					whileTap={{ scale: 0.95 }}
					className='w-full bg-gradient-to-r from-orange-500 to-amber-500 text-white font-bold py-2.5 rounded-xl text-sm flex items-center justify-center gap-2 shadow-md shadow-orange-500/30'
				>
					<motion.span
						animate={{ rotate: [0, -12, 12, -7, 0] }}
						transition={{ repeat: Infinity, duration: 2.8, ease: 'easeInOut', repeatDelay: 5 }}
					>
						🔥
					</motion.span>
					Зробити ставку
				</motion.button>
			</div>
		</motion.div>
	);
};

export default AuctionCard;
