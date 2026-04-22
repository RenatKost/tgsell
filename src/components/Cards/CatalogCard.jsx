import { faHeart } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AppContext';
import { dealsAPI } from '../../services/api';

/* ── Tooltip ─────────────────────────────────────────────────────── */
const Tooltip = ({ children, text, desc }) => {
	const [show, setShow] = useState(false);
	return (
		<div className='relative' onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)}>
			{children}
			{show && (
				<div className='absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 pointer-events-none'>
					<div className='bg-gray-900 dark:bg-card text-white rounded-lg px-3 py-2 shadow-xl border border-gray-700 dark:border-card-border min-w-[160px] max-w-[220px]'>
						<p className='text-[11px] font-semibold mb-0.5 whitespace-nowrap'>{text}</p>
						{desc && <p className='text-[10px] text-gray-300 dark:text-gray-400 leading-snug'>{desc}</p>}
					</div>
					<div className='absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-x-[5px] border-x-transparent border-t-[5px] border-t-gray-900 dark:border-t-card' />
				</div>
			)}
		</div>
	);
};

/* ── CatalogCard ─────────────────────────────────────────────────── */
const CatalogCard = ({ channel }) => {
	const navigate = useNavigate();
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

	const cpm = channel.avg_views && channel.price && !channel.views_hidden
		? Math.round(channel.price / channel.avg_views * 1000)
		: null;
	const pricePerSub = channel.subscribers_count && channel.price
		? (channel.price / channel.subscribers_count).toFixed(2)
		: null;
	const payback = channel.monthly_income && channel.price
		? (channel.price / channel.monthly_income).toFixed(1)
		: null;

	const hasActivity = channel.total_posts || channel.post_frequency || channel.last_post_date
		|| channel.avg_forwards > 0 || channel.avg_reactions > 0;

	const handleBuy = async () => {
		if (!isAuthenticated) { alert('Увійдіть для покупки каналу'); return; }
		try {
			const { data } = await dealsAPI.create(channel.id);
			navigate(`/deal/${data.id}`);
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка створення угоди');
		}
	};

	return (
		<div className='group bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon hover:dark:shadow-neon-lg transition-shadow duration-300 flex flex-col'>

			{/* ── Header ── */}
			<div className='p-4 pb-3'>
				<div className='flex items-center gap-3'>
					{channel.avatar_url ? (
						<img className='w-11 h-11 rounded-lg object-cover flex-shrink-0' src={channel.avatar_url} alt={channel.channel_name} />
					) : (
						<div className='w-11 h-11 rounded-lg bg-gradient-to-br from-accent to-emerald-700 flex items-center justify-center text-black text-sm font-black flex-shrink-0'>
							{channel.channel_name?.[0] || 'T'}
						</div>
					)}
					<div className='min-w-0 flex-1'>
						<h5 className='font-bold text-gray-900 dark:text-white text-sm leading-tight truncate'>
							{channel.channel_name || 'Без назви'}
						</h5>
						<p className='text-gray-400 dark:text-gray-500 text-[11px] mt-0.5'>
							{channel.subscribers_count?.toLocaleString('uk-UA') || '0'} підписників
						</p>
					</div>
					<button
						onClick={() => isAuthenticated ? toggleFavorite(channel.id) : alert('Увійдіть щоб додати в обране')}
						className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all ${
							isFav
								? 'bg-red-50 dark:bg-red-900/30 text-red-500'
								: 'bg-gray-50 dark:bg-card-inner text-gray-300 dark:text-gray-500 hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30'
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
							className='inline-flex items-center gap-1 text-accent bg-accent/10 hover:bg-accent/20 text-[11px] font-semibold px-2.5 py-1 rounded-lg transition-all'
						>
							↗ Відкрити
						</a>
					)}
					{channel.bundle_id ? (
						<span className='bg-accent/15 text-accent text-[11px] font-bold px-2.5 py-1 rounded-lg border border-accent/30'>
							📡 В сетці · {channel.bundle_name}
						</span>
					) : channel.category && (
						<span className='bg-gray-50 dark:bg-card-inner text-gray-500 dark:text-gray-400 text-[11px] font-medium px-2.5 py-1 rounded-lg'>
							{channel.category}
						</span>
					)}
				</div>
			</div>

			{/* ── Key Metrics ── */}
			<div className='px-4 pb-3 flex-1'>
				<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>Ключові метрики</p>
				<div className='grid grid-cols-2 gap-2'>
					<div className='border-l-2 border-cyan-400 bg-gray-50 dark:bg-card-inner rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>Переглядів</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>
							{channel.views_hidden
								? <span className='text-amber-500 text-xs font-medium'>🔒 Приховані</span>
								: (channel.avg_views?.toLocaleString('uk-UA') || '—')}
						</p>
					</div>
					<div className='border-l-2 border-emerald-400 bg-gray-50 dark:bg-card-inner rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>ER</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>
							{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}
						</p>
					</div>
					<div className='border-l-2 border-orange-400 bg-gray-50 dark:bg-card-inner rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>Вік каналу</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>{formatAge(channel.age)}</p>
					</div>
					<div className='border-l-2 border-violet-400 bg-gray-50 dark:bg-card-inner rounded-r-lg pl-3 pr-2 py-2'>
						<p className='text-gray-400 text-[10px]'>Прибуток / міс.</p>
						<p className='font-bold text-sm text-gray-800 dark:text-gray-100'>
							{channel.monthly_income ? `${channel.monthly_income.toLocaleString('uk-UA')} USDT` : '—'}
						</p>
					</div>
				</div>
			</div>

			{/* ── Activity badges ── */}
			{hasActivity && (
				<div className='px-4 pb-3'>
					<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>Активність</p>
					<div className='flex flex-wrap gap-1.5'>
						{channel.total_posts != null && (
							<Tooltip text='Усього постів' desc='Загальна кількість публікацій за весь час'>
								<div className='flex items-center gap-1.5 bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/40 rounded-lg px-2 py-1.5 cursor-default'>
									<div className='w-5 h-5 rounded-md bg-blue-100 dark:bg-blue-800/50 flex items-center justify-center'>
										<svg className='w-3 h-3 text-blue-500' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='2'>
											<path strokeLinecap='round' strokeLinejoin='round' d='M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z' />
										</svg>
									</div>
									<span className='text-[11px] font-semibold text-blue-700 dark:text-blue-300'>{channel.total_posts.toLocaleString('uk-UA')}</span>
								</div>
							</Tooltip>
						)}
						{channel.post_frequency != null && (
							<Tooltip text='Публікацій / день' desc='Середня частота публікацій за останній період'>
								<div className='flex items-center gap-1.5 bg-orange-50 dark:bg-orange-900/20 border border-orange-100 dark:border-orange-800/40 rounded-lg px-2 py-1.5 cursor-default'>
									<div className='w-5 h-5 rounded-md bg-orange-100 dark:bg-orange-800/50 flex items-center justify-center'>
										<svg className='w-3 h-3 text-orange-500' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='2'>
											<path strokeLinecap='round' strokeLinejoin='round' d='M13 7h8m0 0v8m0-8l-8 8-4-4-6 6' />
										</svg>
									</div>
									<span className='text-[11px] font-semibold text-orange-700 dark:text-orange-300'>~{channel.post_frequency}/д</span>
								</div>
							</Tooltip>
						)}
						{channel.last_post_date && (
							<Tooltip text='Останній пост' desc='Скільки часу минуло з останньої публікації'>
								<div className='flex items-center gap-1.5 bg-gray-100 dark:bg-card-inner border border-gray-200 dark:border-card-border rounded-lg px-2 py-1.5 cursor-default'>
									<div className='w-5 h-5 rounded-md bg-gray-200 dark:bg-card-hover flex items-center justify-center'>
										<svg className='w-3 h-3 text-gray-500' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='2'>
											<path strokeLinecap='round' strokeLinejoin='round' d='M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' />
										</svg>
									</div>
									<span className='text-[11px] font-semibold text-gray-600 dark:text-gray-300'>{formatDate(channel.last_post_date)}</span>
								</div>
							</Tooltip>
						)}
						{channel.avg_forwards > 0 && (
							<Tooltip text='Пересилань / пост' desc='Скільки разів у середньому пересилають пости'>
								<div className='flex items-center gap-1.5 bg-teal-50 dark:bg-teal-900/20 border border-teal-100 dark:border-teal-800/40 rounded-lg px-2 py-1.5 cursor-default'>
									<div className='w-5 h-5 rounded-md bg-teal-100 dark:bg-teal-800/50 flex items-center justify-center'>
										<svg className='w-3 h-3 text-teal-500' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='2'>
											<path strokeLinecap='round' strokeLinejoin='round' d='M13 7l5 5m0 0l-5 5m5-5H6' />
										</svg>
									</div>
									<span className='text-[11px] font-semibold text-teal-700 dark:text-teal-300'>{channel.avg_forwards.toLocaleString('uk-UA')}</span>
								</div>
							</Tooltip>
						)}
						{channel.avg_reactions > 0 && (
							<Tooltip text='Реакцій / пост' desc='Середня кількість реакцій на публікацію'>
								<div className='flex items-center gap-1.5 bg-pink-50 dark:bg-pink-900/20 border border-pink-100 dark:border-pink-800/40 rounded-lg px-2 py-1.5 cursor-default'>
									<div className='w-5 h-5 rounded-md bg-pink-100 dark:bg-pink-800/50 flex items-center justify-center'>
										<svg className='w-3 h-3 text-pink-500' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='2'>
											<path strokeLinecap='round' strokeLinejoin='round' d='M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z' />
										</svg>
									</div>
									<span className='text-[11px] font-semibold text-pink-700 dark:text-pink-300'>{channel.avg_reactions.toLocaleString('uk-UA')}</span>
								</div>
							</Tooltip>
						)}
					</div>
				</div>
			)}

			{/* ── Analytics strip ── */}
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

			{/* ── Footer ── */}
			<div className='border-t border-gray-100 dark:border-card-border px-4 py-3 mt-auto'>
				<div className='flex items-center justify-between mb-3'>
					<div>
						<p className='text-gray-400 text-[10px]'>Ціна</p>
						<p className='font-extrabold text-lg text-gray-900 dark:text-white leading-none'>
							{channel.bundle_id
								? <><span>{channel.price?.toLocaleString('uk-UA') || '—'}</span><span className='text-xs font-semibold text-gray-400 ml-1'>USDT за сетку</span></>
								: <>{channel.price?.toLocaleString('uk-UA') || '—'}<span className='text-xs font-semibold text-gray-400 ml-1'>USDT</span></>
							}
						</p>
					</div>
					{channel.created_at && (
						<p className='text-gray-300 dark:text-gray-600 text-[10px]'>
							{new Date(channel.created_at).toLocaleDateString('uk-UA')}
						</p>
					)}
				</div>
				<div className='flex gap-2'>
					{channel.bundle_id ? (
						<>
							<NavLink
								to={`/bundle/${channel.bundle_id}`}
								className='flex-1 text-center px-3 py-2 rounded-lg text-xs font-semibold text-accent bg-accent/10 hover:bg-accent/20 border border-accent/30 transition-all'
							>
								📡 До сетки
							</NavLink>
						</>
					) : (
						<>
							<NavLink
								to={`/channel/${channel.id}`}
								className='flex-1 text-center px-3 py-2 rounded-lg text-xs font-semibold text-gray-500 dark:text-gray-300 bg-gray-50 dark:bg-card-inner hover:bg-gray-100 dark:hover:bg-card-hover border border-gray-200 dark:border-card-border transition-all'
							>
								Деталі
							</NavLink>
							<button
								onClick={handleBuy}
								className='flex-1 px-3 py-2 rounded-lg text-xs font-bold bg-accent text-black shadow-sm shadow-accent/20 hover:brightness-110 hover:shadow-accent/40 transition-all'
							>
								Купити
							</button>
						</>
					)}
				</div>
			</div>
		</div>
	);
};

export default CatalogCard;
