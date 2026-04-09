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

	const cpm = channel.avg_views && channel.price
		? Math.round(channel.price / channel.avg_views * 1000)
		: null;
	const pricePerSub = channel.subscribers_count && channel.price
		? (channel.price / channel.subscribers_count).toFixed(2)
		: null;
	const payback = channel.monthly_income && channel.price
		? (channel.price / channel.monthly_income).toFixed(1)
		: null;

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
		<div className='bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm'>
			{/* Channel header */}
			<div className='p-4'>
				<div className='flex items-center gap-3'>
					{channel.avatar_url ? (
						<img className='w-10 h-10 rounded-lg object-cover flex-shrink-0' src={channel.avatar_url} alt={channel.channel_name} />
					) : (
						<div className='w-10 h-10 rounded-lg bg-gradient-to-br from-[#3498db] to-[#2573a7] flex items-center justify-center text-white text-sm font-bold flex-shrink-0'>
							{channel.channel_name?.[0] || '?'}
						</div>
					)}
					<div className='min-w-0 flex-1'>
						<h5 className='font-bold text-gray-900 dark:text-white text-sm leading-tight truncate'>{channel.channel_name}</h5>
						<div className='flex items-center gap-2 mt-0.5'>
							<span className='text-gray-400 text-[11px]'>{channel.subscribers_count?.toLocaleString('uk-UA') || '0'} підписників</span>
							{subTrend && (
								<span className={`text-[10px] font-semibold ${subTrend.up ? 'text-emerald-500' : 'text-red-500'}`}>
									{subTrend.up ? '↑' : '↓'} {Math.abs(subTrend.diff).toLocaleString('uk-UA')} ({subTrend.up ? '+' : ''}{subTrend.pct}%)
								</span>
							)}
						</div>
					</div>
					<button
						onClick={() => isAuthenticated ? toggleFavorite(channel.id) : alert('Увійдіть щоб додати в обране')}
						className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all text-sm ${
							isFav ? 'bg-red-50 dark:bg-red-900/30 text-red-500' : 'bg-gray-50 dark:bg-slate-700 text-gray-300 dark:text-gray-500 hover:text-red-400'
						}`}
					>
						<FontAwesomeIcon icon={faHeart} className='text-xs' />
					</button>
				</div>

				<div className='flex flex-wrap items-center gap-1.5 mt-2.5'>
					{channel.telegram_link && (
						<a
							href={channel.telegram_link}
							target='_blank'
							rel='noopener noreferrer'
							className='inline-flex items-center gap-1 text-[#3498db] bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50 text-[11px] font-semibold px-2.5 py-1.5 rounded-lg transition-all'
						>
							↗ Переглянути канал
						</a>
					)}
					{channel.category && (
						<span className='bg-gray-50 dark:bg-slate-700 text-gray-500 dark:text-gray-400 text-[11px] font-medium px-2.5 py-1.5 rounded-lg'>
							{channel.category}
						</span>
					)}
				</div>
			</div>

			{/* Key Metrics with colored accents */}
			<div className='px-4 pb-3'>
				<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>Ключові метрики</p>
				<div className='grid grid-cols-2 gap-2'>
					<div className='border-l-2 border-cyan-400 bg-gray-50 dark:bg-slate-700/50 rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>Переглядів</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</p>
					</div>
					<div className='border-l-2 border-emerald-400 bg-gray-50 dark:bg-slate-700/50 rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>ER</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}</p>
					</div>
					<div className='border-l-2 border-orange-400 bg-gray-50 dark:bg-slate-700/50 rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>Вік каналу</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>{formatAge(channel.age)}</p>
					</div>
					<div className='border-l-2 border-violet-400 bg-gray-50 dark:bg-slate-700/50 rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>Прибуток / міс.</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>
							{channel.monthly_income ? `${channel.monthly_income.toLocaleString('uk-UA')} USDT` : '—'}
						</p>
					</div>
				</div>
			</div>

			{/* Activity - compact horizontal pills */}
			{(channel.total_posts || channel.post_frequency || channel.last_post_date || channel.avg_forwards || channel.avg_reactions) && (
				<div className='px-4 pb-3'>
					<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>Активність</p>
					<div className='flex flex-wrap gap-1.5'>
						{channel.total_posts != null && (
							<span className='bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 text-[11px] font-medium px-2 py-1 rounded-md'>
								📝 {channel.total_posts.toLocaleString('uk-UA')} постів
							</span>
						)}
						{channel.post_frequency != null && (
							<span className='bg-orange-50 dark:bg-orange-900/20 text-orange-600 dark:text-orange-400 text-[11px] font-medium px-2 py-1 rounded-md'>
								📊 ~{channel.post_frequency}/день
							</span>
						)}
						{channel.last_post_date && (
							<span className='bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-gray-400 text-[11px] font-medium px-2 py-1 rounded-md'>
								⏱ {formatDate(channel.last_post_date)}
							</span>
						)}
						{channel.avg_forwards > 0 && (
							<span className='bg-teal-50 dark:bg-teal-900/20 text-teal-600 dark:text-teal-400 text-[11px] font-medium px-2 py-1 rounded-md'>
								⬆ {channel.avg_forwards.toLocaleString('uk-UA')}
							</span>
						)}
						{channel.avg_reactions > 0 && (
							<span className='bg-pink-50 dark:bg-pink-900/20 text-pink-600 dark:text-pink-400 text-[11px] font-medium px-2 py-1 rounded-md'>
								❤️ {channel.avg_reactions.toLocaleString('uk-UA')}
							</span>
						)}
					</div>
				</div>
			)}

			{/* Analytics strip */}
			{(cpm || pricePerSub || payback) && (
				<div className='px-4 pb-3'>
					<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>Аналітика</p>
					<div className='grid grid-cols-3 gap-1.5'>
						<div className='bg-violet-50 dark:bg-violet-900/20 rounded-lg p-2 text-center'>
							<p className='text-violet-400 text-[10px]'>CPM</p>
							<p className='font-bold text-xs text-violet-600 dark:text-violet-300'>{cpm != null ? `$${cpm}` : '—'}</p>
						</div>
						<div className='bg-amber-50 dark:bg-amber-900/20 rounded-lg p-2 text-center'>
							<p className='text-amber-500 text-[10px]'>$/підписник</p>
							<p className='font-bold text-xs text-amber-600 dark:text-amber-300'>{pricePerSub ?? '—'}</p>
						</div>
						<div className='bg-emerald-50 dark:bg-emerald-900/20 rounded-lg p-2 text-center'>
							<p className='text-emerald-500 text-[10px]'>Окупність</p>
							<p className='font-bold text-xs text-emerald-600 dark:text-emerald-300'>{payback ? `${payback} міс.` : '—'}</p>
						</div>
					</div>
				</div>
			)}

			{/* Price + Buy */}
			<div className='border-t border-gray-100 dark:border-slate-700 px-4 py-3'>
				<div className='flex items-center justify-between mb-3'>
					<div>
						<p className='text-gray-400 text-[10px]'>Ціна</p>
						<p className='font-extrabold text-lg text-gray-900 dark:text-white'>
							{channel.price?.toLocaleString('uk-UA')}
							<span className='text-xs font-semibold text-gray-400 ml-1'>USDT</span>
						</p>
					</div>
					{channel.created_at && (
						<p className='text-gray-300 text-[10px]'>
							Розміщено {new Date(channel.created_at).toLocaleDateString('uk-UA')}
						</p>
					)}
				</div>
				<button
					onClick={onBuy}
					className='w-full font-bold bg-[#27ae60] text-white py-2.5 rounded-lg shadow-lg shadow-green-100/50 dark:shadow-none hover:bg-green-600 transition-all text-sm'
				>
					Купити канал
				</button>
			</div>
		</div>
	);
};

export default DetailsCard;
