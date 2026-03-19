import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { channelsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import CabinetCard from '../components/Cards/CabinetCard';

const STATUS_FILTERS = [
	{ text: 'Всі', value: null },
	{ text: 'Опубліковані', value: 'approved' },
	{ text: 'На модерації', value: 'pending' },
	{ text: 'Відхилені', value: 'rejected' },
];

const CabinetPage = () => {
	const { user } = useAuth();
	const [activeFilter, setActiveFilter] = useState(STATUS_FILTERS[0]);
	const [channels, setChannels] = useState([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		const fetchChannels = async () => {
			setLoading(true);
			try {
				const params = { seller_id: user?.id };
				if (activeFilter.value) {
					params.status = activeFilter.value;
				}
				const { data } = await channelsAPI.getAll(params);
				setChannels(data.items || data);
			} catch (err) {
				console.error('Failed to load channels:', err);
			} finally {
				setLoading(false);
			}
		};
		if (user?.id) fetchChannels();
	}, [user?.id, activeFilter]);

	const handleDelete = async (channelId) => {
		if (!confirm('Видалити оголошення?')) return;
		try {
			await channelsAPI.delete(channelId);
			setChannels(prev => prev.filter(c => c.id !== channelId));
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка видалення');
		}
	};

	const filteredChannels = activeFilter.value
		? channels.filter(c => c.status === activeFilter.value)
		: channels;

	return (
		<section className='my-28'>
			<h1 className='uppercase leading-normal md:text-left text-center tracking-widest font-bold md:text-3xl text-2xl lg:text-4xl text-[#3498db] mb-8 md:pl-[18%]'>
				мої оголошення
			</h1>
			<div className='flex md:flex-row flex-col items-start w-[90vw] gap-4 justify-between'>
				<aside className='md:w-[20%]'>
					<ul className='grid space-y-3 font-semibold'>
						{STATUS_FILTERS.map(f => (
							<li
								onClick={() => setActiveFilter(f)}
								className={
									f === activeFilter
										? 'text-[#27ae60] inline-block cursor-pointer duration-500'
										: 'text-[#3498db] hover:text-[#27ae60] inline-block cursor-pointer duration-500'
								}
								key={f.text}
							>
								{f.text}
							</li>
						))}
					</ul>
				</aside>
				<div className='w-[100%]'>
					{loading ? (
						<div className='flex justify-center py-20'>
							<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
						</div>
					) : filteredChannels.length === 0 ? (
						<>
							<p className='text-lg font-semibold'>
								Тут будуть відображатися ваші майбутні оголошення.
								<br /> Наразі у вас немає активних оголошень.
							</p>
							<NavLink
								className='mt-10 inline-block font-bold bg-[#27ae60] text-white py-4 px-6 rounded-md shadow-md shadow-green-400 hover:bg-white hover:text-[#27ae60] duration-500'
								to='/sell'
							>
								ПРОДАТИ КАНАЛ
							</NavLink>
						</>
					) : (
						<div className='md:grid flex flex-col 2xl:grid-cols-3 md:grid-cols-2 gap-8 justify-between'>
							{filteredChannels.map(channel => (
								<CabinetCard key={channel.id} channel={channel} onDelete={handleDelete} />
							))}
						</div>
					)}
				</div>
			</div>
		</section>
	);
};

export default CabinetPage;
