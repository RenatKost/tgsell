import { useEffect, useState } from 'react';
import { useParams, useNavigate, NavLink } from 'react-router-dom';
import { channelsAPI, dealsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import DetailsCard from '../components/Cards/DetailsCard';
import ChannelHealth from '../components/ChanelDetails/ChannelHealth';
import AIRiskScore from '../components/ChanelDetails/AIRiskScore';
import PostsPerDay from '../components/ChanelDetails/Coverage';
import ER from '../components/ChanelDetails/ER';
import Subscribers from '../components/ChanelDetails/Subscribers';
import Views from '../components/ChanelDetails/Views';
import PostsList from '../components/ChanelDetails/PostsList';
import AiAnalysis from '../components/ChanelDetails/AiAnalysis';

const ChannelDetailsPage = () => {
	const { id } = useParams();
	const navigate = useNavigate();
	const { isAuthenticated } = useAuth();
	const [channel, setChannel] = useState(null);
	const [stats, setStats] = useState([]);
	const [health, setHealth] = useState(null);
	const [healthLoading, setHealthLoading] = useState(true);
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

	useEffect(() => {
		if (!channel) return;
		const fetchHealth = async () => {
			try {
				const { data } = await channelsAPI.getHealth(channel.id);
				setHealth(data);
			} catch {
				setHealth(null);
			} finally {
				setHealthLoading(false);
			}
		};
		fetchHealth();
	}, [channel]);

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
				<div className='animate-spin rounded-full h-8 w-8 border-2 border-gray-200 dark:border-card-border border-t-accent' />
			</div>
		);
	}

	if (!channel) return null;

	const resources = channel.resources ? channel.resources.split(',').map(r => r.trim()).filter(Boolean) : [];

	return (
		<section className='pt-28 pb-8'>
			{/* Breadcrumb */}
			<div className='flex items-center gap-1.5 text-xs mb-5 px-0.5'>
				<NavLink to='/catalog' className='text-gray-400 dark:text-gray-500 hover:text-accent transition-colors'>Каталог</NavLink>
				<span className='text-gray-300 dark:text-gray-600'>/</span>
				<span className='text-gray-600 dark:text-gray-300 font-medium'>{channel.channel_name || 'Канал'}</span>
			</div>

			{/* Row 1: DetailsCard + Subscribers + Views — 3 columns */}
			<div className='grid grid-cols-1 lg:grid-cols-[380px_1fr_1fr] gap-4 items-start'>
				<div className='space-y-4'>
					<DetailsCard channel={channel} onBuy={handleBuy} stats={stats} />

					{channel.description && (
					<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm p-4'>
						<h4 className='font-semibold text-gray-900 dark:text-white text-xs uppercase tracking-wider mb-2'>Коментар власника</h4>
						<p className='text-gray-600 dark:text-gray-300 text-xs leading-relaxed bg-blue-50 dark:bg-card-inner rounded-lg p-3'>
							</p>
						</div>
					)}

					{resources.length > 0 && (
					<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm p-4'>
						<h4 className='font-semibold text-gray-900 dark:text-white text-xs uppercase tracking-wider mb-2'>Додаткові ресурси</h4>
						<div className='flex flex-wrap gap-1.5'>
							{resources.map((url, idx) => (
								<a
									key={idx}
									href={url}
									target='_blank'
									rel='noopener noreferrer'
									className='inline-flex items-center gap-1 bg-gray-50 dark:bg-card-inner hover:bg-accent hover:text-white text-gray-600 dark:text-gray-300 font-medium text-[11px] px-3 py-2 rounded-lg border border-gray-200 dark:border-card-border hover:border-accent transition-all'
									>
										<span>🔗</span> Ресурс {idx + 1}
									</a>
								))}
							</div>
						</div>
					)}
				</div>

				<Subscribers stats={stats} current={channel.subscribers_count} />
				<Views stats={stats} current={channel.avg_views} viewsHidden={channel.views_hidden} />
			</div>

			{/* Row 2: ER + PostsPerDay + AI Risk Assessment — 3 columns */}
			<div className='mt-4 grid md:grid-cols-3 gap-4'>
				<ER stats={stats} current={channel.er} />
				<PostsPerDay stats={stats} />
				<AIRiskScore health={health} loading={healthLoading} />
			</div>

			{/* Row 3: Health (left) + AI Analysis with AdvReach (right) */}
			<div className='mt-4 grid md:grid-cols-2 gap-4'>
				<ChannelHealth health={health} loading={healthLoading} />
				<AiAnalysis channelId={channel.id} channel={channel} />
			</div>

			{/* Row 4: Posts full width */}
			<div className='mt-4'>
				<PostsList channelId={channel.id} />
			</div>
		</section>
	);
};

export default ChannelDetailsPage;
