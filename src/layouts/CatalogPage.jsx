import { useEffect, useState } from 'react';
import CatalogCard from '../components/Cards/CatalogCard';
import { channelsAPI } from '../services/api';
import { options as categoryOptions } from '../components/Main/Calculator';

const CatalogPage = () => {
	const [channels, setChannels] = useState([]);
	const [loading, setLoading] = useState(true);
	const [search, setSearch] = useState('');
	const [category, setCategory] = useState('');
	const [sortBy, setSortBy] = useState('newest');
	const [page, setPage] = useState(1);
	const [totalPages, setTotalPages] = useState(1);

	useEffect(() => {
		const fetchChannels = async () => {
			setLoading(true);
			try {
				const { data } = await channelsAPI.getAll({
					search,
					category,
					sort: sortBy,
					page,
					limit: 12,
				});
				setChannels(data.items || data);
				setTotalPages(data.total_pages || 1);
			} catch (err) {
				console.error('Failed to load channels:', err);
				setChannels([]);
			} finally {
				setLoading(false);
			}
		};
		fetchChannels();
	}, [search, category, sortBy, page]);

	return (
		<section className='pt-28 pb-10'>
			{/* Hero header */}
			<div className='mb-8'>
				<h1 className='font-bold text-2xl text-center sm:text-start md:text-4xl text-gray-900 dark:text-white mb-2'>
					Каталог каналів
				</h1>
				<p className='text-gray-500 dark:text-gray-400 text-center sm:text-start text-sm md:text-base'>
					Знайдіть ідеальний Telegram-канал для покупки
				</p>
			</div>

			<div>
				{/* Search & Filters */}
				<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-4 md:p-5 mb-8'>
					<div className='flex flex-col md:flex-row gap-3'>
						<div className='relative flex-1'>
							<span className='absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 text-sm'>🔍</span>
							<input
								type='text'
								placeholder='Пошук каналу...'
								value={search}
								onChange={(e) => { setSearch(e.target.value); setPage(1); }}
								className='w-full border border-gray-200 dark:border-slate-600 pl-10 pr-4 py-3 rounded-xl focus:border-[#3498db] focus:ring-2 focus:ring-blue-50 dark:focus:ring-blue-900/30 focus:outline-none transition-all bg-gray-50 dark:bg-slate-700 dark:text-white dark:placeholder-gray-400'
							/>
						</div>
						<select
							value={category}
							onChange={(e) => { setCategory(e.target.value); setPage(1); }}
							className='border border-gray-200 dark:border-slate-600 px-4 py-3 rounded-xl focus:border-[#3498db] focus:ring-2 focus:ring-blue-50 dark:focus:ring-blue-900/30 focus:outline-none transition-all bg-gray-50 dark:bg-slate-700 dark:text-white cursor-pointer'
						>
							<option value=''>Всі категорії</option>
							{categoryOptions.map(opt => (
								<option key={opt.label} value={opt.label}>{opt.label}</option>
							))}
						</select>
						<select
							value={sortBy}
							onChange={(e) => { setSortBy(e.target.value); setPage(1); }}
							className='border border-gray-200 dark:border-slate-600 px-4 py-3 rounded-xl focus:border-[#3498db] focus:ring-2 focus:ring-blue-50 dark:focus:ring-blue-900/30 focus:outline-none transition-all bg-gray-50 dark:bg-slate-700 dark:text-white cursor-pointer'
						>
							<option value='newest'>Нові</option>
							<option value='price_asc'>Ціна ↑</option>
							<option value='price_desc'>Ціна ↓</option>
							<option value='subscribers_desc'>Підписники ↓</option>
						</select>
					</div>
				</div>

				{/* Results count */}
				{!loading && channels.length > 0 && (
					<p className='text-gray-400 text-sm mb-6'>
						Знайдено: {channels.length}
					</p>
				)}

				{loading ? (
					<div className='flex justify-center py-20'>
						<div className='animate-spin rounded-full h-10 w-10 border-2 border-gray-200 dark:border-slate-600 border-t-[#3498db]'></div>
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
							className='w-10 h-10 rounded-xl flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-800 transition-all disabled:opacity-30 disabled:cursor-not-allowed'
						>
							←
						</button>
						{Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
							<button
								key={p}
								onClick={() => setPage(p)}
								className={`w-10 h-10 rounded-xl font-semibold text-sm transition-all duration-300 ${
									p === page
										? 'bg-[#3498db] text-white shadow-md shadow-blue-200 dark:shadow-blue-900/30'
										: 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-800'
								}`}
							>
								{p}
							</button>
						))}
						<button
							onClick={() => setPage(p => Math.min(totalPages, p + 1))}
							disabled={page === totalPages}
							className='w-10 h-10 rounded-xl flex items-center justify-center text-gray-400 hover:bg-gray-100 dark:hover:bg-slate-800 transition-all disabled:opacity-30 disabled:cursor-not-allowed'
						>
							→
						</button>
					</div>
				)}
			</div>
		</section>
	);
};

export default CatalogPage;
