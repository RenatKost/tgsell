import {
	faBarChart,
	faChartLine,
	faClock,
	faEye,
	faHryvniaSign,
	faListAlt,
	faUsers,
	faWallet,
	faTrash,
} from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { NavLink } from 'react-router-dom';

const statusLabels = {
	pending: { text: 'На модерації', color: 'text-yellow-600 bg-yellow-100' },
	approved: { text: 'Опубліковано', color: 'text-green-600 bg-green-100' },
	rejected: { text: 'Відхилено', color: 'text-red-600 bg-red-100' },
	sold: { text: 'Продано', color: 'text-gray-600 bg-gray-100' },
};

const CabinetCard = ({ channel, onDelete }) => {
	const status = statusLabels[channel.status] || statusLabels.pending;

	const formatAge = (months) => {
		if (!months) return '—';
		const y = Math.floor(months / 12);
		const m = months % 12;
		return y > 0 ? `${y} р. ${m} міс.` : `${m} міс.`;
	};

	return (
		<div className='bg-white rounded-md shadow-md px-4 py-8 relative'>
			<span className={`absolute top-2 right-2 text-xs px-2 py-1 rounded-full font-semibold ${status.color}`}>
				{status.text}
			</span>

			<div className='flex items-center lg:flex-row flex-col gap-5 sm:gap-10 border-b-[1px] border-gray-400 pb-2'>
				{channel.avatar_url ? (
					<img className='w-20 h-20 rounded-full object-cover' src={channel.avatar_url} alt={channel.channel_name} />
				) : (
					<div className='w-20 h-20 rounded-full bg-blue-100 flex items-center justify-center text-2xl font-bold text-blue-500'>
						{channel.channel_name?.[0] || '?'}
					</div>
				)}
				<div>
					<NavLink to={`/channel/${channel.id}`} className='font-bold mb-3 hover:text-blue-500 duration-300 block'>
						{channel.channel_name}
					</NavLink>
					<div className='flex gap-1 items-center mb-3'>
						<FontAwesomeIcon icon={faUsers} className='text-gray-500' />
						<p className='text-gray-500'>
							{channel.subscribers_count?.toLocaleString('uk-UA') || '0'} підписників
						</p>
					</div>
					{channel.daily_growth != null && (
						<div className='flex gap-1 items-center'>
							<FontAwesomeIcon icon={faChartLine} className='text-gray-500' />
							<p className='text-gray-500'>
								{channel.daily_growth > 0 ? '+' : ''}{channel.daily_growth} за вчора
							</p>
						</div>
					)}
				</div>
			</div>
			<div className='border-b-[1px] border-gray-400 p-2 mt-2'>
				<div className='flex items-center gap-2 mb-2'>
					<FontAwesomeIcon icon={faListAlt} />
					<p className='font-bold'>Категорія</p>
				</div>
				<p className='text-gray-500'>{channel.category || '—'}</p>
			</div>
			<div className='border-b-[1px] border-gray-400 p-2 mt-2'>
				<div className='flex items-center gap-2 mb-2'>
					<FontAwesomeIcon icon={faClock} />
					<p className='font-bold'>Вік</p>
				</div>
				<p className='text-gray-500'>{formatAge(channel.age)}</p>
			</div>
			<div className='border-b-[1px] border-gray-400 p-2 grid lg:grid-cols-2 mt-2'>
				<div className='border-gray-400 lg:border-r-[1px] border-b-[1px] lg:border-b-[0]'>
					<div className='flex gap-2 mb-2'>
						<FontAwesomeIcon icon={faEye} />
						<p className='font-bold'>Переглядів</p>
					</div>
					<p className='text-gray-500 mb-2 lg:mb-0'>
						{channel.avg_views?.toLocaleString('uk-UA') || '—'}
					</p>
				</div>
				<div className='lg:pl-2 pt-2 mt-2 lg:pt-0 lg:mt-0'>
					<div className='flex gap-2 mb-2'>
						<FontAwesomeIcon icon={faBarChart} />
						<p className='font-bold'>ER</p>
					</div>
					<p className='text-gray-500'>
						{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}
					</p>
				</div>
			</div>
			<div className='border-b-[1px] border-gray-400 p-2 mt-2'>
				<div className='flex items-center gap-2 mb-2'>
					<FontAwesomeIcon icon={faHryvniaSign} />
					<p className='font-bold'>Прибуток в місяць</p>
				</div>
				<p className='text-gray-500'>
					{channel.monthly_income
						? `${channel.monthly_income.toLocaleString('uk-UA')} ₴`
						: '—'}
				</p>
			</div>
			<div className='border-b-[1px] border-gray-400 p-2 mt-2'>
				<div className='flex items-center gap-2 mb-2'>
					<FontAwesomeIcon icon={faWallet} />
					<p className='font-bold'>Ціна</p>
				</div>
				<p className='text-gray-500'>{channel.price?.toLocaleString('uk-UA')} USDT</p>
			</div>

			{channel.rejection_reason && (
				<div className='mt-3 p-2 bg-red-50 rounded-md'>
					<p className='text-sm text-red-600'>
						<span className='font-bold'>Причина відхилення:</span> {channel.rejection_reason}
					</p>
				</div>
			)}

			{onDelete && channel.status !== 'sold' && (
				<div className='flex justify-end mt-3'>
					<button
						onClick={() => onDelete(channel.id)}
						className='text-red-400 hover:text-red-600 duration-300'
						title='Видалити оголошення'
					>
						<FontAwesomeIcon icon={faTrash} />
					</button>
				</div>
			)}
		</div>
	);
};

export default CabinetCard;
