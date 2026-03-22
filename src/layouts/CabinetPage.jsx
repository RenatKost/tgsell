import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { channelsAPI, favoritesAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import CabinetCard from '../components/Cards/CabinetCard';
import CatalogCard from '../components/Cards/CatalogCard';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
	faList,
	faHeart,
	faPlus,
	faFilter,
} from '@fortawesome/free-solid-svg-icons';

const TABS = [
	{ text: 'Мої оголошення', value: 'my', icon: faList },
	{ text: 'Обране', value: 'favorites', icon: faHeart },
];

const STATUS_FILTERS = [
	{ text: 'Всі', value: null, dot: 'bg-gray-400' },
	{ text: 'Опубліковані', value: 'approved', dot: 'bg-green-500' },
	{ text: 'На модерації', value: 'pending', dot: 'bg-yellow-500' },
	{ text: 'Відхилені', value: 'rejected', dot: 'bg-red-500' },
];

const CabinetPage = () => {
	const { user } = useAuth();
	const [activeTab, setActiveTab] = useState(TABS[0]);
	const [activeFilter, setActiveFilter] = useState(STATUS_FILTERS[0]);
	const [channels, setChannels] = useState([]);
	const [favorites, setFavorites] = useState([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		const fetchData = async () => {
			setLoading(true);
			try {
				if (activeTab.value === 'my') {
					const params = { seller_id: user?.id };
					if (activeFilter.value) {
						params.status = activeFilter.value;
					}
					const { data } = await channelsAPI.getAll(params);
					setChannels(data.items || data);
				} else {
					const { data } = await favoritesAPI.getAll();
					setFavorites(data);
				}
			} catch (err) {
				console.error('Failed to load:', err);
			} finally {
				setLoading(false);
			}
		};
		if (user?.id) fetchData();
	}, [user?.id, activeTab, activeFilter]);

	const handleDelete = async (channelId) => {
		if (!confirm('Видалити оголошення?')) return;
		try {
			await channelsAPI.delete(channelId);
			setChannels(prev => prev.filter(c => c.id !== channelId));
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка видалення');
		}
	};

	const filteredChannels = activeFilter.value
		? channels.filter(c => c.status === activeFilter.value)
		: channels;

	const counts = {
		all: channels.length,
		approved: channels.filter(c => c.status === 'approved').length,
		pending: channels.filter(c => c.status === 'pending').length,
		rejected: channels.filter(c => c.status === 'rejected').length,
	};

	return (
		<section className='mt-28 mb-16 max-w-7xl mx-auto px-4'>
			{/* Header */}
			<div className='flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8'>
				<div>
					<h1 className='text-2xl md:text-3xl font-bold text-gray-800'>
						{user?.first_name ? `Привіт, ${user.first_name} 👋` : 'Особистий кабінет'}
					</h1>
					<p className='text-gray-500 mt-1'>Керуйте каналами та обраним</p>
				</div>
				<NavLink
					to='/sell'
					className='inline-flex items-center gap-2 bg-[#27ae60] text-white font-semibold py-3 px-6 rounded-xl shadow-lg shadow-green-200 hover:shadow-green-300 hover:bg-[#219a52] duration-300 whitespace-nowrap'
				>
					<FontAwesomeIcon icon={faPlus} />
					Продати канал
				</NavLink>
			</div>

			{/* Tabs */}
			<div className='flex gap-2 mb-6 border-b border-gray-200'>
				{TABS.map(tab => (
					<button
						key={tab.value}
						onClick={() => setActiveTab(tab)}
						className={`flex items-center gap-2 px-5 py-3 font-semibold text-sm duration-300 border-b-2 -mb-px ${
							activeTab.value === tab.value
								? 'border-[#3498db] text-[#3498db]'
								: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
						}`}
					>
						<FontAwesomeIcon icon={tab.icon} />
						{tab.text}
						{tab.value === 'favorites' && favorites.length > 0 && (
							<span className='bg-red-100 text-red-600 text-xs px-2 py-0.5 rounded-full'>{favorites.length}</span>
						)}
					</button>
				))}
			</div>

			{/* Content */}
			{activeTab.value === 'my' ? (
				<>
					{/* Status filter pills */}
					<div className='flex flex-wrap gap-2 mb-6'>
						{STATUS_FILTERS.map(f => (
							<button
								key={f.text}
								onClick={() => setActiveFilter(f)}
								className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium duration-300 ${
									f === activeFilter
										? 'bg-[#3498db] text-white shadow-md shadow-blue-200'
										: 'bg-white text-gray-600 border border-gray-200 hover:border-[#3498db] hover:text-[#3498db]'
								}`}
							>
								<span className={`w-2 h-2 rounded-full ${f === activeFilter ? 'bg-white' : f.dot}`} />
								{f.text}
								<span className={`text-xs ${f === activeFilter ? 'text-blue-100' : 'text-gray-400'}`}>
									{f.value === null ? counts.all : counts[f.value] || 0}
								</span>
							</button>
						))}
					</div>

					{loading ? (
						<div className='flex justify-center py-20'>
							<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
						</div>
					) : filteredChannels.length === 0 ? (
						<div className='text-center py-16 bg-white rounded-2xl border border-dashed border-gray-300'>
							<div className='text-5xl mb-4'>📢</div>
							<p className='text-lg font-semibold text-gray-700 mb-2'>
								{activeFilter.value ? 'Немає каналів з таким статусом' : 'У вас ще немає оголошень'}
							</p>
							<p className='text-gray-500 mb-6'>Додайте свій перший канал для продажу</p>
							<NavLink
								className='inline-flex items-center gap-2 font-bold bg-[#27ae60] text-white py-3 px-8 rounded-xl shadow-lg shadow-green-200 hover:bg-[#219a52] duration-300'
								to='/sell'
							>
								<FontAwesomeIcon icon={faPlus} />
								ПРОДАТИ КАНАЛ
							</NavLink>
						</div>
					) : (
						<div className='grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-6'>
							{filteredChannels.map(channel => (
								<CabinetCard key={channel.id} channel={channel} onDelete={handleDelete} />
							))}
						</div>
					)}
				</>
			) : (
				<>
					{loading ? (
						<div className='flex justify-center py-20'>
							<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
						</div>
					) : favorites.length === 0 ? (
						<div className='text-center py-16 bg-white rounded-2xl border border-dashed border-gray-300'>
							<div className='text-5xl mb-4'>❤️</div>
							<p className='text-lg font-semibold text-gray-700 mb-2'>У вас поки немає обраних каналів</p>
							<p className='text-gray-500 mb-6'>Додайте канали в обране з каталогу</p>
							<NavLink
								to='/catalog'
								className='inline-flex items-center gap-2 font-bold bg-[#3498db] text-white py-3 px-8 rounded-xl shadow-lg shadow-blue-200 hover:bg-[#2980b9] duration-300'
							>
								Перейти до каталогу
							</NavLink>
						</div>
					) : (
						<div className='grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-6'>
							{favorites.map(channel => (
								<CatalogCard key={channel.id} channel={channel} />
							))}
						</div>
					)}
				</>
			)}
		</section>
	);
};

export default CabinetPage;
