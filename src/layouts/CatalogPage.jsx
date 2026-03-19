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
		<section className='my-28'>
			<h1 className='uppercase leading-normal lg:pl-[3%] tracking-widest font-bold text-2xl text-center sm:text-start md:text-4xl text-[#3498db] mb-8'>
				КУПИТИ TELEGRAM-КАНАЛ
			</h1>
			<div className='lg:p-10 p-0'>
				{/* Search & Filters */}
				<div className='flex flex-col md:flex-row gap-4 mb-8'>
					<input
						type='text'
						placeholder='Пошук каналу...'
						value={search}
						onChange={(e) => { setSearch(e.target.value); setPage(1); }}
						className='flex-1 border border-gray-300 px-4 py-3 rounded-md focus:border-[#3498db]'
					/>
					<select
						value={category}
						onChange={(e) => { setCategory(e.target.value); setPage(1); }}
						className='border border-gray-300 px-4 py-3 rounded-md focus:border-[#3498db]'
					>
						<option value=''>Всі категорії</option>
						{categoryOptions.map(opt => (
							<option key={opt.label} value={opt.label}>{opt.label}</option>
						))}
					</select>
					<select
						value={sortBy}
						onChange={(e) => { setSortBy(e.target.value); setPage(1); }}
						className='border border-gray-300 px-4 py-3 rounded-md focus:border-[#3498db]'
					>
						<option value='newest'>Нові</option>
						<option value='price_asc'>Ціна ↑</option>
						<option value='price_desc'>Ціна ↓</option>
						<option value='subscribers_desc'>Підписники ↓</option>
					</select>
				</div>

				<h3 className='font-bold mb-6 text-xl'>
					{loading ? 'Завантаження...' : `Всього каналів: ${channels.length}`}
				</h3>

				{loading ? (
					<div className='flex justify-center py-12'>
						<div className='animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#3498db]'></div>
					</div>
				) : channels.length === 0 ? (
					<div className='text-center py-12'>
						<p className='text-gray-500 text-lg'>Каналів не знайдено</p>
					</div>
				) : (
					<div className='grid xl:grid-cols-3 md:justify-center md:grid-cols-2 gap-10 lg:justify-between'>
						{channels.map(channel => (
							<CatalogCard key={channel.id} channel={channel} />
						))}
					</div>
				)}

				{/* Pagination */}
				{totalPages > 1 && (
					<div className='flex justify-center gap-2 mt-10'>
						{Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
							<button
								key={p}
								onClick={() => setPage(p)}
								className={`px-4 py-2 rounded-md font-bold duration-300 ${
									p === page
										? 'bg-[#3498db] text-white'
										: 'bg-white shadow-md hover:bg-gray-50'
								}`}
							>
								{p}
							</button>
						))}
					</div>
				)}
			</div>
		</section>
	);
};

export default CatalogPage;
