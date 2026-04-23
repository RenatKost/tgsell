import { useEffect, useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import CatalogCard from '../components/Cards/CatalogCard';
import { channelsAPI, bundlesAPI } from '../services/api';
import BundleCard from '../components/Cards/BundleCard';
import { options as categoryOptions } from '../components/Main/Calculator';

/* ── Dual-range price slider ────────────────────────────────────── */
const PriceRangeSlider = ({ min = 0, max = 50000, value, onChange }) => {
	const [lo, hi] = value;
	const trackRef = useRef(null);

	const pct = (v) => ((v - min) / (max - min)) * 100;

	const handleLo = (e) => {
		const v = Math.min(Number(e.target.value), hi - 1);
		onChange([v, hi]);
	};
	const handleHi = (e) => {
		const v = Math.max(Number(e.target.value), lo + 1);
		onChange([lo, v]);
	};

	return (
		<div className='flex items-center gap-2 min-w-[160px]'>
			<span className='text-[10px] text-gray-400 whitespace-nowrap'>{lo.toLocaleString()}</span>
			<div className='relative flex-1 h-4' ref={trackRef}>
				<div className='absolute top-1/2 -translate-y-1/2 left-0 right-0 h-1.5 rounded-full bg-card-inner dark:bg-card-inner' />
				<div
					className='absolute top-1/2 -translate-y-1/2 h-1.5 rounded-full bg-accent'
					style={{ left: `${pct(lo)}%`, right: `${100 - pct(hi)}%` }}
				/>
				<input type='range' min={min} max={max} step={100} value={lo}
					onChange={handleLo}
					className='absolute w-full top-1/2 -translate-y-1/2 appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-page [&::-webkit-slider-thumb]:cursor-pointer [&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-accent [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-page [&::-moz-range-thumb]:cursor-pointer'
				/>
				<input type='range' min={min} max={max} step={100} value={hi}
					onChange={handleHi}
					className='absolute w-full top-1/2 -translate-y-1/2 appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-page [&::-webkit-slider-thumb]:cursor-pointer [&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-accent [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-page [&::-moz-range-thumb]:cursor-pointer'
				/>
			</div>
			<span className='text-[10px] text-gray-400 whitespace-nowrap'>{hi >= max ? '∞' : hi.toLocaleString()}</span>
		</div>
	);
};

/* ── Filter chip ────────────────────────────────────────────────── */
const Chip = ({ active, onClick, icon, label, activeColor = 'bg-accent text-black' }) => (
	<button
		onClick={onClick}
		className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[12px] font-semibold whitespace-nowrap transition-all duration-200 border ${
			active
				? `${activeColor} border-transparent shadow-sm`
				: 'bg-white dark:bg-card text-gray-500 dark:text-gray-400 border-gray-200 dark:border-card-border hover:border-accent/50 dark:hover:border-accent/40'
		}`}
	>
		{icon}
		{label}
	</button>
);

const PRICE_MAX = 50000;

const CatalogPage = () => {
	const [channels, setChannels] = useState([]);
	const [bundles, setBundles] = useState([]);
	const [bundlesLoading, setBundlesLoading] = useState(true);
	const [loading, setLoading] = useState(true);
	const [search, setSearch] = useState('');
	const [category, setCategory] = useState('');
	const [sortBy, setSortBy] = useState('newest');
	const [page, setPage] = useState(1);
	const [totalPages, setTotalPages] = useState(1);

	// Quick filters
	const [roi6, setRoi6] = useState(false);
	const [roi12, setRoi12] = useState(false);
	const [er20, setEr20] = useState(false);
	const [verifiedData, setVerifiedData] = useState(false);
	const [aiRecommended, setAiRecommended] = useState(false);
	const [priceRange, setPriceRange] = useState([0, PRICE_MAX]);
	// Debounced price — updates 1s after user stops dragging
	const [debouncedPrice, setDebouncedPrice] = useState([0, PRICE_MAX]);
	useEffect(() => {
		const t = setTimeout(() => setDebouncedPrice(priceRange), 1000);
		return () => clearTimeout(t);
	}, [priceRange]);

	const fetchChannels = useCallback(async () => {
		setLoading(true);
		try {
			const params = {
				search,
				category,
				sort: sortBy,
				page,
				limit: 12,
			};
			if (roi6) params.roi_max = 6;
			else if (roi12) params.roi_max = 12;
			if (er20) params.er_min = 20;
			if (verifiedData) params.verified_data = true;
			if (aiRecommended) params.ai_recommended = true;
			if (debouncedPrice[0] > 0) params.min_price = debouncedPrice[0];
			if (debouncedPrice[1] < PRICE_MAX) params.max_price = debouncedPrice[1];

			const { data } = await channelsAPI.getAll(params);
			setChannels(data.items || data);
			setTotalPages(data.total_pages || 1);
		} catch (err) {
			console.error('Failed to load channels:', err);
			setChannels([]);
		} finally {
			setLoading(false);
		}
	}, [search, category, sortBy, page, roi6, roi12, er20, verifiedData, aiRecommended, debouncedPrice]);

	useEffect(() => {
		setBundlesLoading(true);
		bundlesAPI.getAll({ limit: 20 })
			.then(({ data }) => setBundles(data.items || []))
			.catch(() => setBundles([]))
			.finally(() => setBundlesLoading(false));
	}, []);

	useEffect(() => {
		fetchChannels();
	}, [fetchChannels]);

	const resetPage = () => setPage(1);

	return (
		<section className='pt-28 pb-10'>
			{/* ── Header row ── */}
			<div className='flex flex-col sm:flex-row sm:items-end gap-3 mb-5'>
				<div>
					<h1 className='font-black text-2xl md:text-3xl text-gray-900 dark:text-white tracking-tight uppercase'>
						Каталог каналів
					</h1>
					<p className='text-gray-500 dark:text-gray-400 text-sm mt-0.5'>
						Знайдіть ідеальний Telegram-канал для покупки
					</p>
				</div>
				{/* Search */}
				<div className='relative sm:ml-auto w-full sm:w-64'>
					<span className='absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none'>
						<svg width='14' height='14' viewBox='0 0 24 24' fill='none'>
							<circle cx='11' cy='11' r='7' stroke='#6B7280' strokeWidth='2'/>
							<path d='M16.5 16.5l3.5 3.5' stroke='#6B7280' strokeWidth='2' strokeLinecap='round'/>
						</svg>
					</span>
					<input
						type='text'
						placeholder='Пошук'
						value={search}
						onChange={(e) => { setSearch(e.target.value); resetPage(); }}
						className='w-full bg-white dark:bg-card border border-gray-200 dark:border-card-border pl-9 pr-4 py-2 rounded-xl text-sm focus:border-accent focus:outline-none dark:text-white dark:placeholder-gray-500 transition-colors'
					/>
				</div>
			</div>

			{/* ── Filter bar ── */}
			<div className='flex flex-wrap items-center gap-2 mb-6 bg-white dark:bg-card border border-gray-100 dark:border-card-border rounded-2xl px-4 py-3 shadow-sm dark:shadow-neon'>

				{/* Category dropdown */}
				<div className='relative'>
					<select
						value={category}
						onChange={(e) => { setCategory(e.target.value); resetPage(); }}
						className='appearance-none bg-gray-50 dark:bg-card-inner border border-gray-200 dark:border-card-border text-gray-700 dark:text-gray-300 text-[12px] font-semibold pl-3 pr-7 py-1.5 rounded-xl focus:outline-none focus:border-accent cursor-pointer transition-colors'
					>
						<option value=''>Категорія</option>
						{categoryOptions.map(opt => (
							<option key={opt.label} value={opt.label}>{opt.label}</option>
						))}
					</select>
					<svg className='pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-gray-400' width='10' height='10' viewBox='0 0 12 12'>
						<path d='M2 4l4 4 4-4' stroke='currentColor' strokeWidth='1.6' strokeLinecap='round' strokeLinejoin='round' fill='none'/>
					</svg>
				</div>

				{/* Sort dropdown */}
				<div className='relative'>
					<select
						value={sortBy}
						onChange={(e) => { setSortBy(e.target.value); resetPage(); }}
						className='appearance-none bg-gray-50 dark:bg-card-inner border border-gray-200 dark:border-card-border text-gray-700 dark:text-gray-300 text-[12px] font-semibold pl-3 pr-7 py-1.5 rounded-xl focus:outline-none focus:border-accent cursor-pointer transition-colors'
					>
						<option value='newest'>Новіші</option>
						<option value='price_asc'>Ціна ↑</option>
						<option value='price_desc'>Ціна ↓</option>
						<option value='subscribers_desc'>Підписники ↓</option>
					</select>
					<svg className='pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-gray-400' width='10' height='10' viewBox='0 0 12 12'>
						<path d='M2 4l4 4 4-4' stroke='currentColor' strokeWidth='1.6' strokeLinecap='round' strokeLinejoin='round' fill='none'/>
					</svg>
				</div>

				<div className='h-5 w-px bg-gray-200 dark:bg-card-border mx-1 hidden sm:block' />

				{/* ROI chips */}
				<Chip
					active={roi6}
					onClick={() => { setRoi6(v => !v); if (!roi6) setRoi12(false); resetPage(); }}
					icon={
						<svg width='12' height='12' viewBox='0 0 24 24' fill='none'>
							<path d='M3 17l4-8 4 5 3-3 4 6' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'/>
						</svg>
					}
					label='ROI < 6 міс.'
					activeColor='bg-accent text-black'
				/>
				<Chip
					active={roi12}
					onClick={() => { setRoi12(v => !v); if (!roi12) setRoi6(false); resetPage(); }}
					icon={
						<svg width='12' height='12' viewBox='0 0 24 24' fill='none'>
							<path d='M3 17l4-8 4 5 3-3 4 6' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'/>
						</svg>
					}
					label='ROI < 12 міс.'
					activeColor='bg-accent text-black'
				/>
				<Chip
					active={er20}
					onClick={() => { setEr20(v => !v); resetPage(); }}
					icon={
						<svg width='12' height='12' viewBox='0 0 24 24' fill='none'>
							<path d='M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z' stroke='currentColor' strokeWidth='2'/>
							<circle cx='12' cy='12' r='3' stroke='currentColor' strokeWidth='2'/>
						</svg>
					}
					label='ER > 20%'
					activeColor='bg-accent text-black'
				/>

				<div className='h-5 w-px bg-gray-200 dark:bg-card-border mx-1 hidden sm:block' />

				{/* Verified data */}
				<Chip
					active={verifiedData}
					onClick={() => { setVerifiedData(v => !v); resetPage(); }}
					icon={
						<svg width='12' height='12' viewBox='0 0 24 24' fill='none'>
							<path d='M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z' stroke='currentColor' strokeWidth='2' strokeLinejoin='round'/>
						</svg>
					}
					label='verified data'
					activeColor='bg-green-500 text-white'
				/>

				{/* AI підбор */}
				<Chip
					active={aiRecommended}
					onClick={() => { setAiRecommended(v => !v); resetPage(); }}
					icon={
						<svg width='12' height='12' viewBox='0 0 24 24' fill='none'>
							<rect x='3' y='7' width='18' height='12' rx='2' stroke='currentColor' strokeWidth='2'/>
							<path d='M8 7V5a4 4 0 018 0v2' stroke='currentColor' strokeWidth='2' strokeLinecap='round'/>
							<circle cx='12' cy='13' r='2' fill='currentColor'/>
						</svg>
					}
					label='AI-підбор'
					activeColor='bg-accent text-black'
				/>

				{/* Price range */}
				<div className='sm:ml-auto flex items-center gap-2'>
					<span className='text-[11px] text-gray-400 font-medium whitespace-nowrap'>Ціна USDT</span>
					<PriceRangeSlider
						min={0}
						max={PRICE_MAX}
						value={priceRange}
						onChange={(v) => { setPriceRange(v); resetPage(); }}
					/>
				</div>
			</div>

			{/* Active filter badges */}
			<AnimatePresence>
				{(roi6 || roi12 || er20 || verifiedData || aiRecommended || priceRange[0] > 0 || priceRange[1] < PRICE_MAX) && (
					<motion.div
						initial={{ opacity: 0, height: 0 }}
						animate={{ opacity: 1, height: 'auto' }}
						exit={{ opacity: 0, height: 0 }}
						className='flex flex-wrap items-center gap-2 mb-4'
					>
						<span className='text-xs text-gray-400'>Активні фільтри:</span>
						{roi6 && <span className='text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full'>ROI &lt; 6 міс.</span>}
						{roi12 && <span className='text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full'>ROI &lt; 12 міс.</span>}
						{er20 && <span className='text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full'>ER &gt; 20%</span>}
						{verifiedData && <span className='text-xs bg-green-500/10 text-green-400 px-2 py-0.5 rounded-full'>✓ verified data</span>}
						{aiRecommended && <span className='text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full'>🤖 AI-підбор</span>}
						{(priceRange[0] > 0 || priceRange[1] < PRICE_MAX) && (
							<span className='text-xs bg-accent/10 text-accent px-2 py-0.5 rounded-full'>
								{priceRange[0].toLocaleString()}–{priceRange[1] >= PRICE_MAX ? '∞' : priceRange[1].toLocaleString()} USDT
							</span>
						)}
						<button
							onClick={() => {
								setRoi6(false); setRoi12(false); setEr20(false);
								setVerifiedData(false); setAiRecommended(false);
								setPriceRange([0, PRICE_MAX]); resetPage();
							}}
							className='text-xs text-gray-400 hover:text-red-400 transition-colors ml-1'
						>
							Скинути все ×
						</button>
					</motion.div>
				)}
			</AnimatePresence>

			{/* Bundles section */}
			{(bundlesLoading || bundles.length > 0) && (
				<div className='mb-10'>
					<div className='flex items-center gap-2 mb-4'>
						<span className='text-accent text-xl'>📡</span>
						<h2 className='font-black text-xl text-white uppercase tracking-tight'>Сітки каналів</h2>
						{!bundlesLoading && (
							<span className='text-xs text-gray-500 ml-1'>{bundles.length} {bundles.length === 1 ? 'сітка' : 'сітки'}</span>
						)}
					</div>
					{bundlesLoading ? (
						<div className='grid xl:grid-cols-3 md:grid-cols-2 gap-6'>
							{[1, 2].map(i => <div key={i} className='bg-card rounded-2xl border border-card-border h-64 animate-pulse' />)}
						</div>
					) : (
						<div className='grid xl:grid-cols-3 md:grid-cols-2 gap-6'>
							{bundles.map(b => <BundleCard key={b.id} bundle={b} />)}
						</div>
					)}
					<div className='border-b border-card-border mt-8' />
				</div>
			)}

			{/* Results count */}
			{!loading && channels.length > 0 && (
				<p className='text-gray-400 text-xs mb-4'>
					Знайдено: <span className='text-gray-300 font-medium'>{channels.length}</span>
				</p>
			)}

			{/* Grid */}
			{loading ? (
				<div className='grid xl:grid-cols-3 md:grid-cols-2 gap-6'>
					{[1, 2, 3, 4, 5, 6].map((i) => (
						<div key={i} className='bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border h-64 animate-pulse' />
					))}
				</div>
			) : channels.length === 0 ? (
				<div className='text-center py-20'>
					<p className='text-4xl mb-3'>📭</p>
					<p className='text-gray-500 dark:text-gray-400 text-lg font-medium'>Каналів не знайдено</p>
					<p className='text-gray-400 dark:text-gray-500 text-sm mt-1'>Спробуйте змінити фільтри</p>
				</div>
			) : (
				<div className='grid xl:grid-cols-3 md:grid-cols-2 gap-6'>
					{channels.map(channel => (
						<CatalogCard key={channel.id} channel={channel} />
					))}
				</div>
			)}

			{/* Pagination */}
			{totalPages > 1 && (
				<div className='flex justify-center items-center gap-1.5 mt-12'>
					<button
						onClick={() => setPage(p => Math.max(1, p - 1))}
						disabled={page === 1}
						className='w-10 h-10 rounded-xl flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-card transition-all disabled:opacity-30 disabled:cursor-not-allowed'
					>
						←
					</button>
					{Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
						<button
							key={p}
							onClick={() => setPage(p)}
							className={`w-10 h-10 rounded-xl font-semibold text-sm transition-all duration-300 ${
								p === page
									? 'bg-accent text-black shadow-md shadow-accent/30'
									: 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-card'
							}`}
						>
							{p}
						</button>
					))}
					<button
						onClick={() => setPage(p => Math.min(totalPages, p + 1))}
						disabled={page === totalPages}
						className='w-10 h-10 rounded-xl flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-card transition-all disabled:opacity-30 disabled:cursor-not-allowed'
					>
						→
					</button>
				</div>
			)}
		</section>
	);
};

export default CatalogPage;
