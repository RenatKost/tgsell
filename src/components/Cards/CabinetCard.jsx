import {
	faBarChart,
	faChartLine,
	faClock,
	faEye,
	faDollarSign,
	faListAlt,
	faUsers,
	faWallet,
	faTrash,
	faArrowRight,
} from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { NavLink } from 'react-router-dom';

const statusLabels = {
	pending: { text: 'На модерації', color: 'text-yellow-700 bg-yellow-50 border-yellow-200' },
	approved: { text: 'Опубліковано', color: 'text-green-700 bg-green-50 border-green-200' },
	rejected: { text: 'Відхилено', color: 'text-red-700 bg-red-50 border-red-200' },
	sold: { text: 'Продано', color: 'text-gray-700 bg-gray-50 border-gray-200' },
};

const CabinetCard = ({ channel, onDelete }) => {
	const status = statusLabels[channel.status] || statusLabels.pending;

	const formatAge = (months) => {
		if (!months) return '—';
		const m = typeof months === 'string' ? parseInt(months, 10) : months;
		if (isNaN(m)) return '—';
		const y = Math.floor(m / 12);
		const rem = m % 12;
		return y > 0 ? `${y} р. ${rem} міс.` : `${rem} міс.`;
	};

	return (
		<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 shadow-sm hover:shadow-md duration-300 overflow-hidden'>
			{/* Top: Avatar + Name + Status */}
			<div className='p-5 pb-4'>
				<div className='flex items-start gap-4'>
					{channel.avatar_url ? (
						<img className='w-14 h-14 rounded-xl object-cover flex-shrink-0' src={channel.avatar_url} alt={channel.channel_name} />
					) : (
						<div className='w-14 h-14 rounded-xl bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center text-xl font-bold text-white flex-shrink-0'>
							{channel.channel_name?.[0] || '?'}
						</div>
					)}
					<div className='flex-1 min-w-0'>
						<div className='flex items-start justify-between gap-2'>
							<NavLink to={`/channel/${channel.id}`} className='font-bold text-gray-800 dark:text-white hover:text-[#3498db] duration-300 truncate block'>
								{channel.channel_name}
							</NavLink>
							<div className='flex items-center gap-1.5 flex-shrink-0'>
								{(channel.listing_type === 'auction' || channel.listing_type === 'both') && (
									<span className='text-xs px-2 py-0.5 rounded-full font-medium bg-orange-50 text-orange-600 border border-orange-200'>🔥</span>
								)}
								<span className={`text-xs px-2.5 py-1 rounded-full font-medium border whitespace-nowrap ${status.color}`}>
									{status.text}
								</span>
							</div>
						</div>
						<div className='flex items-center gap-3 mt-1.5 text-sm text-gray-500'>
							<span className='flex items-center gap-1'>
								<FontAwesomeIcon icon={faUsers} className='text-xs' />
								{channel.subscribers_count?.toLocaleString('uk-UA') || '0'}
							</span>
							{channel.daily_growth != null && (
								<span className={`flex items-center gap-1 ${channel.daily_growth >= 0 ? 'text-green-600' : 'text-red-500'}`}>
									<FontAwesomeIcon icon={faChartLine} className='text-xs' />
									{channel.daily_growth >= 0 ? '+' : ''}{channel.daily_growth}
								</span>
							)}
							{channel.category && (
								<span className='flex items-center gap-1'>
									<FontAwesomeIcon icon={faListAlt} className='text-xs' />
									{channel.category}
								</span>
							)}
						</div>
					</div>
				</div>
			</div>

			{/* Stats grid */}
			<div className='grid grid-cols-2 sm:grid-cols-4 gap-px bg-gray-100 dark:bg-slate-700 border-t border-gray-100 dark:border-slate-700'>
				<div className='bg-white dark:bg-slate-800 p-3 text-center'>
					<p className='text-xs text-gray-400 dark:text-gray-500 mb-0.5'>Переглядів</p>
					<p className='font-semibold text-gray-800 dark:text-gray-100 text-sm'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</p>
				</div>
				<div className='bg-white dark:bg-slate-800 p-3 text-center'>
					<p className='text-xs text-gray-400 dark:text-gray-500 mb-0.5'>ER</p>
					<p className='font-semibold text-gray-800 dark:text-gray-100 text-sm'>{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}</p>
				</div>
				<div className='bg-white dark:bg-slate-800 p-3 text-center'>
					<p className='text-xs text-gray-400 dark:text-gray-500 mb-0.5'>Вік</p>
					<p className='font-semibold text-gray-800 dark:text-gray-100 text-sm'>{formatAge(channel.age)}</p>
				</div>
				<div className='bg-white dark:bg-slate-800 p-3 text-center'>
					<p className='text-xs text-gray-400 dark:text-gray-500 mb-0.5'>Дохід/міс</p>
					<p className='font-semibold text-gray-800 dark:text-gray-100 text-sm'>
						{channel.monthly_income ? `${channel.monthly_income.toLocaleString('uk-UA')}` : '—'}
					</p>
				</div>
			</div>

			{/* Bottom: Price + Actions */}
			<div className='p-4 pt-3 border-t border-gray-100 dark:border-slate-700'>
				{channel.rejection_reason && (
					<div className='mb-3 px-3 py-2 bg-red-50 rounded-lg border border-red-100'>
						<p className='text-xs text-red-600'>
							<span className='font-semibold'>Причина:</span> {channel.rejection_reason}
						</p>
					</div>
				)}
				<div className='flex items-center justify-between'>
					<div>
						<p className='text-xs text-gray-400 dark:text-gray-500'>Ціна</p>
						<p className='text-lg font-bold text-gray-800 dark:text-white'>{channel.price?.toLocaleString('uk-UA')} <span className='text-sm text-gray-500'>USDT</span></p>
					</div>
					<div className='flex items-center gap-2'>
						{onDelete && channel.status !== 'sold' && (
							<button
								onClick={() => onDelete(channel.id)}
								className='w-9 h-9 rounded-lg border border-gray-200 dark:border-slate-600 text-gray-400 hover:text-red-500 hover:border-red-200 hover:bg-red-50 dark:hover:bg-red-900/30 duration-300 flex items-center justify-center'
								title='Видалити'
							>
								<FontAwesomeIcon icon={faTrash} size='sm' />
							</button>
						)}
						<NavLink
							to={`/channel/${channel.id}`}
							className='flex items-center gap-1.5 px-4 py-2 bg-[#3498db] text-white text-sm font-semibold rounded-lg hover:bg-[#2980b9] duration-300'
						>
							Деталі
							<FontAwesomeIcon icon={faArrowRight} size='xs' />
						</NavLink>
					</div>
				</div>
			</div>
		</div>
	);
};

export default CabinetCard;
