import {
	faBarChart,
	faClock,
	faEye,
	faHeart,
	faDollarSign,
	faListAlt,
	faWallet,
} from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';

const DetailsCard = ({ channel, onBuy }) => {
	const formatAge = (months) => {
		if (!months) return '—';
		const m = typeof months === 'string' ? parseInt(months, 10) : months;
		if (isNaN(m)) return '—';
		const y = Math.floor(m / 12);
		const rem = m % 12;
		return y > 0 ? `${y} р. ${rem} міс.` : `${rem} міс.`;
	};

	return (
		<div className='bg-white rounded-md shadow-lg px-4 py-8'>
			<div className='flex items-center lg:flex-row flex-col gap-5 sm:gap-10 border-b-[1px] border-gray-400 pb-2'>
				{channel.avatar_url ? (
					<img className='w-20 h-20 rounded-full object-cover' src={channel.avatar_url} alt={channel.channel_name} />
				) : (
					<div className='w-20 h-20 rounded-full bg-blue-100 flex items-center justify-center text-2xl font-bold text-blue-500'>
						{channel.channel_name?.[0] || '?'}
					</div>
				)}
				<div className='min-w-0'>
					<h5 className='font-bold mb-6'>{channel.channel_name}</h5>
					{channel.telegram_link && (
						<a
							href={channel.telegram_link}
							target='_blank'
							rel='noopener noreferrer'
							className='border-2 border-sky-500 px-3 py-2 rounded-md text-sky-500 hover:bg-sky-500 hover:text-white duration-500 whitespace-nowrap text-sm'
						>
							переглянути канал
						</a>
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
			<div className='border-b-[1px] border-gray-400 p-2 grid grid-cols-2 gap-4 mt-2'>
				<div className='border-r-[1px] border-gray-400 pr-4'>
					<div className='flex items-center gap-2 mb-2'>
						<FontAwesomeIcon icon={faEye} />
						<p className='font-bold'>Переглядів</p>
					</div>
					<p className='text-gray-500'>
						{channel.avg_views?.toLocaleString('uk-UA') || '—'}
					</p>
				</div>
				<div>
					<div className='flex items-center gap-2 mb-2'>
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
					<FontAwesomeIcon icon={faDollarSign} />
					<p className='font-bold'>Прибуток в місяць</p>
				</div>
				<p className='text-gray-500'>
					{channel.monthly_income
						? `${channel.monthly_income.toLocaleString('uk-UA')} USDT`
						: '—'}
				</p>
			</div>
			<div className='border-b-[1px] border-gray-400 p-2 mt-2'>
				<div className='flex items-center gap-2 mb-2'>
					<FontAwesomeIcon icon={faWallet} />
					<p className='font-bold'>Ціна</p>
				</div>
				<p className='text-gray-500'>
					{channel.price?.toLocaleString('uk-UA')} USDT
				</p>
			</div>
			<div className='flex flex-row sm:gap-0 gap-3 justify-between items-center mt-4'>
				<button
					onClick={onBuy}
					className='font-bold bg-[#27ae60] sm:w-[65%] text-white py-2 px-6 rounded-md shadow-lg hover:shadow-green-400 duration-500'
				>
					Купити
				</button>
				<button className='font-bold bg-[#3498db] text-white py-2 px-6 rounded-md shadow-md hover:text-red-500 duration-500'>
					<FontAwesomeIcon icon={faHeart} />
				</button>
			</div>
		</div>
	);
};

export default DetailsCard;
