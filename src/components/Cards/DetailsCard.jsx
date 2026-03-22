import { faHeart } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useAuth } from '../../context/AppContext';

const DetailsCard = ({ channel, onBuy }) => {
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

				{channel.telegram_link && (
					<a
						href={channel.telegram_link}
						target='_blank'
						rel='noopener noreferrer'
						className='inline-flex items-center gap-1.5 mt-3 text-[#3498db] bg-blue-50 hover:bg-blue-100 text-sm font-semibold px-4 py-2 rounded-xl transition-all duration-300'
					>
						↗ Переглянути канал
					</a>
				)}

				{channel.category && (
					<span className='inline-block mt-3 bg-blue-50 text-[#3498db] text-xs font-semibold px-3 py-1 rounded-lg'>
						{channel.category}
					</span>
				)}
			</div>

			{/* Stats grid */}
			<div className='px-5 pb-4'>
				<div className='grid grid-cols-2 gap-3'>
					<div className='bg-gray-50 rounded-xl p-3'>
						<p className='text-gray-400 text-xs mb-0.5'>Переглядів</p>
						<p className='font-bold text-gray-800'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3'>
						<p className='text-gray-400 text-xs mb-0.5'>ER</p>
						<p className='font-bold text-gray-800'>{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3'>
						<p className='text-gray-400 text-xs mb-0.5'>Вік</p>
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

			{/* Price + Actions */}
			<div className='border-t border-gray-100 px-5 py-4'>
				<div className='flex items-center justify-between mb-4'>
					<div>
						<p className='text-gray-400 text-xs'>Ціна</p>
						<p className='font-extrabold text-2xl text-gray-900'>
							{channel.price?.toLocaleString('uk-UA')}
							<span className='text-sm font-semibold text-gray-400 ml-1'>USDT</span>
						</p>
					</div>
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
