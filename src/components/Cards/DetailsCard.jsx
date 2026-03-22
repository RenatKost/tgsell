import { faHeart } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useAuth } from '../../context/AppContext';

const DetailsCard = ({ channel, onBuy, stats = [] }) => {
	const { isAuthenticated, favoriteIds, toggleFavorite } = useAuth();
	const isFav = favoriteIds.has(channel.id);

	const formatAge = (months) => {
		if (!months) return '—';
		const m = typeof months === 'string' ? parseInt(months, 10) : months;
		if (isNaN(m)) return '—';
		const y = Math.floor(m / 12);
		const rem = m % 12;
		return y > 0 ? `${y} р. ${rem} міс.` : `${rem} міс.`;
	};

	const formatDate = (d) => {
		if (!d) return '—';
		const date = new Date(d);
		if (isNaN(date)) return '—';
		const now = new Date();
		const diff = Math.floor((now - date) / (1000 * 60 * 60));
		if (diff < 1) return 'щойно';
		if (diff < 24) return `${diff} год. тому`;
		const days = Math.floor(diff / 24);
		if (days < 7) return `${days} дн. тому`;
		return date.toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' });
	};

	// Computed metrics
	const cpm = channel.avg_views && channel.price
		? Math.round(channel.price / channel.avg_views * 1000)
		: null;
	const pricePerSub = channel.subscribers_count && channel.price
		? (channel.price / channel.subscribers_count).toFixed(2)
		: null;
	const payback = channel.monthly_income && channel.price
		? (channel.price / channel.monthly_income).toFixed(1)
		: null;

	// Subscriber trend from stats
	let subTrend = null;
	if (stats.length >= 2) {
		const first = stats[0]?.subscribers;
		const last = stats[stats.length - 1]?.subscribers;
		if (first && last) {
			const diff = last - first;
			const pct = ((diff / first) * 100).toFixed(1);
			subTrend = { diff, pct, up: diff > 0 };
		}
	}

	return (
		<div className='bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden'>
			{/* Header */}
			<div className='p-5 pb-4'>
				<div className='flex items-center gap-4'>
					{channel.avatar_url ? (
						<img className='w-16 h-16 rounded-xl object-cover flex-shrink-0' src={channel.avatar_url} alt={channel.channel_name} />
					) : (
						<div className='w-16 h-16 rounded-xl bg-gradient-to-br from-[#3498db] to-[#2573a7] flex items-center justify-center text-white text-2xl font-bold flex-shrink-0'>
							{channel.channel_name?.[0] || '?'}
						</div>
					)}
					<div className='min-w-0 flex-1'>
						<h5 className='font-bold text-gray-900 text-lg'>{channel.channel_name}</h5>
						<p className='text-gray-400 text-sm'>{channel.subscribers_count?.toLocaleString('uk-UA') || '0'} підписників</p>
						{subTrend && (
							<span className={`text-xs font-semibold ${subTrend.up ? 'text-emerald-500' : 'text-red-500'}`}>
								{subTrend.up ? '↑' : '↓'} {Math.abs(subTrend.diff).toLocaleString('uk-UA')} ({subTrend.up ? '+' : ''}{subTrend.pct}%)
							</span>
						)}
					</div>
					<button
						onClick={() => isAuthenticated ? toggleFavorite(channel.id) : alert('Увійдіть щоб додати в обране')}
						className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center transition-all duration-300 ${
							isFav ? 'bg-red-50 text-red-500' : 'bg-gray-50 text-gray-300 hover:text-red-400 hover:bg-red-50'
						}`}
					>
						<FontAwesomeIcon icon={faHeart} />
					</button>
				</div>

				<div className='flex flex-wrap items-center gap-2 mt-3'>
					{channel.telegram_link && (
						<a
							href={channel.telegram_link}
							target='_blank'
							rel='noopener noreferrer'
							className='inline-flex items-center gap-1.5 text-[#3498db] bg-blue-50 hover:bg-blue-100 text-sm font-semibold px-4 py-2 rounded-xl transition-all duration-300'
						>
							↗ Переглянути канал
						</a>
					)}
					{channel.category && (
						<span className='bg-blue-50 text-[#3498db] text-xs font-semibold px-3 py-2 rounded-xl'>
							{channel.category}
						</span>
					)}
				</div>
			</div>

			{/* Main stats grid */}
			<div className='px-5 pb-2'>
				<p className='text-xs text-gray-400 font-semibold uppercase tracking-wider mb-2'>Статистика</p>
				<div className='grid grid-cols-2 gap-2.5'>
					<div className='bg-gray-50 rounded-xl p-3'>
						<p className='text-gray-400 text-xs mb-0.5'>Переглядів</p>
						<p className='font-bold text-gray-800'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3'>
						<p className='text-gray-400 text-xs mb-0.5'>ER</p>
						<p className='font-bold text-gray-800'>{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3'>
						<p className='text-gray-400 text-xs mb-0.5'>Вік каналу</p>
						<p className='font-bold text-gray-800'>{formatAge(channel.age)}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3'>
						<p className='text-gray-400 text-xs mb-0.5'>Прибуток / міс.</p>
						<p className='font-bold text-gray-800'>
							{channel.monthly_income ? `${channel.monthly_income.toLocaleString('uk-UA')} USDT` : '—'}
						</p>
					</div>
				</div>
			</div>

			{/* Activity stats */}
			{(channel.total_posts || channel.post_frequency || channel.last_post_date || channel.avg_forwards || channel.avg_reactions) && (
				<div className='px-5 pb-2 pt-2'>
					<p className='text-xs text-gray-400 font-semibold uppercase tracking-wider mb-2'>Активність</p>
					<div className='grid grid-cols-2 gap-2.5'>
						<div className='bg-gray-50 rounded-xl p-3'>
							<p className='text-gray-400 text-xs mb-0.5'>Усього постів</p>
							<p className='font-bold text-gray-800'>{channel.total_posts?.toLocaleString('uk-UA') || '—'}</p>
						</div>
						<div className='bg-gray-50 rounded-xl p-3'>
							<p className='text-gray-400 text-xs mb-0.5'>Постів / день</p>
							<p className='font-bold text-gray-800'>{channel.post_frequency ?? '—'}</p>
						</div>
						<div className='bg-gray-50 rounded-xl p-3'>
							<p className='text-gray-400 text-xs mb-0.5'>Останній пост</p>
							<p className='font-bold text-gray-800 text-sm'>{formatDate(channel.last_post_date)}</p>
						</div>
						<div className='bg-gray-50 rounded-xl p-3'>
							<p className='text-gray-400 text-xs mb-0.5'>⬆ Пересилань</p>
							<p className='font-bold text-gray-800'>{channel.avg_forwards?.toLocaleString('uk-UA') || '—'}</p>
						</div>
					</div>
					{channel.avg_reactions != null && channel.avg_reactions > 0 && (
						<div className='bg-gray-50 rounded-xl p-3 mt-2.5'>
							<p className='text-gray-400 text-xs mb-0.5'>❤️ Реакції / пост</p>
							<p className='font-bold text-gray-800'>{channel.avg_reactions.toLocaleString('uk-UA')}</p>
						</div>
					)}
				</div>
			)}

			{/* Computed analytics */}
			{(cpm || pricePerSub || payback) && (
				<div className='px-5 pb-2 pt-2'>
					<p className='text-xs text-gray-400 font-semibold uppercase tracking-wider mb-2'>Аналітика</p>
					<div className='grid grid-cols-3 gap-2.5'>
						<div className='bg-violet-50 rounded-xl p-3 text-center'>
							<p className='text-violet-400 text-xs mb-0.5'>CPM</p>
							<p className='font-bold text-violet-700'>{cpm != null ? `$${cpm}` : '—'}</p>
						</div>
						<div className='bg-amber-50 rounded-xl p-3 text-center'>
							<p className='text-amber-500 text-xs mb-0.5'>$/підписник</p>
							<p className='font-bold text-amber-700'>{pricePerSub ?? '—'}</p>
						</div>
						<div className='bg-emerald-50 rounded-xl p-3 text-center'>
							<p className='text-emerald-500 text-xs mb-0.5'>Окупність</p>
							<p className='font-bold text-emerald-700'>{payback ? `${payback} міс.` : '—'}</p>
						</div>
					</div>
				</div>
			)}

			{/* Price + Actions */}
			<div className='border-t border-gray-100 px-5 py-4 mt-1'>
				<div className='flex items-center justify-between mb-4'>
					<div>
						<p className='text-gray-400 text-xs'>Ціна</p>
						<p className='font-extrabold text-2xl text-gray-900'>
							{channel.price?.toLocaleString('uk-UA')}
							<span className='text-sm font-semibold text-gray-400 ml-1'>USDT</span>
						</p>
					</div>
					{channel.created_at && (
						<p className='text-gray-300 text-xs'>
							Розміщено {new Date(channel.created_at).toLocaleDateString('uk-UA')}
						</p>
					)}
				</div>
				<button
					onClick={onBuy}
					className='w-full font-bold bg-[#27ae60] text-white py-3.5 rounded-xl shadow-lg shadow-green-100 hover:bg-green-600 transition-all duration-300 text-base'
				>
					Купити канал
				</button>
			</div>
		</div>
	);
};

export default DetailsCard;
