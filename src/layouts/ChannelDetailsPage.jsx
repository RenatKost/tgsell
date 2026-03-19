import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { channelsAPI, dealsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import DetailsCard from '../components/Cards/DetailsCard';
import AdvertisingReach from '../components/ChanelDetails/AdvertisingReach';
import Coverage from '../components/ChanelDetails/Coverage';
import ER from '../components/ChanelDetails/ER';
import Subscribers from '../components/ChanelDetails/Subscribers';
import Views from '../components/ChanelDetails/Views';

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
				<div className='animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500' />
			</div>
		);
	}

	if (!channel) return null;

	// Parse resources
	const resources = channel.resources ? channel.resources.split(',').map(r => r.trim()).filter(Boolean) : [];

	return (
		<section className='mt-28 flex flex-col lg:flex-row items-start gap-6'>
			<div className='grid gap-6'>
				<DetailsCard channel={channel} onBuy={handleBuy} />

				{channel.description && (
					<div className='w-full lg:w-[450px] flex flex-col items-center bg-white rounded-md shadow-lg px-4 py-4'>
						<h4 className='font-bold mb-5 text-lg'>Коментарі від власника</h4>
						<p className='rounded-md bg-blue-500 bg-opacity-[0.15] p-2 leading-normal w-full'>
							{channel.description}
						</p>
					</div>
				)}

				{resources.length > 0 && (
					<div className='w-full lg:w-[450px] flex items-center flex-col gap-4 bg-white rounded-md shadow-lg px-4 py-4'>
						<h4 className='font-bold mb-2 text-lg'>Додаткові ресурси</h4>
						<div className='flex items-center gap-4 flex-wrap'>
							{resources.map((url, idx) => (
								<a
									key={idx}
									href={url}
									target='_blank'
									rel='noopener noreferrer'
									className={`text-white font-bold shadow-md text-xl px-4 w-36 text-center py-2 rounded-md duration-300 ${
										idx % 2 === 0
											? 'bg-[#27ae60] hover:shadow-[#27ae60]'
											: 'bg-[#3498db] hover:shadow-[#3498db]'
									}`}
								>
									Ресурс {idx + 1}
								</a>
							))}
						</div>
					</div>
				)}
			</div>
			<div className='grid 2xl:grid-cols-2 gap-6 w-full'>
				<Subscribers stats={stats} current={channel.subscribers_count} />
				<Coverage stats={stats} current={channel.avg_views} />
				<Views stats={stats} current={channel.avg_views} />
				<ER stats={stats} current={channel.er} />
				<AdvertisingReach channel={channel} />
			</div>
		</section>
	);
};

export default ChannelDetailsPage;
