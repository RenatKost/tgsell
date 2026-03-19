import { useEffect, useState } from 'react';
import { adminAPI } from '../services/api';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import {
	faCheck,
	faTimes,
	faUsers,
	faEye,
	faBarChart,
	faExternalLinkAlt,
	faGavel,
} from '@fortawesome/free-solid-svg-icons';

const TABS = [
	{ text: 'Канали на модерації', value: 'channels' },
	{ text: 'Спірні угоди', value: 'disputes' },
];

const ModerCabinet = () => {
	const [activeTab, setActiveTab] = useState(TABS[0]);
	const [pendingChannels, setPendingChannels] = useState([]);
	const [disputes, setDisputes] = useState([]);
	const [loading, setLoading] = useState(true);
	const [rejectId, setRejectId] = useState(null);
	const [rejectReason, setRejectReason] = useState('');

	useEffect(() => {
		loadData();
	}, [activeTab]);

	const loadData = async () => {
		setLoading(true);
		try {
			if (activeTab.value === 'channels') {
				const { data } = await adminAPI.getPendingChannels();
				setPendingChannels(Array.isArray(data) ? data : data.items || []);
			} else {
				const { data } = await adminAPI.getAllDeals({ status: 'disputed' });
				setDisputes(Array.isArray(data) ? data : data.items || []);
			}
		} catch (err) {
			console.error('Failed to load admin data:', err);
		} finally {
			setLoading(false);
		}
	};

	const handleApprove = async (id) => {
		try {
			await adminAPI.approveChannel(id);
			setPendingChannels(prev => prev.filter(c => c.id !== id));
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка');
		}
	};

	const handleReject = async (id) => {
		if (!rejectReason.trim()) {
			alert('Вкажіть причину відхилення');
			return;
		}
		try {
			await adminAPI.rejectChannel(id, rejectReason);
			setPendingChannels(prev => prev.filter(c => c.id !== id));
			setRejectId(null);
			setRejectReason('');
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка');
		}
	};

	const handleResolve = async (dealId, resolution) => {
		try {
			await adminAPI.resolveDeal(dealId, { resolution });
			setDisputes(prev => prev.filter(d => d.id !== dealId));
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка');
		}
	};

	return (
		<div className='my-28'>
			<h1 className='uppercase leading-normal tracking-widest font-bold text-2xl md:text-4xl text-[#3498db] mb-8 md:pl-[20%] text-center md:text-left'>
				Панель модератора
				{activeTab.value === 'channels' && (
					<span className='text-green-500'> ({pendingChannels.length})</span>
				)}
			</h1>
			<div className='flex flex-col md:flex-row items-start w-full gap-6'>
				<aside className='md:w-[20%]'>
					<ul className='grid space-y-3 font-semibold'>
						{TABS.map(tab => (
							<li
								onClick={() => setActiveTab(tab)}
								className={
									tab === activeTab
										? 'text-[#27ae60] inline-block cursor-pointer duration-500'
										: 'text-[#3498db] hover:text-[#27ae60] inline-block cursor-pointer duration-500'
								}
								key={tab.value}
							>
								{tab.text}
							</li>
						))}
					</ul>
				</aside>

				<div className='flex-1'>
					{loading ? (
						<div className='flex justify-center py-20'>
							<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
						</div>
					) : activeTab.value === 'channels' ? (
						pendingChannels.length === 0 ? (
							<p className='text-lg text-gray-500'>Немає каналів на модерації</p>
						) : (
							<div className='grid gap-6'>
								{pendingChannels.map(channel => (
									<div
										key={channel.id}
										className='bg-white rounded-lg shadow-md p-6'
									>
										<div className='flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4'>
											<div className='flex items-center gap-4'>
												{channel.avatar_url ? (
													<img className='w-14 h-14 rounded-full object-cover' src={channel.avatar_url} alt='' />
												) : (
													<div className='w-14 h-14 rounded-full bg-blue-100 flex items-center justify-center text-xl font-bold text-blue-500'>
														{channel.channel_name?.[0] || '?'}
													</div>
												)}
												<div>
													<h3 className='font-bold text-lg'>{channel.channel_name}</h3>
													<a
														href={channel.telegram_link}
														target='_blank'
														rel='noopener noreferrer'
														className='text-blue-500 text-sm hover:underline'
													>
														{channel.telegram_link} <FontAwesomeIcon icon={faExternalLinkAlt} size='xs' />
													</a>
												</div>
											</div>
											<div className='flex gap-3'>
												<button
													onClick={() => handleApprove(channel.id)}
													className='bg-green-500 text-white px-4 py-2 rounded-md font-semibold hover:bg-green-600 duration-300 flex items-center gap-2'
												>
													<FontAwesomeIcon icon={faCheck} /> Схвалити
												</button>
												<button
													onClick={() => setRejectId(rejectId === channel.id ? null : channel.id)}
													className='bg-red-500 text-white px-4 py-2 rounded-md font-semibold hover:bg-red-600 duration-300 flex items-center gap-2'
												>
													<FontAwesomeIcon icon={faTimes} /> Відхилити
												</button>
											</div>
										</div>

										<div className='grid grid-cols-2 md:grid-cols-4 gap-3 text-sm'>
											<div className='bg-gray-50 p-2 rounded'>
												<FontAwesomeIcon icon={faUsers} className='text-gray-400 mr-1' />
												<span className='font-semibold'>{channel.subscribers_count?.toLocaleString('uk-UA') || '—'}</span>
												<p className='text-gray-400'>підписників</p>
											</div>
											<div className='bg-gray-50 p-2 rounded'>
												<FontAwesomeIcon icon={faEye} className='text-gray-400 mr-1' />
												<span className='font-semibold'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</span>
												<p className='text-gray-400'>переглядів</p>
											</div>
											<div className='bg-gray-50 p-2 rounded'>
												<FontAwesomeIcon icon={faBarChart} className='text-gray-400 mr-1' />
												<span className='font-semibold'>{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}</span>
												<p className='text-gray-400'>ER</p>
											</div>
											<div className='bg-gray-50 p-2 rounded'>
												<span className='font-semibold text-green-600'>{channel.price?.toLocaleString('uk-UA')} USDT</span>
												<p className='text-gray-400'>ціна</p>
											</div>
										</div>

										{channel.description && (
											<p className='mt-3 text-gray-600 text-sm bg-blue-50 p-2 rounded'>{channel.description}</p>
										)}

										{rejectId === channel.id && (
											<div className='mt-4 flex gap-2'>
												<input
													type='text'
													value={rejectReason}
													onChange={e => setRejectReason(e.target.value)}
													placeholder='Причина відхилення…'
													className='flex-1 border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-red-300'
												/>
												<button
													onClick={() => handleReject(channel.id)}
													className='bg-red-500 text-white px-4 py-2 rounded-md font-semibold hover:bg-red-600'
												>
													Підтвердити
												</button>
											</div>
										)}
									</div>
								))}
							</div>
						)
					) : disputes.length === 0 ? (
						<p className='text-lg text-gray-500'>Немає спірних угод</p>
					) : (
						<div className='grid gap-6'>
							{disputes.map(deal => (
								<div key={deal.id} className='bg-white rounded-lg shadow-md p-6'>
									<div className='flex items-center justify-between mb-3'>
										<h3 className='font-bold text-lg'>
											<FontAwesomeIcon icon={faGavel} className='mr-2 text-yellow-500' />
											Угода #{deal.id}
										</h3>
										<span className='text-sm text-yellow-600 bg-yellow-100 px-2 py-1 rounded-full'>
											Спір
										</span>
									</div>
									<p className='text-gray-600 mb-2'>
										<span className='font-semibold'>Сума:</span> {deal.amount_usdt} USDT
									</p>
									{deal.dispute_reason && (
										<p className='text-gray-600 mb-4 bg-red-50 p-2 rounded'>
											<span className='font-semibold'>Причина:</span> {deal.dispute_reason}
										</p>
									)}
									<div className='flex gap-3'>
										<button
											onClick={() => handleResolve(deal.id, 'refund_buyer')}
											className='bg-blue-500 text-white px-4 py-2 rounded-md font-semibold hover:bg-blue-600 duration-300'
										>
											Повернути покупцю
										</button>
										<button
											onClick={() => handleResolve(deal.id, 'release_seller')}
											className='bg-green-500 text-white px-4 py-2 rounded-md font-semibold hover:bg-green-600 duration-300'
										>
											Перевести продавцю
										</button>
									</div>
								</div>
							))}
						</div>
					)}
				</div>
			</div>
		</div>
	);
};

export default ModerCabinet;
