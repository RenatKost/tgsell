import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { channelsAPI, favoritesAPI, dealsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import CabinetCard from '../components/Cards/CabinetCard';
import CatalogCard from '../components/Cards/CatalogCard';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
	faList,
	faHeart,
	faPlus,
	faFilter,
	faHandshake,
	faArrowRight,
} from '@fortawesome/free-solid-svg-icons';

const TABS = [
	{ text: 'Мої оголошення', value: 'my', icon: faList },
	{ text: 'Мої угоди', value: 'deals', icon: faHandshake },
	{ text: 'Обране', value: 'favorites', icon: faHeart },
];

const STATUS_FILTERS = [
	{ text: 'Всі', value: null, dot: 'bg-gray-400' },
	{ text: 'Опубліковані', value: 'approved', dot: 'bg-green-500' },
	{ text: 'На модерації', value: 'pending', dot: 'bg-yellow-500' },
	{ text: 'Відхилені', value: 'rejected', dot: 'bg-red-500' },
];

const DEAL_STATUS_LABELS = {
	created: { text: 'Очікує оплати', color: 'bg-yellow-100 text-yellow-700' },
	payment_pending: { text: 'Очікує оплати', color: 'bg-yellow-100 text-yellow-700' },
	paid: { text: 'Оплачено', color: 'bg-blue-100 text-blue-700' },
	channel_transferring: { text: 'Передача каналу', color: 'bg-indigo-100 text-indigo-700' },
	completed: { text: 'Завершено', color: 'bg-green-100 text-green-700' },
	disputed: { text: 'Спір', color: 'bg-red-100 text-red-700' },
	cancelled: { text: 'Скасовано', color: 'bg-gray-100 text-gray-600' },
};

const DEAL_FILTERS = [
	{ text: 'Активні', value: 'active', dot: 'bg-blue-500' },
	{ text: 'Завершені', value: 'completed', dot: 'bg-green-500' },
	{ text: 'Спірні', value: 'disputed', dot: 'bg-red-500' },
	{ text: 'Скасовані', value: 'cancelled', dot: 'bg-gray-400' },
	{ text: 'Всі', value: null, dot: 'bg-gray-400' },
];

const CabinetPage = () => {
	const { user } = useAuth();
	const [activeTab, setActiveTab] = useState(TABS[0]);
	const [activeFilter, setActiveFilter] = useState(STATUS_FILTERS[0]);
	const [dealFilter, setDealFilter] = useState(DEAL_FILTERS[0]);
	const [channels, setChannels] = useState([]);
	const [favorites, setFavorites] = useState([]);
	const [deals, setDeals] = useState([]);
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
				} else if (activeTab.value === 'deals') {
					const { data } = await dealsAPI.getMy();
					setDeals(Array.isArray(data) ? data : []);
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

	const ACTIVE_STATUSES = ['created', 'payment_pending', 'paid', 'channel_transferring'];
	const filteredDeals = dealFilter.value === null
		? deals
		: dealFilter.value === 'active'
			? deals.filter(d => ACTIVE_STATUSES.includes(d.status))
			: deals.filter(d => d.status === dealFilter.value);

	const dealCounts = {
		active: deals.filter(d => ACTIVE_STATUSES.includes(d.status)).length,
		completed: deals.filter(d => d.status === 'completed').length,
		disputed: deals.filter(d => d.status === 'disputed').length,
		cancelled: deals.filter(d => d.status === 'cancelled').length,
		all: deals.length,
	};

	return (
		<section className='mt-28 mb-16 max-w-7xl mx-auto px-4'>
			{/* Header */}
			<div className='flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8'>
				<div>
					<h1 className='text-2xl md:text-3xl font-bold text-gray-800 dark:text-white'>
						{user?.first_name ? `Привіт, ${user.first_name} 👋` : 'Особистий кабінет'}
					</h1>
					<p className='text-gray-500 dark:text-gray-400 mt-1'>Керуйте каналами та обраним</p>
				</div>
				<NavLink
					to='/sell'
					className='inline-flex items-center gap-2 bg-[#27ae60] text-white font-semibold py-3 px-6 rounded-xl shadow-lg shadow-green-200 dark:shadow-green-900/30 hover:shadow-green-300 hover:bg-[#219a52] duration-300 whitespace-nowrap'
				>
					<FontAwesomeIcon icon={faPlus} />
					Продати канал
				</NavLink>
			</div>

			{/* Tabs */}
			<div className='flex gap-2 mb-6 border-b border-gray-200 dark:border-slate-700'>
				{TABS.map(tab => (
					<button
						key={tab.value}
						onClick={() => setActiveTab(tab)}
						className={`flex items-center gap-2 px-5 py-3 font-semibold text-sm duration-300 border-b-2 -mb-px ${
							activeTab.value === tab.value
								? 'border-[#3498db] text-[#3498db]'
							: 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-slate-600'
						}`}
					>
						<FontAwesomeIcon icon={tab.icon} />
						{tab.text}
						{tab.value === 'deals' && deals.length > 0 && (
							<span className='bg-blue-100 text-blue-600 text-xs px-2 py-0.5 rounded-full'>{deals.length}</span>
						)}
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
										? 'bg-[#3498db] text-white shadow-md shadow-blue-200 dark:shadow-blue-900/30'
										: 'bg-white dark:bg-slate-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-slate-600 hover:border-[#3498db] hover:text-[#3498db]'
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
						<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300 dark:border-slate-600'>
							<div className='text-5xl mb-4'>📢</div>
							<p className='text-lg font-semibold text-gray-700 dark:text-gray-200 mb-2'>
								{activeFilter.value ? 'Немає каналів з таким статусом' : 'У вас ще немає оголошень'}
							</p>
							<p className='text-gray-500 dark:text-gray-400 mb-6'>Додайте свій перший канал для продажу</p>
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
			) : activeTab.value === 'deals' ? (
				<>
					{/* Deal filter pills */}
					<div className='flex flex-wrap gap-2 mb-6'>
						{DEAL_FILTERS.map(f => (
							<button
								key={f.text}
								onClick={() => setDealFilter(f)}
								className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium duration-300 ${
									f === dealFilter
									? 'bg-[#3498db] text-white shadow-md shadow-blue-200 dark:shadow-blue-900/30'
									: 'bg-white dark:bg-slate-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-slate-600 hover:border-[#3498db] hover:text-[#3498db]'
								}`}
							>
								<span className={`w-2 h-2 rounded-full ${f === dealFilter ? 'bg-white' : f.dot}`} />
								{f.text}
								<span className={`text-xs ${f === dealFilter ? 'text-blue-100' : 'text-gray-400'}`}>
									{f.value === null ? dealCounts.all : dealCounts[f.value] || 0}
								</span>
							</button>
						))}
					</div>

					{loading ? (
						<div className='flex justify-center py-20'>
							<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
						</div>
					) : filteredDeals.length === 0 ? (
						<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300 dark:border-slate-600'>
							<div className='text-5xl mb-4'>🤝</div>
							<p className='text-lg font-semibold text-gray-700 dark:text-gray-200 mb-2'>
								{dealFilter.value ? 'Немає угод з таким статусом' : 'У вас ще немає угод'}
							</p>
							<p className='text-gray-500 dark:text-gray-400 mb-6'>Перейдіть до каталогу, щоб купити канал</p>
							<NavLink
								to='/catalog'
								className='inline-flex items-center gap-2 font-bold bg-[#3498db] text-white py-3 px-8 rounded-xl shadow-lg shadow-blue-200 hover:bg-[#2980b9] duration-300'
							>
								Перейти до каталогу
							</NavLink>
						</div>
					) : (
						<div className='grid gap-4'>
							{filteredDeals.map(deal => {
								const statusInfo = DEAL_STATUS_LABELS[deal.status] || DEAL_STATUS_LABELS.created;
								const isBuyer = user?.id === deal.buyer_id;
								return (
									<NavLink
										key={deal.id}
										to={`/deal/${deal.id}`}
											className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-5 hover:shadow-md duration-300 block group'
										>
											<div className='flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3'>
												<div>
													<h3 className='font-bold text-gray-800 dark:text-white text-lg'>
														{deal.channel_name || `Канал #${deal.channel_id}`}
													</h3>
													<p className='text-gray-500 dark:text-gray-400 text-sm'>
													Угода #{deal.id} · {isBuyer ? 'Ви покупець' : 'Ви продавець'}
												</p>
											</div>
											<div className='flex items-center gap-3'>
												<span className={`text-xs px-3 py-1 rounded-full font-semibold ${statusInfo.color}`}>
													{statusInfo.text}
												</span>
												<FontAwesomeIcon icon={faArrowRight} className='text-gray-300 group-hover:text-[#3498db] duration-300' />
											</div>
										</div>
										<div className='grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm'>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<span className='font-semibold text-green-600'>{deal.amount_usdt} USDT</span>
												<p className='text-gray-400 dark:text-gray-500 text-xs mt-0.5'>сума</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<span className='font-semibold dark:text-gray-200'>{deal.service_fee} USDT</span>
												<p className='text-gray-400 dark:text-gray-500 text-xs mt-0.5'>комісія</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<span className='font-semibold dark:text-gray-200'>{isBuyer ? (deal.seller_name || 'Продавець') : (deal.buyer_name || 'Покупець')}</span>
												<p className='text-gray-400 dark:text-gray-500 text-xs mt-0.5'>{isBuyer ? 'продавець' : 'покупець'}</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<span className='font-semibold dark:text-gray-200'>{new Date(deal.created_at).toLocaleDateString('uk-UA')}</span>
												<p className='text-gray-400 dark:text-gray-500 text-xs mt-0.5'>дата</p>
											</div>
										</div>
										{deal.dispute_reason && (
											<p className='mt-3 text-sm bg-red-50 text-red-700 p-3 rounded-xl'>
												<span className='font-semibold'>Причина спору:</span> {deal.dispute_reason}
											</p>
										)}
									</NavLink>
								);
							})}
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
						<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300 dark:border-slate-600'>
							<div className='text-5xl mb-4'>❤️</div>
							<p className='text-lg font-semibold text-gray-700 dark:text-gray-200 mb-2'>У вас поки немає обраних каналів</p>
							<p className='text-gray-500 dark:text-gray-400 mb-6'>Додайте канали в обране з каталогу</p>
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
