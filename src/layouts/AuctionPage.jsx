import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { auctionsAPI, activityAPI } from '../services/api';
import AuctionCard from '../components/Cards/AuctionCard';
import BidModal from '../components/Auction/BidModal';
import ActivityTicker from '../components/Auction/ActivityTicker';

/* ─── Mini chart helpers ───────────────────────────────────────── */

/** Generates a deterministic sparkline that ends at `seed` */
const genSparkline = (seed = 10, n = 12) => {
	const pts = [];
	let v = seed * 0.55;
	for (let i = 0; i < n - 1; i++) {
		v += (seed - v) * 0.22 + Math.sin(seed * 0.7 + i * 1.9) * seed * 0.18;
		pts.push(Math.max(0, Math.round(v)));
	}
	pts.push(seed);
	return pts;
};

const Sparkline = ({ data = [], color = '#00FF88', width = 88, height = 34 }) => {
	if (data.length < 2) return <div style={{ width, height }} />;
	const min = Math.min(...data);
	const max = Math.max(...data);
	const range = max - min || 1;
	const pts = data.map((v, i) => {
		const x = (i / (data.length - 1)) * width;
		const y = height - 4 - ((v - min) / range) * (height - 10);
		return `${x.toFixed(1)},${y.toFixed(1)}`;
	}).join(' ');
	const first = pts.split(' ')[0].split(',');
	const last = pts.split(' ').at(-1).split(',');
	const fillPts = `${first[0]},${height} ${pts} ${last[0]},${height}`;
	const gid = `sg-${color.replace('#', '')}-${width}`;
	return (
		<svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio='none'>
			<defs>
				<linearGradient id={gid} x1='0' y1='0' x2='0' y2='1'>
					<stop offset='0%' stopColor={color} stopOpacity='0.3' />
					<stop offset='100%' stopColor={color} stopOpacity='0' />
				</linearGradient>
			</defs>
			<polygon points={fillPts} fill={`url(#${gid})`} />
			<polyline points={pts} fill='none' stroke={color} strokeWidth='1.8' strokeLinecap='round' strokeLinejoin='round' />
		</svg>
	);
};

const BarSparkline = ({ data = [], color = '#F97316', width = 108, height = 38 }) => {
	if (!data.length) return <div style={{ width, height }} />;
	const max = Math.max(...data, 1);
	const step = width / data.length;
	const barW = step * 0.55;
	return (
		<svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
			{data.map((v, i) => {
				const bh = Math.max(3, (v / max) * (height - 4));
				return (
					<rect
						key={i}
						x={i * step + (step - barW) / 2}
						y={height - bh}
						width={barW}
						height={bh}
						rx='2'
						fill={color}
						opacity={0.35 + (i / data.length) * 0.65}
					/>
				);
			})}
		</svg>
	);
};

const MiniDonut = ({ pct = 0.72, size = 54 }) => {
	const r = 19, cx = size / 2, cy = size / 2;
	const circ = 2 * Math.PI * r;
	const dash = circ * pct;
	return (
		<svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
			<circle cx={cx} cy={cy} r={r} fill='none' stroke='#1A3A2A' strokeWidth='7' />
			<circle cx={cx} cy={cy} r={r} fill='none' stroke='#F59E0B' strokeWidth='7'
				strokeDasharray={`${circ}`} strokeLinecap='butt'
				transform={`rotate(-90 ${cx} ${cy})`} />
			<circle cx={cx} cy={cy} r={r} fill='none' stroke='#00FF88' strokeWidth='7'
				strokeDasharray={`${dash} ${circ - dash}`} strokeLinecap='butt'
				transform={`rotate(-90 ${cx} ${cy})`} />
		</svg>
	);
};

/* ─── Sort options ─────────────────────────────────────────────── */
const SORT_OPTIONS = [
	{ value: 'ending_soon', label: 'Скоро завершення', icon: (
		<svg width='14' height='14' viewBox='0 0 24 24' fill='none'><circle cx='12' cy='12' r='9' stroke='currentColor' strokeWidth='2'/><path d='M12 7v5l3 3' stroke='currentColor' strokeWidth='2' strokeLinecap='round'/></svg>
	)},
	{ value: 'price_desc', label: 'Дорожчі', icon: (
		<svg width='14' height='14' viewBox='0 0 24 24' fill='none'><circle cx='12' cy='12' r='9' stroke='currentColor' strokeWidth='2'/><path d='M12 6v2M12 16v2M8.5 9.5l1.5 1.5M14 14l1.5 1.5M7 12h2M15 12h2' stroke='currentColor' strokeWidth='2' strokeLinecap='round'/></svg>
	)},
	{ value: 'price_asc', label: 'Дешевші', icon: (
		<svg width='14' height='14' viewBox='0 0 24 24' fill='none'><path d='M12 3C8 3 5 8 5 12a7 7 0 0014 0c0-2-1-4-3-6-1 2-1 3-4 3 0-3-1-4.5 0-6z' stroke='currentColor' strokeWidth='2' strokeLinejoin='round'/></svg>
	)},
	{ value: 'bids', label: 'Найбільше ставок', icon: (
		<svg width='14' height='14' viewBox='0 0 24 24' fill='none'><path d='M12 2s-5 5-5 9a5 5 0 0010 0c0-4-5-9-5-9z' stroke='currentColor' strokeWidth='2' strokeLinejoin='round'/></svg>
	)},
];

/* ─── Page component ───────────────────────────────────────────── */
const AuctionPage = () => {
	const [auctions, setAuctions] = useState([]);
	const [stats, setStats] = useState(null);
	const [loading, setLoading] = useState(true);
	const [sort, setSort] = useState('ending_soon');
	const [bidAuction, setBidAuction] = useState(null);
	const [minPrice, setMinPrice] = useState('');
	const [maxPrice, setMaxPrice] = useState('');

	const fetchAuctions = useCallback(async () => {
		try {
			const params = { sort, status: 'active' };
			if (minPrice) params.min_price = minPrice;
			if (maxPrice) params.max_price = maxPrice;
			const [auctionsRes, statsRes] = await Promise.all([
				auctionsAPI.getAll(params),
				activityAPI.getStats(),
			]);
			setAuctions(auctionsRes.data.items);
			setStats(statsRes.data);
		} catch (err) {
			console.error('Failed to load auctions:', err);
		} finally {
			setLoading(false);
		}
	}, [sort, minPrice, maxPrice]);

	useEffect(() => {
		fetchAuctions();
		const interval = setInterval(fetchAuctions, 10000);
		return () => clearInterval(interval);
	}, [fetchAuctions]);

	/* decorative sparkline data derived from stats */
	const auctionsTrend  = genSparkline(stats?.active_auctions  ?? 5,  12);
	const bidsHourly     = genSparkline(stats?.bids_today       ?? 20,  6);
	const investorsTrend = genSparkline(stats?.online_investors ?? 60, 12);

	const cardVariants = {
		hidden: { opacity: 0, y: 18 },
		visible: (i) => ({ opacity: 1, y: 0, transition: { delay: i * 0.07, duration: 0.35, ease: 'easeOut' } }),
	};

	return (
		<section className='min-h-screen pt-28 pb-10'>
			{/* Header */}
			<div className='text-center mb-8'>
				<div className='inline-flex items-center gap-2 bg-orange-900/30 text-orange-400 text-sm font-medium px-4 py-2 rounded-full mb-5'>
					<svg width='14' height='14' viewBox='0 0 24 24' fill='#F97316'><path d='M12 2s-5 5-5 9a5 5 0 0010 0c0-4-5-9-5-9z'/></svg>
					Аукціон каналів
				</div>
				<h1 className='text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-3'>
					Аукціон Telegram-каналів
				</h1>
				<p className='text-gray-500 dark:text-gray-400 max-w-lg mx-auto'>
					Зробіть ставку та отримайте канал за найкращою ціною
				</p>
			</div>

			{/* Activity Ticker */}
			<ActivityTicker />

			{/* ── Dashboard cards ── */}
			<div className='grid grid-cols-2 xl:grid-cols-4 gap-3 mb-5'>

				{/* Card 1 — Active Auctions */}
				<motion.div custom={0} variants={cardVariants} initial='hidden' animate='visible'
					className='relative overflow-hidden bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon p-4'>
					<div className='flex items-start justify-between'>
						<div>
							<div className='w-9 h-9 rounded-lg bg-orange-500/15 flex items-center justify-center mb-3'>
								<svg width='18' height='18' viewBox='0 0 24 24' fill='none'>
									<path d='M12 2s-5 5.5-5 9a5 5 0 0010 0c0-3.5-5-9-5-9z' fill='#F97316' opacity='.7'/>
									<path d='M12 8s-2 2.5-2 4a2 2 0 004 0c0-1.5-2-4-2-4z' fill='#F97316'/>
								</svg>
							</div>
							<p className='text-3xl font-extrabold text-gray-900 dark:text-white leading-none'>
								{stats?.active_auctions ?? '—'}
							</p>
							<p className='text-[11px] text-gray-500 dark:text-gray-400 mt-1.5'>Активні аукціони</p>
						</div>
						<div className='flex flex-col items-end gap-0.5 pt-1'>
							<span className='text-[10px] text-gray-400'>24 ч</span>
							<Sparkline data={auctionsTrend} color='#F97316' width={84} height={32} />
							<span className='text-[10px] text-gray-400'>0</span>
						</div>
					</div>
				</motion.div>

				{/* Card 2 — Bids Today */}
				<motion.div custom={1} variants={cardVariants} initial='hidden' animate='visible'
					className='relative overflow-hidden bg-white dark:bg-card rounded-2xl border border-orange-500/35 shadow-sm dark:shadow-neon p-4'>
					<span className='absolute top-3 right-3 inline-flex items-center gap-1 bg-green-500/15 text-green-400 text-[10px] font-semibold px-2 py-0.5 rounded-full'>
						+12% vs вчора
					</span>
					<div className='flex items-start justify-between mt-4'>
						<div>
							<div className='w-9 h-9 rounded-lg bg-orange-500/15 flex items-center justify-center mb-3'>
								<svg width='18' height='18' viewBox='0 0 24 24' fill='none'>
									<circle cx='12' cy='12' r='8' stroke='#F97316' strokeWidth='2'/>
									<path d='M12 8c-1.1 0-2 .7-2 1.5S11 11 12 11s2 .7 2 1.5S13.1 14 12 14m0-6v1m0 5v1' stroke='#F97316' strokeWidth='1.8' strokeLinecap='round'/>
								</svg>
							</div>
							<p className='text-3xl font-extrabold text-gray-900 dark:text-white leading-none'>
								{stats?.bids_today ?? '—'}
							</p>
							<p className='text-[11px] text-gray-500 dark:text-gray-400 mt-1.5'>Ставок сьогодні</p>
						</div>
						<div className='flex flex-col items-end'>
							<BarSparkline data={bidsHourly} color='#F97316' width={104} height={36} />
							<div className='flex justify-between w-[104px] mt-0.5'>
								{[0, 4, 8, 12, 16, 20].map(h => (
									<span key={h} className='text-[9px] text-gray-500'>{h}</span>
								))}
							</div>
						</div>
					</div>
				</motion.div>

				{/* Card 3 — Deals This Week */}
				<motion.div custom={2} variants={cardVariants} initial='hidden' animate='visible'
					className='relative overflow-hidden bg-white dark:bg-card rounded-2xl border border-green-500/30 shadow-sm dark:shadow-neon p-4'>
					<div className='flex items-start justify-between'>
						<div>
							<div className='w-9 h-9 rounded-lg bg-green-500/15 flex items-center justify-center mb-3'>
								<svg width='18' height='18' viewBox='0 0 24 24' fill='none'>
									<path d='M5 13l4 4L19 7' stroke='#10B981' strokeWidth='2.5' strokeLinecap='round' strokeLinejoin='round'/>
								</svg>
							</div>
							<p className='text-3xl font-extrabold text-gray-900 dark:text-white leading-none'>
								{stats?.deals_this_week ?? '—'}
							</p>
							<p className='text-[11px] text-gray-500 dark:text-gray-400 mt-1.5'>Угод за тиждень</p>
						</div>
						<div className='flex flex-col items-center gap-2 pt-1'>
							<MiniDonut pct={0.72} size={52} />
							<div className='flex flex-col gap-0.5'>
								<span className='flex items-center gap-1'>
									<span className='w-2 h-2 rounded-full bg-accent inline-block' />
									<span className='text-[10px] text-gray-400'>USDT</span>
								</span>
								<span className='flex items-center gap-1'>
									<span className='w-2 h-2 rounded-full bg-yellow-500 inline-block' />
									<span className='text-[10px] text-gray-400'>BNB</span>
								</span>
							</div>
						</div>
					</div>
				</motion.div>

				{/* Card 4 — Online Investors */}
				<motion.div custom={3} variants={cardVariants} initial='hidden' animate='visible'
					className='relative overflow-hidden bg-white dark:bg-card rounded-2xl border border-purple-500/30 shadow-sm dark:shadow-neon p-4'>
					<span className='absolute top-3 right-3 inline-flex items-center gap-1.5 text-green-400 text-[10px] font-semibold'>
						<span className='w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse inline-block' />
						Live
					</span>
					<div className='flex items-start justify-between'>
						<div>
							<div className='w-9 h-9 rounded-lg bg-purple-500/15 flex items-center justify-center mb-3'>
								<svg width='18' height='18' viewBox='0 0 24 24' fill='none'>
									<circle cx='9' cy='7' r='3' stroke='#A855F7' strokeWidth='2'/>
									<circle cx='16' cy='8' r='2.5' stroke='#A855F7' strokeWidth='1.8'/>
									<path d='M3 19c0-3.3 2.7-6 6-6s6 2.7 6 6' stroke='#A855F7' strokeWidth='2' strokeLinecap='round'/>
									<path d='M18 14c1.7.5 3 2.1 3 4' stroke='#A855F7' strokeWidth='1.8' strokeLinecap='round'/>
								</svg>
							</div>
							<p className='text-3xl font-extrabold text-gray-900 dark:text-white leading-none'>
								{stats?.online_investors ?? '—'}
							</p>
							<p className='text-[11px] text-gray-500 dark:text-gray-400 mt-1.5'>Онлайн інвесторів</p>
						</div>
						<div className='pt-1'>
							<Sparkline data={investorsTrend} color='#A855F7' width={84} height={32} />
						</div>
					</div>
				</motion.div>
			</div>

			{/* ── Filters ── */}
			<div className='flex flex-wrap items-center gap-2 mb-6'>
				{SORT_OPTIONS.map((opt) => (
					<button
						key={opt.value}
						onClick={() => setSort(opt.value)}
						className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all duration-200 ${
							sort === opt.value
								? 'bg-orange-500 text-white shadow-lg shadow-orange-900/40'
								: 'bg-white dark:bg-card text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-card-border hover:border-orange-400 dark:hover:border-orange-500'
						}`}
					>
						{opt.icon}
						{opt.label}
					</button>
				))}

				{/* Price range */}
				<div className='ml-auto flex items-center gap-2'>
					<div className='relative'>
						<select className='appearance-none bg-white dark:bg-card border border-gray-200 dark:border-card-border text-gray-500 dark:text-gray-400 text-xs rounded-xl px-3 py-[9px] pr-7 focus:outline-none focus:border-orange-400 cursor-pointer'>
							<option>Ціновий діапазон (USDT)</option>
						</select>
						<svg className='pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400' width='10' height='10' viewBox='0 0 12 12'>
							<path d='M2 4l4 4 4-4' stroke='currentColor' strokeWidth='1.5' strokeLinecap='round' strokeLinejoin='round' fill='none'/>
						</svg>
					</div>
					<input type='number' placeholder='Min' value={minPrice} onChange={e => setMinPrice(e.target.value)}
						className='w-20 bg-white dark:bg-card border border-gray-200 dark:border-card-border text-gray-900 dark:text-white text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-orange-400 placeholder-gray-400' />
					<span className='text-gray-400 text-xs font-medium'>~</span>
					<input type='number' placeholder='Max' value={maxPrice} onChange={e => setMaxPrice(e.target.value)}
						className='w-20 bg-white dark:bg-card border border-gray-200 dark:border-card-border text-gray-900 dark:text-white text-xs rounded-xl px-3 py-2 focus:outline-none focus:border-orange-400 placeholder-gray-400' />
				</div>
			</div>

			{/* ── Auction Grid ── */}
			{loading ? (
				<div className='grid md:grid-cols-2 lg:grid-cols-3 gap-6'>
					{[1, 2, 3].map((i) => (
						<div key={i} className='bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border h-72 animate-pulse' />
					))}
				</div>
			) : auctions.length === 0 ? (
				<div className='text-center py-20'>
					<div className='text-6xl mb-4'>🏷️</div>
					<h3 className='text-xl font-bold text-gray-900 dark:text-white mb-2'>
						Поки немає активних аукціонів
					</h3>
					<p className='text-gray-500 dark:text-gray-400'>
						Подайте свій канал на аукціон або перевірте пізніше
					</p>
				</div>
			) : (
				<div className='grid md:grid-cols-2 lg:grid-cols-3 gap-6'>
					{auctions.map((auction) => (
						<AuctionCard key={auction.id} auction={auction} onBid={() => setBidAuction(auction)} />
					))}
				</div>
			)}

			{bidAuction && (
				<BidModal
					auction={bidAuction}
					onClose={() => setBidAuction(null)}
					onSuccess={() => {
						setBidAuction(null);
						fetchAuctions();
					}}
				/>
			)}
		</section>
	);
};

export default AuctionPage;
