import { useEffect, useState } from 'react';
import { useParams, useNavigate, NavLink } from 'react-router-dom';
import { channelsAPI, dealsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import DetailsCard from '../components/Cards/DetailsCard';
import AdvertisingReach from '../components/ChanelDetails/AdvertisingReach';
import PostsPerDay from '../components/ChanelDetails/Coverage';
import ER from '../components/ChanelDetails/ER';
import Subscribers from '../components/ChanelDetails/Subscribers';
import Views from '../components/ChanelDetails/Views';
import PostsList from '../components/ChanelDetails/PostsList';

const ChannelDetailsPage = () => {
	const { id } = useParams();
	const navigate = useNavigate();
	const { isAuthenticated } = useAuth();
	const [channel, setChannel] = useState(null);
	const [stats, setStats] = useState([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		const fetchData = async () => {
			try {
				const [channelRes, statsRes] = await Promise.all([
					channelsAPI.getById(id),
					channelsAPI.getStats(id).catch(() => ({ data: [] })),
				]);
				setChannel(channelRes.data);
				setStats(Array.isArray(statsRes.data) ? statsRes.data : []);
			} catch (err) {
				console.error('Failed to load channel:', err);
				navigate('/catalog');
			} finally {
				setLoading(false);
			}
		};
		fetchData();
	}, [id, navigate]);

	const handleBuy = async () => {
		if (!isAuthenticated) {
			alert('Авторизуйтесь для покупки');
			return;
		}
		try {
			const { data } = await dealsAPI.create(channel.id);
			navigate(`/deal/${data.id}`);
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка створення угоди');
		}
	};

	if (loading) {
		return (
			<div className='mt-28 flex justify-center'>
				<div className='animate-spin rounded-full h-10 w-10 border-2 border-gray-200 border-t-[#3498db]' />
			</div>
		);
	}

	if (!channel) return null;

	const resources = channel.resources ? channel.resources.split(',').map(r => r.trim()).filter(Boolean) : [];

	return (
		<section className='mt-28'>
			{/* Breadcrumb */}
			<div className='flex items-center gap-2 text-sm mb-6 px-1'>
				<NavLink to='/catalog' className='text-gray-400 dark:text-gray-500 hover:text-[#3498db] transition-colors'>Каталог</NavLink>
				<span className='text-gray-300 dark:text-gray-600'>/</span>
				<span className='text-gray-600 dark:text-gray-300 font-medium'>{channel.channel_name || 'Канал'}</span>
			</div>

			<div className='flex flex-col lg:flex-row items-start gap-6'>
				{/* Left column */}
				<div className='w-full lg:w-[460px] flex-shrink-0 space-y-5'>
					<DetailsCard channel={channel} onBuy={handleBuy} stats={stats} />

					{channel.description && (
						<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 shadow-sm p-5'>
							<h4 className='font-bold text-gray-900 dark:text-white mb-3'>Коментар власника</h4>
							<p className='text-gray-600 dark:text-gray-300 text-sm leading-relaxed bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4'>
								{channel.description}
							</p>
						</div>
					)}

					{resources.length > 0 && (
						<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 shadow-sm p-5'>
							<h4 className='font-bold text-gray-900 dark:text-white mb-3'>Додаткові ресурси</h4>
							<div className='flex flex-wrap gap-2'>
								{resources.map((url, idx) => (
									<a
										key={idx}
										href={url}
										target='_blank'
										rel='noopener noreferrer'
										className='inline-flex items-center gap-1.5 bg-gray-50 dark:bg-slate-700 hover:bg-[#3498db] hover:text-white text-gray-600 dark:text-gray-300 font-semibold text-sm px-4 py-2.5 rounded-xl border border-gray-200 dark:border-slate-600 hover:border-[#3498db] transition-all duration-300'
									>
										<span>🔗</span> Ресурс {idx + 1}
									</a>
								))}
							</div>
						</div>
					)}
				</div>

				{/* Right column — charts */}
				<div className='grid 2xl:grid-cols-2 gap-5 w-full'>
					<Subscribers stats={stats} current={channel.subscribers_count} />
					<Views stats={stats} current={channel.avg_views} />
					<ER stats={stats} current={channel.er} />
					<PostsPerDay stats={stats} />
					<AdvertisingReach channel={channel} />
				</div>
			</div>

			{/* Posts section — full width below */}
			<div className='mt-6'>
				<PostsList channelId={channel.id} />
			</div>
		</section>
	);
};

export default ChannelDetailsPage;
