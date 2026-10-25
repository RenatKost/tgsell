import { fmtUsdt, fmtNum, MAX_PRICE_USDT, MAX_PRICE_HINT } from '../utils/money';
import { useCallback, useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { channelsAPI, favoritesAPI, dealsAPI, auctionsAPI, bundlesAPI, meAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import CabinetCard from '../components/Cards/CabinetCard';
import CatalogCard from '../components/Cards/CatalogCard';
import AlertBotHint from '../components/Services/AlertBotHint';
import SavedSearches from '../components/Cabinet/SavedSearches';
import BundleBalanceEditor from '../components/Balance/BundleBalanceEditor';
import BalanceBadges from '../components/Balance/BalanceBadges';
import {
	Badge, LISTING_STATUS, DEAL_STATUS, AUCTION_STATUS, dealNextStep, Spinner, EmptyState, ErrorState,
	LinkButton, FilterChips, surface, inner, btnPrimary, btnSecondary, btnDanger,
} from '../components/Cabinet/ui';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import useReveal from '../hooks/useReveal';
import './escrow.css';
import {
	faList,
	faHeart,
	faPlus,
	faHandshake,
	faArrowRight,
	faGavel,
	faUsers,
	faChevronRight,
	faBell,
} from '@fortawesome/free-solid-svg-icons';

const TABS = [
	{ text: 'Мої оголошення', value: 'my', icon: faList },
	{ text: 'Мої сітки', value: 'bundles', icon: faUsers },
	{ text: 'Мої аукціони', value: 'auctions', icon: faGavel },
	{ text: 'Мої угоди', value: 'deals', icon: faHandshake },
	{ text: 'Обране', value: 'favorites', icon: faHeart },
	{ text: 'Збережені пошуки', value: 'saved', icon: faBell },
];

const STATUS_FILTERS = [
	{ text: 'Усі', value: null, dot: 'bg-gray-400' },
	{ text: 'Опубліковані', value: 'approved', dot: 'bg-green-500' },
	{ text: 'На модерації', value: 'pending', dot: 'bg-yellow-500' },
	{ text: 'Відхилені', value: 'rejected', dot: 'bg-red-500' },
];

const DEAL_FILTERS = [
	{ text: 'Активні', value: 'active', dot: 'bg-blue-500' },
	{ text: 'Завершені', value: 'completed', dot: 'bg-green-500' },
	{ text: 'Спірні', value: 'disputed', dot: 'bg-red-500' },
	{ text: 'Скасовані', value: 'cancelled', dot: 'bg-gray-400' },
	{ text: 'Усі', value: null, dot: 'bg-gray-400' },
];

const CabinetPage = () => {
	const { user, favoriteIds } = useAuth();
	const navigate = useNavigate();
	const [unread, setUnread] = useState({});
	useReveal();
	const [activeTab, setActiveTab] = useState(TABS[0]);
	const [activeFilter, setActiveFilter] = useState(STATUS_FILTERS[0]);
	const [dealFilter, setDealFilter] = useState(DEAL_FILTERS[0]);
	const [channels, setChannels] = useState([]);
	const [favorites, setFavorites] = useState([]);
	const [deals, setDeals] = useState([]);
	const [myAuctions, setMyAuctions] = useState([]);
	const [myBundles, setMyBundles] = useState([]);
	const [balanceBundle, setBalanceBundle] = useState(null); // Task 32
	const [loading, setLoading] = useState(true);
	const [loadError, setLoadError] = useState(false);
	const [reloadKey, setReloadKey] = useState(0);
	// Tab counters: loaded once on open via GET /api/me/counts, refreshed after actions.
	// null = still loading (skeleton). Zero rule: every tab shows «0» explicitly.
	const [tabCounts, setTabCounts] = useState(null);
	const refreshCounts = useCallback(() => {
		if (!user?.id) return;
		meAPI.counts().then(({ data }) => setTabCounts(data)).catch(() => {
			setTabCounts(prev => prev || {});
		});
	}, [user?.id]);

	// On open, on every tab switch, and when favourites change anywhere (♡ toggle).
	useEffect(() => { refreshCounts(); }, [refreshCounts, activeTab, favoriteIds]);
	useEffect(() => {
		const onFocus = () => { if (document.visibilityState === 'visible') refreshCounts(); };
		document.addEventListener('visibilitychange', onFocus);
		return () => document.removeEventListener('visibilitychange', onFocus);
	}, [refreshCounts]);

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
			setLoadError(false);
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
					dealsAPI.chatUnread().then(r => setUnread(r.data.unread || {})).catch(() => {});
				} else if (activeTab.value === 'saved') {
					// loaded by <SavedSearches onChange={refreshCounts} />
				} else {
					const { data } = await favoritesAPI.getAll();
					setFavorites(data);
				}
			} catch (err) {
				console.error('Failed to load:', err);
				setLoadError(true);
			} finally {
				setLoading(false);
			}
		};
		if (user?.id) fetchData();
	}, [user?.id, activeTab, activeFilter, reloadKey]);

	const handleDelete = async (channelId) => {
		if (!confirm('Видалити оголошення?')) return;
		try {
			await channelsAPI.delete(channelId);
			setChannels(prev => prev.filter(c => c.id !== channelId));
			refreshCounts();
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
		if (sp > MAX_PRICE_USDT || bs > MAX_PRICE_USDT) { setAuctionError(MAX_PRICE_HINT); return; }
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
			refreshCounts();
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

	const ACTIVE_STATUSES = ['created', 'payment_pending', 'paid', 'channel_transferring', 'awaiting_payout', 'payout_in_progress'];
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

	const COUNT_KEY = { my: 'listings', bundles: 'bundles', auctions: 'auctions', deals: 'deals', favorites: 'favorites', saved: 'saved_searches' };
	// null → skeleton; number → shown (0 included). Unknown (request failed) → hidden.
	const tabCount = (v) => {
		if (tabCounts === null) return null;
		const n = tabCounts[COUNT_KEY[v]];
		return typeof n === 'number' ? n : undefined;
	};

	const renderBody = (empty, list) => (loading ? <Spinner /> : loadError ? <ErrorState onRetry={() => setReloadKey(k => k + 1)} /> : empty ? empty : list);

	return (
		<section className='esc-page relative isolate pt-24 sm:pt-28 mb-16'>
			<div className='esc-bg esc-bg-short -z-10' aria-hidden='true'><span className='esc-grid' /><span className='esc-blob esc-blob-1' /><span className='esc-blob esc-blob-2' /></div>
			{/* Header */}
			<div className='esc-reveal flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6 sm:mb-8'>
				<div className='min-w-0'>
					<h1 className='esc-title text-[1.75rem] sm:text-4xl font-extrabold tracking-tight leading-tight break-words'>
						{user?.first_name ? <>{`Привіт, ${user.first_name} `}<span className='esc-emoji'>👋</span></> : 'Особистий кабінет'}
					</h1>
					<p className='text-sm sm:text-base text-gray-500 dark:text-gray-400 mt-2 leading-relaxed'>
						Ваші оголошення, угоди та збережені пошуки в одному місці
					</p>
				</div>
				<NavLink to='/sell' className={`${btnPrimary} esc-btn w-full sm:w-auto shadow-neon`}>
					<FontAwesomeIcon icon={faPlus} />
					Виставити канал
				</NavLink>
			</div>

			<div className='esc-reveal' style={{ '--d': '80ms' }}><AlertBotHint className='mb-6' /></div>

			{/* Tabs: 3×2 grid on phones (all visible, no hidden scroll), underline row from md */}
			<div role='tablist' aria-label='Розділи кабінету'
				className='esc-tabs grid grid-cols-3 gap-2 mb-6 md:flex md:gap-1'>
				{TABS.map(tab => {
					const on = activeTab.value === tab.value;
					const n = tabCount(tab.value);
					return (
						<button
							key={tab.value}
							type='button'
							role='tab'
							aria-selected={on}
							onClick={() => setActiveTab(tab)}
							className={`relative flex flex-col md:flex-row items-center justify-center gap-1 md:gap-2 min-h-[56px] md:min-h-[48px] px-2 md:px-4 rounded-xl text-xs md:text-sm font-semibold text-center leading-tight transition-all border ${
								on
									? 'bg-accent/10 border-accent text-gray-900 dark:text-accent'
									: 'bg-white dark:bg-card border-gray-200 dark:border-card-border text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-white md:bg-transparent md:dark:bg-transparent md:border-transparent md:hover:bg-accent/5'
							}`}
						>
							<FontAwesomeIcon icon={tab.icon} className='text-sm' />
							<span>{tab.text}</span>
							{n === null ? (
								<span data-testid='tab-count-skeleton' aria-hidden='true'
									className='absolute top-1 right-1 md:static w-6 h-5 rounded-full bg-gray-200 dark:bg-white/10 animate-pulse' />
							) : typeof n === 'number' && (
								<span data-testid='tab-count' aria-label={`${n}`}
									className={`absolute top-1 right-1 md:static min-w-[20px] h-5 px-1.5 inline-flex items-center justify-center rounded-full text-[11px] font-bold tabular-nums ${
										n > 0 ? 'bg-gray-100 dark:bg-white/10 text-gray-700 dark:text-gray-200' : 'bg-gray-50 dark:bg-white/5 text-gray-400 dark:text-gray-500'
									}`}>
									{n}
								</span>
							)}
						</button>
					);
				})}
			</div>

			{/* Content */}
			{activeTab.value === 'my' ? (
				<>
					<FilterChips items={STATUS_FILTERS} active={activeFilter} onChange={setActiveFilter}
						count={f => (f.value === null ? counts.all : counts[f.value] || 0)} />
					{renderBody(
						filteredChannels.length === 0 && (
							<EmptyState
								icon='📢'
								title={activeFilter.value ? 'Немає оголошень з таким статусом' : 'У вас ще немає оголошень'}
								text={activeFilter.value ? 'Оберіть інший фільтр або додайте новий канал.' : 'Додайте свій перший канал — після модерації він з’явиться в каталозі.'}
								action={<LinkButton to='/sell'><FontAwesomeIcon icon={faPlus} />Виставити канал</LinkButton>}
							/>
						),
						<div className='esc-cab-list grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4 sm:gap-5'>
							{filteredChannels.map(channel => (
								<CabinetCard key={channel.id} channel={channel} onDelete={handleDelete} />
							))}
						</div>,
					)}
				</>
			) : activeTab.value === 'bundles' ? (
				<>
					<div className='flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5'>
						<p className='text-sm text-gray-500 dark:text-gray-400'>Об’єднайте кілька каналів в одну пропозицію.</p>
						<LinkButton to='/sell-bundle' className='w-full sm:w-auto'><FontAwesomeIcon icon={faPlus} />Виставити сітку</LinkButton>
					</div>
					{renderBody(
						myBundles.length === 0 && (
							<EmptyState icon='📡' title='У вас ще немає сіток' text='Сітка — це кілька ваших каналів, які продаються разом за однією ціною.' />
						),
						<div className='grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5'>
							{myBundles.map(b => {
								const st = b.status === 'sold' ? LISTING_STATUS.sold : (LISTING_STATUS[b.status] || LISTING_STATUS.pending);
								return (
									<article key={b.id} className={`${surface} esc-card p-4 sm:p-5 flex flex-col`}>
										<div className='flex items-start justify-between gap-3 mb-2'>
											<h3 className='font-semibold text-gray-900 dark:text-white leading-snug break-words line-clamp-2 min-w-0'>
												<span aria-hidden='true' className='mr-1.5'>📡</span>{b.name}
											</h3>
											<Badge tone={st.tone} className='flex-shrink-0'>{st.text}</Badge>
										</div>
										<p className='text-sm text-gray-500 dark:text-gray-400 mb-3'>
											{b.channel_count} канал(ів) · <span className='text-gray-900 dark:text-accent font-bold'>{fmtUsdt(b.price)} USDT</span>
										</p>
										{(b.channels || []).some(c => Number(c.stars_balance || 0) > 0 || Number(c.ton_balance || 0) > 0) && (
											<ul className='mb-3 space-y-1.5'>
												{b.channels.map(c => (
													<li key={c.id} className='text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2 flex-wrap'>
														<span className='truncate max-w-full'>{c.channel_name}</span>
														<BalanceBadges stars={c.stars_balance} ton={c.ton_balance} size='xs' caption={false} />
													</li>
												))}
											</ul>
										)}
										{b.rejection_reason && (
											<p className='text-sm text-red-700 dark:text-red-300 mb-3 bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-900/40 rounded-xl px-3 py-2'>
												<span className='font-semibold'>Причина відхилення:</span> {b.rejection_reason}
											</p>
										)}
										<div className='flex flex-wrap gap-2 mt-auto pt-1'>
											<NavLink to={`/bundle/${b.id}`} className={`${btnSecondary} flex-1`}>Переглянути</NavLink>
											{b.status !== 'sold' && (
												<button type='button' onClick={() => setBalanceBundle(b)} className={btnSecondary}
													title='Баланс Stars/TON каналів (можна змінити, поки по сітці немає активної угоди)'>
													⭐ Баланс
												</button>
											)}
											{b.status === 'pending' && (
												<button type='button' onClick={async () => {
													if (!confirm('Видалити сітку?')) return;
													try { await bundlesAPI.delete(b.id); setMyBundles(prev => prev.filter(x => x.id !== b.id)); refreshCounts(); }
													catch { alert('Помилка видалення'); }
												}} className={btnDanger}>
													Видалити
												</button>
											)}
										</div>
									</article>
								);
							})}
						</div>,
					)}
					{balanceBundle && (
						<BundleBalanceEditor
							title={`Баланс каналів — «${balanceBundle.name}»`}
							channels={balanceBundle.channels || []}
							note='Змінити баланс можна, лише поки по сітці немає активної угоди.'
							onSave={async (channel_balances) => {
								const { data } = await bundlesAPI.updateBalances(balanceBundle.id, channel_balances);
								setMyBundles(prev => prev.map(x => (x.id === data.id ? { ...x, ...data } : x)));
							}}
							onClose={() => setBalanceBundle(null)}
						/>
					)}
				</>
			) : activeTab.value === 'auctions' ? (
				<>
					<div className='flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5'>
						<p className='text-sm text-gray-500 dark:text-gray-400'>Опубліковані канали можна виставити на аукціон.</p>
						<button type='button' onClick={handleOpenAuctionModal} className={`${btnPrimary} esc-btn w-full sm:w-auto`}>
							<FontAwesomeIcon icon={faGavel} />
							Виставити на аукціон
						</button>
					</div>
					{renderBody(
						myAuctions.length === 0 && (
							<EmptyState
								icon='🔥'
								title='У вас ще немає аукціонів'
								text={availableChannels.length > 0
									? 'Виставте один зі своїх опублікованих каналів на аукціон.'
									: 'Спершу додайте канал і дочекайтеся модерації — потім зможете виставити його на аукціон.'}
							/>
						),
						<div className='grid gap-4'>
							{myAuctions.map(auction => {
								const isActive = auction.status === 'active';
								const endDate = auction.ends_at ? new Date(auction.ends_at) : null;
								const timeRemaining = endDate ? Math.max(0, endDate - Date.now()) : 0;
								const hoursLeft = Math.floor(timeRemaining / 3600000);
								const minsLeft = Math.floor((timeRemaining % 3600000) / 60000);
								const timeStr = timeRemaining > 0 ? `${hoursLeft} год ${minsLeft} хв` : 'Завершено';
								const st = AUCTION_STATUS[auction.status] || { text: auction.status, tone: 'gray' };
								return (
									<article key={auction.id} className={`${surface} esc-card p-4 sm:p-5`}>
										<div className='flex items-start gap-3 mb-4'>
											{auction.channel_avatar ? (
												<img className='w-12 h-12 rounded-xl object-cover flex-shrink-0' src={auction.channel_avatar} alt='' />
											) : (
												<div className='w-12 h-12 rounded-xl bg-gradient-to-br from-orange-400 to-red-500 flex items-center justify-center text-lg font-bold text-white flex-shrink-0'>
													{(auction.channel_name || '?')[0]}
												</div>
											)}
											<div className='min-w-0 flex-1'>
												<NavLink to={`/channel/${auction.channel_id}`} className='font-bold text-gray-900 dark:text-white hover:text-accent leading-snug line-clamp-2 break-words'>
													{auction.channel_name || `Канал #${auction.channel_id}`}
												</NavLink>
												<div className='flex flex-wrap items-center gap-2 mt-1.5'>
													<Badge tone={st.tone}>{st.text}</Badge>
													{isActive && <Badge tone='gray' dot={false}>⏱ {timeStr}</Badge>}
													<span className='text-xs text-gray-400'>Аукціон #{auction.id}</span>
												</div>
											</div>
										</div>
										<dl className='grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 text-sm'>
											{[
												['Поточна ціна', `${fmtUsdt(auction.current_price)} USDT`, true],
												['Стартова ціна', `${fmtUsdt(auction.start_price)} USDT`],
												['Крок ставки', `${fmtUsdt(auction.bid_step)} USDT`],
												['Ставок', auction.bid_count ?? 0],
											].map(([k, v, hl]) => (
												<div key={k} className={`${inner} p-3`}>
													<dt className='text-xs text-gray-500 dark:text-gray-400'>{k}</dt>
													<dd className={`font-semibold mt-1 tabular-nums ${hl ? 'text-orange-600 dark:text-orange-400' : 'text-gray-900 dark:text-gray-100'}`}>{v}</dd>
												</div>
											))}
										</dl>
									</article>
								);
							})}
						</div>,
					)}
				</>
			) : activeTab.value === 'deals' ? (
				<>
					<FilterChips items={DEAL_FILTERS} active={dealFilter} onChange={setDealFilter}
						count={f => (f.value === null ? dealCounts.all : dealCounts[f.value] || 0)} />
					{renderBody(
						filteredDeals.length === 0 && (
							<EmptyState
								icon='🤝'
								title={dealFilter.value ? 'Немає угод з таким статусом' : 'У вас ще немає угод'}
								text='Оберіть канал у каталозі — оплата проходить через безпечну угоду TgSell.'
								action={<LinkButton to='/catalog'>Перейти до каталогу</LinkButton>}
							/>
						),
						<div className='grid gap-4'>
							{filteredDeals.map(deal => {
								const statusInfo = DEAL_STATUS[deal.status] || { text: deal.status, tone: 'gray' };
								const isBuyer = user?.id === deal.buyer_id;
								const next = dealNextStep(deal, isBuyer);
								return (
									<article key={deal.id} className={`${surface} esc-card p-4 sm:p-5`}>
										<div className='flex flex-col sm:flex-row sm:items-start justify-between gap-2 sm:gap-4 mb-4'>
											<div className='min-w-0'>
												<h3 className='font-bold text-gray-900 dark:text-white text-base sm:text-lg leading-snug line-clamp-2 break-words'>
													{deal.channel_name || `Канал #${deal.channel_id}`}
												</h3>
												<p className='text-gray-500 dark:text-gray-400 text-sm mt-1'>
													Угода #{deal.id} · {isBuyer ? 'ви покупець' : 'ви продавець'}
												</p>
											</div>
											<div className='flex flex-wrap items-center gap-2 sm:justify-end flex-shrink-0'>
												<Badge tone={statusInfo.tone}>{statusInfo.text}</Badge>
												{unread[deal.id] > 0 && <Badge tone='blue' dot={false}>💬 {unread[deal.id]} нових</Badge>}
											</div>
										</div>
										<dl className='grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-3 text-sm'>
											<div className={`${inner} p-3`}>
												<dt className='text-xs text-gray-500 dark:text-gray-400'>Сума</dt>
												<dd className='font-bold mt-1 text-gray-900 dark:text-accent tabular-nums'>{fmtUsdt(deal.amount_usdt)} USDT</dd>
											</div>
											<div className={`${inner} p-3`}>
												<dt className='text-xs text-gray-500 dark:text-gray-400'>Комісія</dt>
												<dd className='font-semibold mt-1 text-gray-900 dark:text-gray-100 tabular-nums'>{fmtUsdt(deal.service_fee)} USDT</dd>
											</div>
											<div className={`${inner} p-3 min-w-0`}>
												<dt className='text-xs text-gray-500 dark:text-gray-400'>{isBuyer ? 'Продавець' : 'Покупець'}</dt>
												<dd className='font-semibold mt-1 text-gray-900 dark:text-gray-100 truncate'>{isBuyer ? (deal.seller_name || 'Продавець') : (deal.buyer_name || 'Покупець')}</dd>
											</div>
											<div className={`${inner} p-3`}>
												<dt className='text-xs text-gray-500 dark:text-gray-400'>Створено</dt>
												<dd className='font-semibold mt-1 text-gray-900 dark:text-gray-100 tabular-nums'>{new Date(deal.created_at).toLocaleDateString('uk-UA')}</dd>
											</div>
										</dl>
										{deal.dispute_reason && (
											<p className='mt-3 text-sm bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-900/40 text-red-700 dark:text-red-300 px-3 py-2 rounded-xl'>
												<span className='font-semibold'>Причина спору:</span> {deal.dispute_reason}
											</p>
										)}
										<div className='mt-4 flex justify-end'>
											<NavLink to={`/deal/${deal.id}`} className={`${next.primary ? btnPrimary : btnSecondary} w-full sm:w-auto`}>
												{next.text}
												<FontAwesomeIcon icon={faArrowRight} className='text-xs' />
											</NavLink>
										</div>
									</article>
								);
							})}
						</div>,
					)}
				</>
			) : activeTab.value === 'saved' ? (
				<SavedSearches />
			) : (
				renderBody(
					favorites.length === 0 && (
						<EmptyState
							icon='❤️'
							title='У вас поки немає обраних каналів'
							text='Натисніть ♡ на картці каналу в каталозі, щоб зберегти його тут.'
							action={<LinkButton to='/catalog'>Перейти до каталогу</LinkButton>}
						/>
					),
					<div className='esc-cab-list grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-4 sm:gap-6'>
						{favorites.map(channel => (
							<CatalogCard key={channel.id} channel={channel} />
						))}
					</div>,
				)
			)}

			{/* Auction creation modal */}
			{showAuctionModal && (
				<div
					className='fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm'
					onClick={() => setShowAuctionModal(false)}
				>
					<div
						className='bg-white dark:bg-card border border-transparent dark:border-card-border rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto'
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
													<span><FontAwesomeIcon icon={faUsers} className='mr-1' />{fmtNum(ch.subscribers_count) || '0'}</span>
													<span>{fmtNum(ch.price)} USDT</span>
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
													<p className='text-xs text-gray-500 dark:text-gray-400'>{fmtNum(ch.subscribers_count)} підписників</p>
												</div>
												<button onClick={() => setSelectedChannelId(null)} className='min-h-[44px] px-3 -mr-1 text-sm text-orange-600 dark:text-orange-400 hover:text-orange-700 font-semibold rounded-lg'>
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
											max={MAX_PRICE_USDT}
											title={MAX_PRICE_HINT}
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
											max={MAX_PRICE_USDT}
											title={MAX_PRICE_HINT}
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
									className='flex-1 min-h-[44px] py-3 rounded-xl text-sm font-semibold text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-slate-600 hover:bg-gray-50 dark:hover:bg-slate-700 transition-all'
								>
									Скасувати
								</button>
								{selectedChannelId && (
									<button
										onClick={handleCreateAuction}
										disabled={auctionSubmitting}
										className='flex-[2] min-h-[44px] py-3 rounded-xl text-sm font-semibold bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 text-white shadow-md hover:shadow-lg transition-all disabled:opacity-50 flex items-center justify-center gap-2'
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
