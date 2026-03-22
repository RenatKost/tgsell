import { faHeart } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AppContext';
import { dealsAPI } from '../../services/api';

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

	const handleBuy = async () => {
		if (!isAuthenticated) {
			alert('Увійдіть для покупки каналу');
			return;
		}
		try {
			const { data } = await dealsAPI.create(channel.id);
			navigate(`/deal/${data.id}`);
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка створення угоди');
		}
	};

	return (
		<div className='group bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-xl hover:shadow-blue-50 transition-all duration-500 overflow-hidden flex flex-col'>
			{/* Header */}
			<div className='p-5 pb-4'>
				<div className='flex items-center gap-4'>
					{channel.avatar_url ? (
						<img className='w-14 h-14 rounded-xl object-cover flex-shrink-0' src={channel.avatar_url} alt='' />
					) : (
						<div className='w-14 h-14 rounded-xl bg-gradient-to-br from-[#3498db] to-[#2573a7] flex items-center justify-center text-white text-xl font-bold flex-shrink-0'>
							{channel.channel_name?.[0] || 'T'}
						</div>
					)}
					<div className='min-w-0'>
						<h5 className='font-bold text-gray-900 truncate'>{channel.channel_name || 'Без назви'}</h5>
						<p className='text-gray-400 text-sm'>
							{channel.subscribers_count?.toLocaleString('uk-UA') || '0'} підписників
						</p>
					</div>
					<button
						onClick={() => isAuthenticated ? toggleFavorite(channel.id) : alert('Увійдіть щоб додати в обране')}
						className={`ml-auto flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center transition-all duration-300 ${
							isFav
								? 'bg-red-50 text-red-500'
								: 'bg-gray-50 text-gray-300 hover:text-red-400 hover:bg-red-50'
						}`}
					>
						<FontAwesomeIcon icon={faHeart} className='text-sm' />
					</button>
				</div>
				{channel.category && (
					<span className='inline-block mt-3 bg-blue-50 text-[#3498db] text-xs font-semibold px-3 py-1 rounded-lg'>
						{channel.category}
					</span>
				)}
			</div>

			{/* Stats grid */}
			<div className='px-5 pb-4 flex-1'>
				<div className='grid grid-cols-2 gap-3'>
					<div className='bg-gray-50 rounded-xl p-3'>
						<p className='text-gray-400 text-xs mb-0.5'>Переглядів</p>
						<p className='font-bold text-gray-800 text-sm'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3'>
						<p className='text-gray-400 text-xs mb-0.5'>ER</p>
						<p className='font-bold text-gray-800 text-sm'>{channel.er ? `${channel.er}%` : '—'}</p>
					</div>
					{channel.daily_growth != null && (
						<div className='bg-gray-50 rounded-xl p-3'>
							<p className='text-gray-400 text-xs mb-0.5'>Приріст</p>
							<p className={`font-bold text-sm ${channel.daily_growth >= 0 ? 'text-green-600' : 'text-red-500'}`}>
								{channel.daily_growth >= 0 ? '+' : ''}{channel.daily_growth?.toLocaleString('uk-UA')}
							</p>
						</div>
					)}
					{channel.age && (
						<div className='bg-gray-50 rounded-xl p-3'>
							<p className='text-gray-400 text-xs mb-0.5'>Вік</p>
							<p className='font-bold text-gray-800 text-sm'>{formatAge(channel.age)}</p>
						</div>
					)}
					{channel.monthly_income != null && (
						<div className='bg-gray-50 rounded-xl p-3 col-span-2'>
							<p className='text-gray-400 text-xs mb-0.5'>Прибуток / місяць</p>
							<p className='font-bold text-gray-800 text-sm'>{channel.monthly_income?.toLocaleString('uk-UA')} USDT</p>
						</div>
					)}
				</div>
			</div>

			{/* Analytics */}
			{(() => {
				const cpm = channel.avg_views && channel.price ? Math.round(channel.price / channel.avg_views * 1000) : null;
				const pricePerSub = channel.subscribers_count && channel.price ? (channel.price / channel.subscribers_count).toFixed(2) : null;
				const payback = channel.monthly_income && channel.price ? (channel.price / channel.monthly_income).toFixed(1) : null;
				if (!cpm && !pricePerSub && !payback) return null;
				return (
					<div className='px-5 pb-4'>
						<div className='grid grid-cols-3 gap-2'>
							<div className='bg-violet-50 rounded-xl p-2.5 text-center'>
								<p className='text-violet-400 text-xs mb-0.5'>CPM</p>
								<p className='font-bold text-violet-700 text-sm'>{cpm != null ? `$${cpm}` : '—'}</p>
							</div>
							<div className='bg-amber-50 rounded-xl p-2.5 text-center'>
								<p className='text-amber-500 text-xs mb-0.5'>$/підписник</p>
								<p className='font-bold text-amber-700 text-sm'>{pricePerSub ?? '—'}</p>
							</div>
							<div className='bg-emerald-50 rounded-xl p-2.5 text-center'>
								<p className='text-emerald-500 text-xs mb-0.5'>Окупність</p>
								<p className='font-bold text-emerald-700 text-sm'>{payback ? `${payback} міс.` : '—'}</p>
							</div>
						</div>
					</div>
				);
			})()}

			{/* Footer */}
			<div className='border-t border-gray-100 px-5 py-4 flex items-center justify-between'>
				<div>
					<p className='text-gray-400 text-xs'>Ціна</p>
					<p className='font-extrabold text-lg text-gray-900'>{channel.price?.toLocaleString('uk-UA') || '—'} <span className='text-sm font-semibold text-gray-400'>USDT</span></p>
				</div>
				<div className='flex gap-2'>
					<NavLink
						to={`/channel/${channel.id}`}
						className='px-4 py-2.5 rounded-xl text-sm font-semibold text-gray-500 bg-gray-50 hover:bg-gray-100 transition-all duration-300'
					>
						Деталі
					</NavLink>
					<button
						onClick={handleBuy}
						className='px-5 py-2.5 rounded-xl text-sm font-bold bg-[#27ae60] text-white hover:bg-green-600 shadow-sm hover:shadow-md hover:shadow-green-100 transition-all duration-300'
					>
						Купити
					</button>
				</div>
			</div>
		</div>
	);
};

export default CatalogCard;
