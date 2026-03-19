import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { channelsAPI, favoritesAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import CabinetCard from '../components/Cards/CabinetCard';
import CatalogCard from '../components/Cards/CatalogCard';

const TABS = [
	{ text: 'Мої оголошення', value: 'my' },
	{ text: 'Обране', value: 'favorites' },
];

const STATUS_FILTERS = [
	{ text: 'Всі', value: null },
	{ text: 'Опубліковані', value: 'approved' },
	{ text: 'На модерації', value: 'pending' },
	{ text: 'Відхилені', value: 'rejected' },
];

const CabinetPage = () => {
	const { user } = useAuth();
	const [activeTab, setActiveTab] = useState(TABS[0]);
	const [activeFilter, setActiveFilter] = useState(STATUS_FILTERS[0]);
	const [channels, setChannels] = useState([]);
	const [favorites, setFavorites] = useState([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		const fetchData = async () => {
			setLoading(true);
			try {
				if (activeTab.value === 'my') {
					const params = { seller_id: user?.id };
					if (activeFilter.value) {
						params.status = activeFilter.value;
					}
					const { data } = await channelsAPI.getAll(params);
					setChannels(data.items || data);
				} else {
					const { data } = await favoritesAPI.getAll();
					setFavorites(data);
				}
			} catch (err) {
				console.error('Failed to load:', err);
			} finally {
				setLoading(false);
			}
		};
		if (user?.id) fetchData();
	}, [user?.id, activeTab, activeFilter]);

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
			<h1 className='uppercase leading-normal md:text-left text-center tracking-widest font-bold md:text-3xl text-2xl lg:text-4xl text-[#3498db] mb-4 md:pl-[18%]'>
				{activeTab.value === 'my' ? 'мої оголошення' : 'обране'}
			</h1>
			<div className='flex gap-3 mb-6 md:pl-[18%]'>
				{TABS.map(tab => (
					<button
						key={tab.value}
						onClick={() => setActiveTab(tab)}
						className={`px-4 py-2 rounded-full font-semibold duration-300 ${
							activeTab.value === tab.value
								? 'bg-[#3498db] text-white'
								: 'bg-gray-100 text-gray-600 hover:bg-gray-200'
						}`}
					>
						{tab.text}
					</button>
				))}
			</div>
			<div className='flex md:flex-row flex-col items-start w-[90vw] gap-4 justify-between'>
				<aside className='md:w-[20%]'>
					{activeTab.value === 'my' ? (
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
					) : (
						<p className='text-gray-500 text-sm'>Канали, які ви додали в обране</p>
					)}
				</aside>
				<div className='w-[100%]'>
					{loading ? (
						<div className='flex justify-center py-20'>
							<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
						</div>
					) : activeTab.value === 'my' ? (
						filteredChannels.length === 0 ? (
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
						)
					) : (
						favorites.length === 0 ? (
							<p className='text-lg font-semibold text-gray-500'>
								У вас поки немає обраних каналів.
								<br />
								<NavLink to='/catalog' className='text-[#3498db] hover:underline'>Перейти до каталогу</NavLink>
							</p>
						) : (
							<div className='md:grid flex flex-col 2xl:grid-cols-3 md:grid-cols-2 gap-8 justify-between'>
								{favorites.map(channel => (
									<CatalogCard key={channel.id} channel={channel} />
								))}
							</div>
						)
					)}
				</div>
			</div>
		</section>
	);
};

export default CabinetPage;
