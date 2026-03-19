import {
	faBarChart,
	faChartLine,
	faClock,
	faEye,
	faHeart,
	faDollarSign,
	faListAlt,
	faUsers,
	faWallet,
} from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AppContext';
import { dealsAPI } from '../../services/api';

const CatalogCard = ({ channel }) => {
	const navigate = useNavigate();
	const { isAuthenticated } = useAuth();

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
		<div className='bg-white rounded-md shadow-lg px-4 py-8'>
			<div className='flex items-center lg:flex-row flex-col gap-5 sm:gap-10 border-b-[1px] border-gray-400 pb-2'>
				{channel.avatar_url ? (
					<img className='w-20 h-20 rounded-full' src={channel.avatar_url} alt='' />
				) : (
					<div className='w-20 h-20 rounded-full bg-[#3498db] flex items-center justify-center text-white text-2xl font-bold'>
						{channel.channel_name?.[0] || 'T'}
					</div>
				)}
				<div>
					<h5 className='font-bold mb-3'>{channel.channel_name || 'Без назви'}</h5>
					<div className='flex gap-1 items-center mb-3'>
						<FontAwesomeIcon icon={faUsers} className='text-gray-500' />
						<p className='text-gray-500'>{channel.subscribers_count?.toLocaleString('uk-UA') || '0'} підписників</p>
					</div>
					{channel.daily_growth != null && (
						<div className='flex gap-1 items-center'>
							<FontAwesomeIcon icon={faChartLine} className='text-gray-500' />
							<p className='text-gray-500'>
								{channel.daily_growth >= 0 ? '+' : ''}{channel.daily_growth?.toLocaleString('uk-UA')} за вчора
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
			{channel.age && (
				<div className='border-b-[1px] border-gray-400 p-2 mt-2'>
					<div className='flex items-center gap-2 mb-2'>
						<FontAwesomeIcon icon={faClock} />
						<p className='font-bold'>Вік</p>
					</div>
					<p className='text-gray-500'>{formatAge(channel.age)}</p>
				</div>
			)}
			<div className='border-b-[1px] border-gray-400 p-2 grid lg:grid-cols-2 mt-2'>
				<div className='border-gray-400 lg:border-r-[1px] border-b-[1px] lg:border-b-[0]'>
					<div className='flex gap-2 mb-2'>
						<FontAwesomeIcon icon={faEye} />
						<p className='font-bold'>Переглядів</p>
					</div>
					<p className='text-gray-500 mb-2 lg:mb-0'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</p>
				</div>
				<div className='sm:pl-2 pt-2 mt-2 lg:pt-0 lg:mt-0'>
					<div className='flex gap-2 mb-2 '>
						<FontAwesomeIcon icon={faBarChart} />
						<p className='font-bold'>ER</p>
					</div>
					<p className='text-gray-500'>{channel.er ? `${channel.er}%` : '—'}</p>
				</div>
			</div>
			{channel.monthly_income != null && (
				<div className='border-b-[1px] border-gray-400 p-2 mt-2'>
					<div className='flex items-center gap-2 mb-2'>
					<FontAwesomeIcon icon={faDollarSign} />
					<p className='font-bold'>Прибуток в місяць</p>
				</div>
				<p className='text-gray-500'>{channel.monthly_income?.toLocaleString('uk-UA')} USDT</p>
				</div>
			)}
			<div className='border-b-[1px] border-gray-400 p-2 mt-2'>
				<div className='flex items-center gap-2 mb-2'>
					<FontAwesomeIcon icon={faWallet} />
					<p className='font-bold'>Ціна</p>
				</div>
				<p className='text-gray-500'>{channel.price?.toLocaleString('uk-UA') || '—'} USDT</p>
			</div>
			<div className='flex justify-center my-6'>
				<NavLink
					to={`/channel/${channel.id}`}
					className='font-bold border-b-[1px] border-transparent duration-500 hover:border-black pb-1'
				>
					Детальніше
				</NavLink>
			</div>
			<div className='flex flex-row sm:gap-0 gap-3 justify-between items-center'>
				<button
					onClick={handleBuy}
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

export default CatalogCard;
