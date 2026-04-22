import { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { channelsAPI, favoritesAPI, dealsAPI, auctionsAPI, bundlesAPI } from '../services/api';
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
	faGavel,
	faUsers,
	faChevronRight,
} from '@fortawesome/free-solid-svg-icons';

const TABS = [
	{ text: 'Мої оголошення', value: 'my', icon: faList },
	{ text: 'Мої сетки', value: 'bundles', icon: faUsers },
	{ text: 'Мої аукціони', value: 'auctions', icon: faGavel },
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
	const navigate = useNavigate();
	const [activeTab, setActiveTab] = useState(TABS[0]);
	const [activeFilter, setActiveFilter] = useState(STATUS_FILTERS[0]);
	const [dealFilter, setDealFilter] = useState(DEAL_FILTERS[0]);
	const [channels, setChannels] = useState([]);
	const [favorites, setFavorites] = useState([]);
	const [deals, setDeals] = useState([]);
	const [myAuctions, setMyAuctions] = useState([]);
	const [myBundles, setMyBundles] = useState([]);
	const [loading, setLoading] = useState(true);

	// Auction creation modal
	const [showAuctionModal, setShowAuctionModal] = useState(false);
	const [availableChannels, setAvailableChannels] = useState([]);
	const [selectedChannelId, setSelectedChannelId] = useState(null);
	const [auctionForm, setAuctionForm] = useState({ start_price: '', bid_step: '10', duration_hours: '48' });
	const [auctionSubmitting, setAuctionSubmitting] = useState(false);
	const [auctionError, setAuctionError] = useState('');

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
				} else if (activeTab.value === 'bundles') {
					const { data } = await bundlesAPI.getAll({ seller_id: user?.id });
					setMyBundles(data.items || []);
				} else if (activeTab.value === 'auctions') {
					const [auctRes, chRes] = await Promise.all([
						auctionsAPI.getAll({ seller_id: user?.id }),
						channelsAPI.getAll({ seller_id: user?.id, status: 'approved' }),
					]);
					setMyAuctions(auctRes.data.items || []);
					setAvailableChannels((chRes.data.items || chRes.data || []));
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

	const handleOpenAuctionModal = () => {
		if (availableChannels.length === 0) {
			navigate('/sell');
			return;
		}
		setSelectedChannelId(null);
		setAuctionForm({ start_price: '', bid_step: '10', duration_hours: '48' });
		setAuctionError('');
		setShowAuctionModal(true);
	};

	const handleCreateAuction = async () => {
		if (!selectedChannelId) { setAuctionError('Оберіть канал'); return; }
		const sp = parseFloat(auctionForm.start_price);
		const bs = parseFloat(auctionForm.bid_step);
		if (!sp || sp <= 0) { setAuctionError('Вкажіть коректну стартову ціну'); return; }
		if (!bs || bs <= 0) { setAuctionError('Вкажіть коректний крок ставки'); return; }
		setAuctionError('');
		setAuctionSubmitting(true);
		try {
			await auctionsAPI.createFromChannel({
				channel_id: selectedChannelId,
				start_price: sp,
				bid_step: bs,
				duration_hours: parseInt(auctionForm.duration_hours),
			});
			setShowAuctionModal(false);
			// Refresh auctions
			const { data } = await auctionsAPI.getAll({ seller_id: user?.id });
			setMyAuctions(data.items || []);
		} catch (err) {
			setAuctionError(err.response?.data?.detail || 'Помилка створення аукціону');
		} finally {
			setAuctionSubmitting(false);
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
		<section className='pt-28 mb-16'>
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
						{tab.value === 'auctions' && myAuctions.length > 0 && (
							<span className='bg-orange-100 text-orange-600 text-xs px-2 py-0.5 rounded-full'>{myAuctions.length}</span>
						)}
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
			) : activeTab.value === 'bundles' ? (
				<>
					<div className='flex justify-end mb-6'>
						<NavLink to='/sell-bundle'
							className='inline-flex items-center gap-2 bg-accent text-black font-bold py-3 px-6 rounded-xl shadow-lg shadow-accent/30 hover:brightness-110 transition-all'>
							<FontAwesomeIcon icon={faPlus} />
							Продати сетку каналів
						</NavLink>
					</div>
					{loading ? (
						<div className='flex justify-center py-20'>
							<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-accent' />
						</div>
					) : myBundles.length === 0 ? (
						<div className='text-center py-16 bg-card rounded-2xl border border-dashed border-card-border'>
							<div className='text-5xl mb-4'>📡</div>
							<p className='text-gray-300 font-semibold text-lg mb-1'>У вас немає сеток</p>
							<p className='text-gray-500 text-sm mb-6'>Об'єднайте кілька каналів в одну пропозицію</p>
							<NavLink to='/sell-bundle'
								className='inline-flex items-center gap-2 bg-accent text-black font-bold py-2.5 px-6 rounded-xl hover:brightness-110 transition-all'>
								<FontAwesomeIcon icon={faPlus} /> Створити сетку
							</NavLink>
						</div>
					) : (
						<div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
							{myBundles.map(b => (
								<div key={b.id} className='bg-card border border-card-border rounded-xl p-5 shadow-neon'>
									<div className='flex items-start justify-between mb-2'>
										<div className='flex items-center gap-2'>
											<span className='text-accent font-bold'>📡</span>
											<span className='font-semibold text-white'>{b.name}</span>
										</div>
										<span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
											b.status === 'approved' ? 'bg-green-900/40 text-green-400' :
											b.status === 'rejected' ? 'bg-red-900/40 text-red-400' :
											b.status === 'sold' ? 'bg-gray-700 text-gray-400' :
											'bg-yellow-900/40 text-yellow-400'
										}`}>
											{b.status === 'approved' ? 'Схвалено' : b.status === 'rejected' ? 'Відхилено' : b.status === 'sold' ? 'Продано' : 'На модерації'}
										</span>
									</div>
									<div className='text-sm text-gray-400 mb-3'>
										{b.channel_count} каналів · <span className='text-accent font-semibold'>{b.price} USDT</span>
									</div>
									{b.rejection_reason && (
										<div className='text-xs text-red-400 mb-3 bg-red-900/20 rounded p-2'>
											Причина: {b.rejection_reason}
										</div>
									)}
									<div className='flex gap-2'>
										<NavLink to={`/bundle/${b.id}`}
											className='flex-1 text-center text-xs py-1.5 rounded-lg bg-card-inner text-gray-300 hover:text-accent border border-card-border transition-all'>
											Переглянути
										</NavLink>
										{b.status === 'pending' && (
											<button onClick={async () => {
												if (!confirm('Видалити сетку?')) return;
												try { await bundlesAPI.delete(b.id); setMyBundles(prev => prev.filter(x => x.id !== b.id)); }
												catch { alert('Помилка видалення'); }
											}} className='px-3 py-1.5 rounded-lg text-xs bg-red-900/30 text-red-400 hover:bg-red-900/50 border border-red-900 transition-all'>
												Видалити
											</button>
										)}
									</div>
								</div>
							))}
						</div>
					)}
				</>
			) : activeTab.value === 'auctions' ? (
				<>
					{/* Add auction button */}
					<div className='flex justify-end mb-6'>
						<button
							onClick={handleOpenAuctionModal}
							className='inline-flex items-center gap-2 bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white font-semibold py-3 px-6 rounded-xl shadow-lg shadow-orange-200 dark:shadow-orange-900/30 duration-300'
						>
							<FontAwesomeIcon icon={faGavel} />
							Виставити на аукціон
						</button>
					</div>

					{loading ? (
						<div className='flex justify-center py-20'>
							<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
						</div>
					) : myAuctions.length === 0 ? (
						<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300 dark:border-slate-600'>
							<div className='text-5xl mb-4'>🔥</div>
							<p className='text-lg font-semibold text-gray-700 dark:text-gray-200 mb-2'>У вас ще немає аукціонів</p>
							<p className='text-gray-500 dark:text-gray-400 mb-6'>
								{availableChannels.length > 0
									? 'Виставте один зі своїх каналів на аукціон'
									: 'Спершу додайте канал через форму, потім зможете виставити його на аукціон'}
							</p>
							<button
								onClick={handleOpenAuctionModal}
								className='inline-flex items-center gap-2 font-bold bg-orange-500 text-white py-3 px-8 rounded-xl shadow-lg shadow-orange-200 hover:bg-orange-600 duration-300'
							>
								<FontAwesomeIcon icon={faPlus} />
								{availableChannels.length > 0 ? 'Обрати канал' : 'Додати канал'}
							</button>
						</div>
					) : (
						<div className='grid gap-4'>
							{myAuctions.map(auction => {
								const isEnded = auction.status === 'ended';
								const isActive = auction.status === 'active';
								const endDate = auction.ends_at ? new Date(auction.ends_at) : null;
								const timeRemaining = endDate ? Math.max(0, endDate - Date.now()) : 0;
								const hoursLeft = Math.floor(timeRemaining / 3600000);
								const minsLeft = Math.floor((timeRemaining % 3600000) / 60000);
								const timeStr = timeRemaining > 0 ? `${hoursLeft}г ${minsLeft}хв` : 'Завершено';
								const statusColors = {
									active: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
									scheduled: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
									ended: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
									cancelled: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
								};
								const statusTexts = { active: 'Активний', scheduled: 'Запланований', ended: 'Завершений', cancelled: 'Скасований' };
								return (
									<div key={auction.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-5 hover:shadow-md duration-300'>
										<div className='flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3'>
											<div className='flex items-center gap-3'>
												{auction.channel_avatar ? (
													<img className='w-12 h-12 rounded-xl object-cover' src={auction.channel_avatar} alt='' />
												) : (
													<div className='w-12 h-12 rounded-xl bg-gradient-to-br from-orange-400 to-red-500 flex items-center justify-center text-lg font-bold text-white'>
														{(auction.channel_name || '?')[0]}
													</div>
												)}
												<div>
													<NavLink to={`/channel/${auction.channel_id}`} className='font-bold text-gray-800 dark:text-white hover:text-orange-500 duration-300'>
														{auction.channel_name || `Канал #${auction.channel_id}`}
													</NavLink>
													<p className='text-gray-500 dark:text-gray-400 text-sm'>
														Аукціон #{auction.id}
													</p>
												</div>
											</div>
											<div className='flex items-center gap-3'>
												<span className={`text-xs px-3 py-1 rounded-full font-semibold ${statusColors[auction.status] || statusColors.active}`}>
													{statusTexts[auction.status] || auction.status}
												</span>
												{isActive && (
													<span className='text-xs px-3 py-1 rounded-full font-medium bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300'>
														⏱ {timeStr}
													</span>
												)}
											</div>
										</div>
										<div className='grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm'>
											<div className='bg-orange-50 dark:bg-orange-900/20 p-3 rounded-xl'>
												<span className='font-semibold text-orange-600'>{auction.current_price} USDT</span>
												<p className='text-gray-400 dark:text-gray-500 text-xs mt-0.5'>поточна ціна</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<span className='font-semibold dark:text-gray-200'>{auction.start_price} USDT</span>
												<p className='text-gray-400 dark:text-gray-500 text-xs mt-0.5'>стартова ціна</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<span className='font-semibold dark:text-gray-200'>{auction.bid_step} USDT</span>
												<p className='text-gray-400 dark:text-gray-500 text-xs mt-0.5'>крок ставки</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<span className='font-semibold dark:text-gray-200'>{auction.bid_count}</span>
												<p className='text-gray-400 dark:text-gray-500 text-xs mt-0.5'>ставок</p>
											</div>
										</div>
									</div>
								);
							})}
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

			{/* Auction creation modal */}
			{showAuctionModal && (
				<div
					className='fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm'
					onClick={() => setShowAuctionModal(false)}
				>
					<div
						className='bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden'
						onClick={e => e.stopPropagation()}
					>
						{/* Header */}
						<div className='bg-gradient-to-r from-orange-500 to-red-500 px-6 py-5 text-white'>
							<h3 className='text-lg font-bold'>Виставити на аукціон</h3>
							<p className='text-sm text-white/80 mt-1'>
								{selectedChannelId ? 'Вкажіть параметри аукціону' : 'Оберіть канал зі списку'}
							</p>
						</div>

						<div className='p-6'>
							{!selectedChannelId ? (
								/* Step 1: Select channel */
								<div className='space-y-2 max-h-[360px] overflow-y-auto'>
									{availableChannels.map(ch => (
										<button
											key={ch.id}
											onClick={() => setSelectedChannelId(ch.id)}
											className='w-full flex items-center gap-3 p-3 rounded-xl border border-gray-200 dark:border-slate-600 hover:border-orange-400 hover:bg-orange-50 dark:hover:bg-orange-900/10 transition-all text-left'
										>
											{ch.avatar_url ? (
												<img className='w-10 h-10 rounded-lg object-cover' src={ch.avatar_url} alt='' />
											) : (
												<div className='w-10 h-10 rounded-lg bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center text-sm font-bold text-white'>
													{ch.channel_name?.[0] || '?'}
												</div>
											)}
											<div className='flex-1 min-w-0'>
												<p className='font-semibold text-gray-800 dark:text-white truncate text-sm'>{ch.channel_name}</p>
												<div className='flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400'>
													<span><FontAwesomeIcon icon={faUsers} className='mr-1' />{ch.subscribers_count?.toLocaleString('uk-UA') || '0'}</span>
													<span>{ch.price} USDT</span>
												</div>
											</div>
											<FontAwesomeIcon icon={faChevronRight} className='text-gray-300 dark:text-gray-600' />
										</button>
									))}
								</div>
							) : (
								/* Step 2: Auction params */
								<div className='space-y-4'>
									{/* Selected channel preview */}
									{(() => {
										const ch = availableChannels.find(c => c.id === selectedChannelId);
										return ch ? (
											<div className='flex items-center gap-3 p-3 bg-orange-50 dark:bg-orange-900/10 rounded-xl border border-orange-200 dark:border-orange-800/30'>
												{ch.avatar_url ? (
													<img className='w-10 h-10 rounded-lg object-cover' src={ch.avatar_url} alt='' />
												) : (
													<div className='w-10 h-10 rounded-lg bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center text-sm font-bold text-white'>
														{ch.channel_name?.[0] || '?'}
													</div>
												)}
												<div className='flex-1 min-w-0'>
													<p className='font-semibold text-gray-800 dark:text-white text-sm truncate'>{ch.channel_name}</p>
													<p className='text-xs text-gray-500 dark:text-gray-400'>{ch.subscribers_count?.toLocaleString('uk-UA')} підписників</p>
												</div>
												<button onClick={() => setSelectedChannelId(null)} className='text-xs text-orange-500 hover:text-orange-700 font-medium'>
													Змінити
												</button>
											</div>
										) : null;
									})()}

									<div>
										<label className='text-sm font-medium text-gray-600 dark:text-gray-400 mb-1.5 block'>Стартова ціна (USDT)</label>
										<input
											type='number'
											value={auctionForm.start_price}
											onChange={e => setAuctionForm(p => ({ ...p, start_price: e.target.value }))}
											className='w-full border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-3 text-sm bg-gray-50/50 dark:bg-slate-700/50 dark:text-white focus:border-orange-400 focus:ring-4 focus:ring-orange-50 dark:focus:ring-orange-900/30 transition-all'
											placeholder='100'
											min='1'
										/>
									</div>

									<div>
										<label className='text-sm font-medium text-gray-600 dark:text-gray-400 mb-1.5 block'>Крок ставки (USDT)</label>
										<input
											type='number'
											value={auctionForm.bid_step}
											onChange={e => setAuctionForm(p => ({ ...p, bid_step: e.target.value }))}
											className='w-full border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-3 text-sm bg-gray-50/50 dark:bg-slate-700/50 dark:text-white focus:border-orange-400 focus:ring-4 focus:ring-orange-50 dark:focus:ring-orange-900/30 transition-all'
											placeholder='10'
											min='1'
										/>
									</div>

									<div>
										<label className='text-sm font-medium text-gray-600 dark:text-gray-400 mb-1.5 block'>Тривалість</label>
										<select
											value={auctionForm.duration_hours}
											onChange={e => setAuctionForm(p => ({ ...p, duration_hours: e.target.value }))}
											className='w-full border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-3 text-sm bg-gray-50/50 dark:bg-slate-700/50 dark:text-white focus:border-orange-400 focus:ring-4 focus:ring-orange-50 dark:focus:ring-orange-900/30 transition-all'
										>
											<option value='24'>24 години</option>
											<option value='48'>48 годин</option>
											<option value='72'>72 години</option>
											<option value='168'>7 днів</option>
										</select>
									</div>

									<p className='text-xs text-gray-400 dark:text-gray-500'>
										💡 Аукціон триватиме до завершення часу або поки ви не закриєте лот за останньою ціною
									</p>
								</div>
							)}

							{auctionError && (
								<div className='flex items-center gap-2 bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800 text-red-600 dark:text-red-400 text-sm px-4 py-3 rounded-xl mt-4'>
									<svg className='w-4 h-4 flex-shrink-0' fill='currentColor' viewBox='0 0 20 20'>
										<path fillRule='evenodd' d='M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z' clipRule='evenodd' />
									</svg>
									{auctionError}
								</div>
							)}

							{/* Actions */}
							<div className='flex gap-3 mt-5'>
								<button
									onClick={() => setShowAuctionModal(false)}
									className='flex-1 py-3 rounded-xl text-sm font-semibold text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 transition-all'
								>
									Скасувати
								</button>
								{selectedChannelId && (
									<button
										onClick={handleCreateAuction}
										disabled={auctionSubmitting}
										className='flex-[2] py-3 rounded-xl text-sm font-semibold bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white shadow-md hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2'
									>
										{auctionSubmitting ? (
											<svg className='animate-spin w-5 h-5' fill='none' viewBox='0 0 24 24'>
												<circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4' />
												<path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z' />
											</svg>
										) : (
											<>🔥 Створити аукціон</>
										)}
									</button>
								)}
							</div>
						</div>
					</div>
				</div>
			)}
		</section>
	);
};

export default CabinetPage;
