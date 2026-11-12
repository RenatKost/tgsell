import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, NavLink, useSearchParams } from 'react-router-dom';
import { trackEvent } from '../utils/tracking';
import { Radio, ExternalLink } from 'lucide-react';
import { channelsAPI, dealsAPI, priceOffersAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import AuthModal from '../components/Header/AuthModal';
import BuyConfirmModal from '../components/Buy/BuyConfirmModal';
import PriceOfferModal from '../components/Buy/PriceOfferModal';
import { savePendingBuy, peekPendingBuy, clearPendingBuy, markPendingBuyLoggedIn } from '../utils/buyIntent';
import { savePendingOffer, peekPendingOffer, clearPendingOffer, markPendingOfferLoggedIn } from '../utils/offerIntent';
import { offerBounds } from '../utils/offerAmount';
import { loginModalCopy } from '../utils/loginCopy';
import { offerLinkNotice } from '../utils/offerLink';
import { IcoSignal } from '../components/Icon3D';
import DetailsCard from '../components/Cards/DetailsCard';
import ChannelHealth from '../components/ChanelDetails/ChannelHealth';
import AIRiskScore from '../components/ChanelDetails/AIRiskScore';
import PostsPerDay from '../components/ChanelDetails/Coverage';
import ER from '../components/ChanelDetails/ER';
import Subscribers from '../components/ChanelDetails/Subscribers';
import Views from '../components/ChanelDetails/Views';
import PostsList from '../components/ChanelDetails/PostsList';
import AiAnalysis from '../components/ChanelDetails/AiAnalysis';
import { PriceEstimate } from '../components/Pricing/PriceVerdict';
import { QualityBlock } from '../components/Quality/QualityBadge';
import BalanceBadges, { hasBalance } from '../components/Balance/BalanceBadges';
import SimilarChannels from '../components/Similar/SimilarChannels';
import NotFoundPage from './NotFoundPage';
import useReveal from '../hooks/useReveal';
import './escrow.css';
import './premium.css';

const ChannelDetailsPage = () => {
	const { id } = useParams();
	// Task 23: channel view (server dedupes repeats within 10 min)
	useEffect(() => { if (Number(id) > 0) trackEvent('channel_view', { channel_id: Number(id) }); }, [id]);
	// Task 24: click-through from a saved-search bot notification (?ref=saved_search)
	const [searchParams, setSearchParams] = useSearchParams();
	useEffect(() => {
		if (searchParams.get('ref') === 'saved_search' && Number(id) > 0) {
			trackEvent('saved_search_click', { channel_id: Number(id), page: 'channel' });
			setSearchParams({}, { replace: true });
		}
	}, [id, searchParams, setSearchParams]);
	const navigate = useNavigate();
	useReveal();
	const { isAuthenticated, user } = useAuth();
	const [channel, setChannel] = useState(null);
	const [stats, setStats] = useState([]);
	const [health, setHealth] = useState(null);
	const [healthLoading, setHealthLoading] = useState(true);
	const [loading, setLoading] = useState(true);
	const [notFound, setNotFound] = useState(false);
	const [replacedBy, setReplacedBy] = useState(null);

	useEffect(() => {
		const fetchData = async () => {
			setNotFound(false);
			setReplacedBy(null);
			try {
				const [channelRes, statsRes] = await Promise.all([
					channelsAPI.getById(id),
					channelsAPI.getStats(id).catch(() => ({ data: [] })),
				]);
				setChannel(channelRes.data);
				setStats(Array.isArray(statsRes.data) ? statsRes.data : []);
			} catch (err) {
				console.error('Failed to load channel:', err);
				// Missing / unpublished lot (or invalid id) → show the 404 page instead of redirecting
				const st = err?.response?.status;
				const rep = Number(err?.response?.data?.replaced_by);
				if (st === 404 && rep > 0) { setReplacedBy(rep); return; }
				if (st === 404 || st === 422 || !(Number(id) > 0)) setNotFound(true);
				else navigate('/catalog');
			} finally {
				setLoading(false);
			}
		};
		fetchData();
	}, [id, navigate]);

	// Relisted lot: notice + auto-redirect to the new active lot
	useEffect(() => {
		if (!replacedBy) return;
		const t = setTimeout(() => navigate(`/channel/${replacedBy}`, { replace: true }), 3000);
		return () => clearTimeout(t);
	}, [replacedBy, navigate]);

	useEffect(() => {
		if (!channel) return;
		const fetchHealth = async () => {
			try {
				const { data } = await channelsAPI.getHealth(channel.id);
				setHealth(data);
			} catch {
				setHealth(null);
			} finally {
				setHealthLoading(false);
			}
		};
		fetchHealth();
	}, [channel]);

	const [showAuth, setShowAuth] = useState(false);
	const [authIntent, setAuthIntent] = useState('buy');
	const [showConfirm, setShowConfirm] = useState(false);
	const [buying, setBuying] = useState(false);
	const [buyError, setBuyError] = useState(null);
	const loginFromBuyTracked = useRef(false);

	const handleBuy = () => {
		if (!channel) return;
		trackEvent('buy_click', { channel_id: channel.id });
		if (!isAuthenticated) {
			clearPendingOffer();
			savePendingBuy(channel.id, { needLogin: true });
			setAuthIntent('buy');
			trackEvent('login_prompt_open', { channel_id: channel.id });
			setShowAuth(true);
			return;
		}
		savePendingBuy(channel.id, { needLogin: false });
		setBuyError(null);
		setShowConfirm(true);
	};

	// After Telegram login (this page or a return from BuyIntentGate): open confirm, never auto-create the deal.
	useEffect(() => {
		if (!isAuthenticated || !channel) return;
		if (peekPendingOffer()) return;
		const pending = peekPendingBuy();
		if (!pending || pending.channelId !== Number(channel.id)) return;
		if (pending.needLogin && !loginFromBuyTracked.current) {
			loginFromBuyTracked.current = true;
			markPendingBuyLoggedIn();
			trackEvent('login_success_from_buy', { channel_id: channel.id });
		}
		setShowAuth(false);
		setShowConfirm(true);
	}, [isAuthenticated, channel]);

	const closeConfirm = () => {
		if (buying) return;
		setShowConfirm(false);
		setBuyError(null);
		clearPendingBuy();
		setAcceptedOffer(null);
	};

	const confirmBuy = async () => {
		if (!channel || buying) return;
		setBuying(true);
		setBuyError(null);
		try {
			const { data } = await dealsAPI.create(channel.id, null, acceptedOffer?.id || null);
			clearPendingBuy();
			setAcceptedOffer(null);
			navigate(`/deal/${data.id}`);
		} catch (err) {
			setBuyError(err.response?.data?.detail || 'Помилка створення угоди');
		} finally {
			setBuying(false);
		}
	};

	const [showOffer, setShowOffer] = useState(false);
	const [offering, setOffering] = useState(false);
	const [offerError, setOfferError] = useState(null);
	const [acceptedOffer, setAcceptedOffer] = useState(null);
	const [offerSent, setOfferSent] = useState(false);
	const [offerNotice, setOfferNotice] = useState(null);
	useEffect(() => {
		if (!offerSent) return;
		const t = setTimeout(() => setOfferSent(false), 5000);
		return () => clearTimeout(t);
	}, [offerSent]);
	useEffect(() => {
		if (!offerNotice) return;
		const t = setTimeout(() => setOfferNotice(null), 7000);
		return () => clearTimeout(t);
	}, [offerNotice]);
	const loginFromOfferTracked = useRef(false);

	const handleOffer = () => {
		if (!channel) return;
		trackEvent('offer_open', { channel_id: channel.id });
		if (!isAuthenticated) {
			clearPendingBuy();
			savePendingOffer(channel.id, { needLogin: true });
			setAuthIntent('offer');
			trackEvent('login_prompt_open', { channel_id: channel.id });
			setShowAuth(true);
			return;
		}
		setOfferError(null);
		setShowOffer(true);
	};

	// After login from the offer path: open the offer form, never auto-send.
	useEffect(() => {
		if (!isAuthenticated || !channel) return;
		const pending = peekPendingOffer();
		if (!pending || pending.channelId !== Number(channel.id)) return;
		if (pending.needLogin && !loginFromOfferTracked.current) {
			loginFromOfferTracked.current = true;
			markPendingOfferLoggedIn();
		}
		clearPendingOffer();
		setShowAuth(false);
		setShowConfirm(false);
		setOfferError(null);
		setShowOffer(true);
	}, [isAuthenticated, channel]);

	// Deep link from the accepted-offer bot message: /channel/:id?offer=:id
	useEffect(() => {
		const raw = searchParams.get('offer');
		const offerId = Number(raw);
		if (!(offerId > 0) || !isAuthenticated) return;
		let cancelled = false;
		const clearOfferParam = () => {
			const next = new URLSearchParams(searchParams);
			next.delete('offer');
			setSearchParams(next, { replace: true });
		};
		(async () => {
			try {
				const { data } = await priceOffersAPI.get(offerId);
				if (cancelled) return;
				const notice = offerLinkNotice(data, { channelId: id });
				if (notice) {
					setOfferNotice(notice);
					clearOfferParam();
					return;
				}
				if (data.channel_id !== Number(id) || !data.can_create_deal) {
					clearOfferParam();
					return;
				}
				setAcceptedOffer(data);
				setShowConfirm(true);
				clearOfferParam();
			} catch (err) {
				if (cancelled) return;
				setOfferNotice(offerLinkNotice(null, { channelId: id, error: err }));
				clearOfferParam();
			}
		})();
		return () => { cancelled = true; };
	}, [isAuthenticated, id, searchParams, setSearchParams]);

	const closeOffer = () => {
		if (offering) return;
		setShowOffer(false);
		setOfferError(null);
		clearPendingOffer();
	};

	const submitOffer = async ({ amount_usdt, comment }) => {
		if (!channel || offering) return;
		setOffering(true);
		setOfferError(null);
		try {
			await priceOffersAPI.create({ channel_id: channel.id, amount_usdt, comment });
			trackEvent('offer_sent', { channel_id: channel.id });
			clearPendingOffer();
			setShowOffer(false);
			setOfferError(null);
			setOfferSent(true);
		} catch (err) {
			setOfferError(err.response?.data?.detail || 'Не вдалося надіслати пропозицію');
		} finally {
			setOffering(false);
		}
	};

	const handleGoAuction = () => {
		navigate('/auction');
	};

	if (loading) {
		return (
			<div className='mt-28 flex justify-center'>
				<div className='animate-spin rounded-full h-8 w-8 border-2 border-gray-200 dark:border-card-border border-t-accent' />
			</div>
		);
	}

	if (replacedBy) {
		return (
			<section className='pt-28 pb-16 px-4 flex justify-center'>
				<div className='max-w-md w-full text-center rounded-2xl border border-gray-200 dark:border-card-border p-6' role='status'>
					<h1 className='text-xl font-semibold mb-2'>Лот оновлено</h1>
					<p className='text-sm opacity-80 mb-4'>Продавець переопублікував цей канал як новий лот. Зараз перенаправимо вас на актуальне оголошення…</p>
					<NavLink to={`/channel/${replacedBy}`} replace className='inline-block rounded-xl bg-accent text-white px-4 py-2 text-sm font-medium'>
						Перейти до лоту #{replacedBy}
					</NavLink>
				</div>
			</section>
		);
	}
	if (notFound) return <NotFoundPage />;
	if (!channel) return null;

	const resources = channel.resources ? channel.resources.split(',').map(r => r.trim()).filter(Boolean) : [];

	return (
		<section className='esc-page chd-page relative overflow-x-clip pt-28 pb-8'>
			<div className='esc-bg esc-bg-short' aria-hidden='true'><span className='esc-grid' /><span className='esc-blob esc-blob-1' /><span className='esc-blob esc-blob-2' /></div>
			{/* Breadcrumb */}
			<div className='flex items-center gap-1.5 text-xs mb-5 px-0.5'>
				<NavLink to='/catalog' className='text-gray-400 dark:text-gray-500 hover:text-accent transition-colors'>Каталог</NavLink>
				<span className='text-gray-300 dark:text-gray-600'>/</span>
				<span className='text-gray-600 dark:text-gray-300 font-medium'>{channel.channel_name || 'Канал'}</span>
			</div>

			{/* Admin-set buyer warning (migration 0046) */}
			{channel.buyer_warning && (
				<div role='alert' className='mb-5 flex items-start gap-3 p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 border-2 border-amber-300 dark:border-amber-700'>
					<span className='text-xl leading-none flex-shrink-0'>⚠️</span>
					<div>
						<p className='text-sm font-bold text-amber-800 dark:text-amber-300 mb-1'>Попередження для покупця</p>
						<p className='text-sm text-amber-900 dark:text-amber-200 whitespace-pre-line break-words'>{channel.buyer_warning}</p>
					</div>
				</div>
			)}

			{/* Bundle banner */}
			{channel.bundle_id && (
				<div className='mb-5 flex items-center gap-3 p-3 rounded-xl bg-accent/10 border border-accent/30'>
					<IcoSignal size='sm' className='flex-shrink-0' />
					<span className='text-sm text-gray-200'>
						Цей канал продається у складі сітки <span className='text-accent font-semibold'>«{channel.bundle_name}»</span>
					</span>
					<NavLink to={`/bundle/${channel.bundle_id}`}
						className='ml-auto text-sm text-accent hover:underline whitespace-nowrap'>
						Переглянути сітку →
					</NavLink>
				</div>
			)}

			{/* 2-column layout: fixed sidebar + fluid content */}
			<div className='grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-4 items-start'>

				{/* LEFT SIDEBAR: DetailsCard → Comment → Resources → ChannelHealth */}
				<div className='esc-reveal flex flex-col gap-4'>
					<DetailsCard channel={channel} onBuy={handleBuy} onAuction={handleGoAuction} onOffer={handleOffer} showOffer={!channel.bundle_id && user?.id !== channel.seller_id && !!offerBounds(channel.price)} stats={stats} />
					{hasBalance(channel) && (
						<div className='bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-4'>
							<p className='text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2'>Баланс каналу</p>
							<BalanceBadges stars={channel.stars_balance} ton={channel.ton_balance} />
							<p className='text-[11px] text-gray-400 mt-2 leading-snug'>Не перевіряється платформою й не входить у ціну. Покупець підтверджує баланс під час передачі каналу.</p>
						</div>
					)}
					<QualityBlock channel={channel} />
					<PriceEstimate channel={channel} />

					{channel.description && (
						<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon p-4'>
							<h4 className='font-semibold text-gray-900 dark:text-white text-xs uppercase tracking-wider mb-2'>Коментар власника</h4>
							<p className='text-gray-600 dark:text-gray-300 text-xs leading-relaxed bg-blue-50 dark:bg-card-inner rounded-lg p-3 break-words overflow-hidden'>
								{channel.description}
							</p>
						</div>
					)}

					{resources.length > 0 && (
						<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon p-4'>
							<h4 className='font-semibold text-gray-900 dark:text-white text-xs uppercase tracking-wider mb-2'>Додаткові ресурси</h4>
							<div className='flex flex-wrap gap-1.5'>
								{resources.map((url, idx) => (
									<a
										key={idx}
										href={url}
										target='_blank'
										rel='noopener noreferrer'
										className='inline-flex items-center gap-1.5 bg-gray-50 dark:bg-card-inner hover:bg-accent hover:text-white text-gray-600 dark:text-gray-300 font-medium text-[11px] px-3 py-2 rounded-lg border border-gray-200 dark:border-card-border hover:border-accent transition-all'
									>
										<ExternalLink size={11} /> Ресурс {idx + 1}
									</a>
								))}
							</div>
						</div>
					)}

					<ChannelHealth health={health} loading={healthLoading} />
				</div>

				{/* RIGHT CONTENT: charts + AI Analysis stacked */}
				<div className='esc-reveal flex flex-col gap-4' style={{ '--d': '80ms' }}>
					{/* Charts row 1: Subscribers + Views */}
					<div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
						<Subscribers stats={stats} current={channel.subscribers_count} />
						<Views stats={stats} current={channel.avg_views} viewsHidden={channel.views_hidden} />
					</div>

					{/* Charts row 2: ER + PostsPerDay + AIRiskScore */}
					<div className='grid grid-cols-1 md:grid-cols-3 gap-4'>
						<ER stats={stats} current={channel.er} />
						<PostsPerDay stats={stats} />
						<AIRiskScore health={health} loading={healthLoading} />
					</div>

					{/* AI Analysis full right-column width */}
					{channel.is_closed && (
						<div className='flex items-center gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40 rounded-lg text-xs text-amber-600 dark:text-amber-400'>
							⚠️ Обмежені дані — закритий канал, аналіз ґрунтується на даних продавця
						</div>
					)}
					<AiAnalysis channelId={channel.id} channel={channel} />
				</div>
			</div>

			{/* Posts full width */}
			<div className='esc-reveal mt-4'>
				<PostsList channelId={channel.id} />
			</div>

			<SimilarChannels channelId={channel.id} />

			<AuthModal
				show={showAuth}
				setShow={setShowAuth}
				title={loginModalCopy(authIntent).title}
				subtitle={loginModalCopy(authIntent).subtitle}
			/>
			<BuyConfirmModal
				channel={channel}
				open={showConfirm}
				onClose={closeConfirm}
				onConfirm={confirmBuy}
				busy={buying}
				error={buyError}
				amount={acceptedOffer ? acceptedOffer.amount_usdt : undefined}
				note={acceptedOffer
					? 'Угоду буде створено за погодженою пропозицією. Публічна ціна лота не змінюється. Кошти підуть на адресу гаранта лише після підтвердження готовності обома сторонами.'
					: undefined}
			/>
			<PriceOfferModal
				channel={channel}
				open={showOffer}
				onClose={closeOffer}
				onSubmit={submitOffer}
				busy={offering}
				error={offerError}
			/>
			{offerSent && (
				<div role='status' className='fixed bottom-4 left-1/2 -translate-x-1/2 z-[80] max-w-sm w-[calc(100%-2rem)] rounded-xl bg-emerald-600 text-white text-sm font-medium px-4 py-3 shadow-lg'>
					Пропозицію надіслано продавцю. Відповідь прийде в Telegram-бот і зʼявиться у кабінеті.
				</div>
			)}
			{offerNotice && (
				<div role='status' className='fixed bottom-4 left-1/2 -translate-x-1/2 z-[80] max-w-sm w-[calc(100%-2rem)] rounded-xl bg-slate-800 text-white text-sm font-medium px-4 py-3 shadow-lg'>
					{offerNotice}
				</div>
			)}
		</section>
	);
};

export default ChannelDetailsPage;
