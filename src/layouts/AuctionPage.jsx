import { useState, useEffect } from 'react';
import { auctionsAPI, activityAPI } from '../services/api';
import AuctionCard from '../components/Cards/AuctionCard';
import BidModal from '../components/Auction/BidModal';
import ActivityTicker from '../components/Auction/ActivityTicker';

const AuctionPage = () => {
	const [auctions, setAuctions] = useState([]);
	const [stats, setStats] = useState(null);
	const [loading, setLoading] = useState(true);
	const [sort, setSort] = useState('ending_soon');
	const [bidAuction, setBidAuction] = useState(null);

	const fetchAuctions = async () => {
		try {
			const [auctionsRes, statsRes] = await Promise.all([
				auctionsAPI.getAll({ sort, status: 'active' }),
				activityAPI.getStats(),
			]);
			setAuctions(auctionsRes.data.items);
			setStats(statsRes.data);
		} catch (err) {
			console.error('Failed to load auctions:', err);
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => {
		fetchAuctions();
		const interval = setInterval(fetchAuctions, 10000);
		return () => clearInterval(interval);
	}, [sort]);

	const sortOptions = [
		{ value: 'ending_soon', label: '⏰ Скоро завершення' },
		{ value: 'price_desc', label: '💰 Дорожчі' },
		{ value: 'price_asc', label: '💸 Дешевші' },
		{ value: 'bids', label: '🔥 Найбільше ставок' },
	];

	return (
		<section className='min-h-screen py-20 px-4'>
			<div className='max-w-7xl mx-auto'>
				{/* Header */}
				<div className='text-center mb-8'>
					<div className='inline-flex items-center gap-2 bg-orange-50 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 text-sm font-medium px-4 py-2 rounded-full mb-5'>
						<span>🔥</span>
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

				{/* Stats Bar */}
				{stats && (
					<div className='grid grid-cols-2 md:grid-cols-4 gap-4 mb-8'>
						{[
							{ label: 'Активні аукціони', value: stats.active_auctions, icon: '🔥' },
							{ label: 'Ставок сьогодні', value: stats.bids_today, icon: '💰' },
							{ label: 'Угод за тиждень', value: stats.deals_this_week, icon: '✅' },
							{ label: 'Онлайн інвесторів', value: stats.online_investors, icon: '👥' },
						].map((s) => (
							<div
								key={s.label}
								className='bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 p-4 text-center'
							>
								<div className='text-2xl mb-1'>{s.icon}</div>
								<div className='text-2xl font-bold text-gray-900 dark:text-white'>
									{s.value}
								</div>
								<div className='text-xs text-gray-500 dark:text-gray-400'>{s.label}</div>
							</div>
						))}
					</div>
				)}

				{/* Sort */}
				<div className='flex items-center gap-3 mb-6 overflow-x-auto pb-2'>
					{sortOptions.map((opt) => (
						<button
							key={opt.value}
							onClick={() => setSort(opt.value)}
							className={`px-4 py-2 rounded-xl text-sm font-medium whitespace-nowrap transition-all duration-200 ${
								sort === opt.value
									? 'bg-orange-500 text-white shadow-lg shadow-orange-200 dark:shadow-orange-900/30'
									: 'bg-white dark:bg-slate-800 text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-slate-700 hover:border-orange-300 dark:hover:border-orange-700'
							}`}
						>
							{opt.label}
						</button>
					))}
				</div>

				{/* Auction Grid */}
				{loading ? (
					<div className='grid md:grid-cols-2 lg:grid-cols-3 gap-6'>
						{[1, 2, 3].map((i) => (
							<div
								key={i}
								className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 h-72 animate-pulse'
							/>
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
							<AuctionCard
								key={auction.id}
								auction={auction}
								onBid={() => setBidAuction(auction)}
							/>
						))}
					</div>
				)}
			</div>

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
