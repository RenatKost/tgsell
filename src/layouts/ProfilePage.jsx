import { useAuth } from '../context/AppContext';
import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { dealsAPI } from '../services/api';

const ProfilePage = () => {
	const { user } = useAuth();
	const [deals, setDeals] = useState([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		dealsAPI.getMy()
			.then(({ data }) => setDeals(data))
			.catch(() => {})
			.finally(() => setLoading(false));
	}, []);

	if (!user) return null;

	return (
		<section className='my-28 max-w-3xl mx-auto'>
			<h1 className='uppercase tracking-widest font-bold text-3xl text-[#3498db] mb-8'>
				Профіль
			</h1>

			{/* User Info */}
			<div className='bg-white rounded-md shadow-lg p-6 mb-6'>
				<div className='flex items-center gap-4 mb-6'>
					{user.avatar_url ? (
						<img src={user.avatar_url} alt='' className='w-16 h-16 rounded-full' />
					) : (
						<div className='w-16 h-16 rounded-full bg-[#3498db] flex items-center justify-center text-white text-2xl font-bold'>
							{user.first_name?.[0]}
						</div>
					)}
					<div>
						<h2 className='text-xl font-bold'>{user.first_name}</h2>
						{user.username && <p className='text-gray-500'>@{user.username}</p>}
					</div>
				</div>
				<div className='grid grid-cols-2 gap-4'>
					<div>
						<p className='text-gray-500 text-sm'>Telegram ID</p>
						<p className='font-bold'>{user.telegram_id}</p>
					</div>
					<div>
						<p className='text-gray-500 text-sm'>Роль</p>
						<p className='font-bold capitalize'>{user.role || 'user'}</p>
					</div>
					<div>
						<p className='text-gray-500 text-sm'>USDT Гаманець (TRC-20)</p>
						<p className='font-bold font-mono text-sm'>{user.usdt_wallet || 'Не вказано'}</p>
					</div>
					<div>
						<p className='text-gray-500 text-sm'>Дата реєстрації</p>
						<p className='font-bold'>
							{user.created_at ? new Date(user.created_at).toLocaleDateString('uk-UA') : '—'}
						</p>
					</div>
				</div>
			</div>

			{/* Deals History */}
			<div className='bg-white rounded-md shadow-lg p-6'>
				<h3 className='font-bold text-lg mb-4'>Історія угод</h3>
				{loading ? (
					<div className='flex justify-center py-4'>
						<div className='animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-[#3498db]'></div>
					</div>
				) : deals.length === 0 ? (
					<p className='text-gray-500'>Угод поки немає</p>
				) : (
					<div className='space-y-3'>
						{deals.map(deal => (
							<NavLink
								key={deal.id}
								to={`/deal/${deal.id}`}
								className='flex items-center justify-between p-3 rounded-md hover:bg-gray-50 duration-300 border'
							>
								<div>
									<p className='font-bold'>Угода #{deal.id}</p>
									<p className='text-gray-500 text-sm'>
										{deal.channel_name || `Канал #${deal.channel_id}`}
									</p>
								</div>
								<div className='text-right'>
									<p className='font-bold text-[#27ae60]'>{deal.amount_usdt} USDT</p>
									<p className='text-gray-500 text-sm capitalize'>{deal.status}</p>
								</div>
							</NavLink>
						))}
					</div>
				)}
			</div>
		</section>
	);
};

export default ProfilePage;
