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
	faTrash,
	faPen,
	faSave,
	faList,
} from '@fortawesome/free-solid-svg-icons';

const TABS = [
	{ text: 'Канали на модерації', value: 'channels' },
	{ text: 'Всі канали', value: 'all_channels' },
	{ text: 'Спірні угоди', value: 'disputes' },
];

const ModerCabinet = () => {
	const [activeTab, setActiveTab] = useState(TABS[0]);
	const [pendingChannels, setPendingChannels] = useState([]);
	const [allChannels, setAllChannels] = useState([]);
	const [disputes, setDisputes] = useState([]);
	const [loading, setLoading] = useState(true);
	const [rejectId, setRejectId] = useState(null);
	const [rejectReason, setRejectReason] = useState('');
	const [editId, setEditId] = useState(null);
	const [editData, setEditData] = useState({});
	const [statusFilter, setStatusFilter] = useState('');

	useEffect(() => {
		loadData();
	}, [activeTab, statusFilter]);

	const loadData = async () => {
		setLoading(true);
		try {
			if (activeTab.value === 'channels') {
				const { data } = await adminAPI.getPendingChannels();
				setPendingChannels(Array.isArray(data) ? data : data.items || []);
			} else if (activeTab.value === 'all_channels') {
				const params = statusFilter ? { status: statusFilter } : {};
				const { data } = await adminAPI.getAllChannels(params);
				setAllChannels(Array.isArray(data) ? data : data.items || []);
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

	const handleDeleteChannel = async (id) => {
		if (!confirm('Видалити канал?')) return;
		try {
			await adminAPI.deleteChannel(id);
			setAllChannels(prev => prev.filter(c => c.id !== id));
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка видалення');
		}
	};

	const startEdit = (channel) => {
		setEditId(channel.id);
		setEditData({
			category: channel.category || '',
			price: channel.price || '',
			monthly_income: channel.monthly_income || '',
			description: channel.description || '',
		});
	};

	const handleSaveEdit = async (id) => {
		try {
			const payload = {
				...editData,
				price: parseFloat(editData.price) || 0,
				monthly_income: editData.monthly_income ? parseFloat(editData.monthly_income) : null,
			};
			const { data } = await adminAPI.updateChannel(id, payload);
			setAllChannels(prev => prev.map(c => (c.id === id ? data : c)));
			setEditId(null);
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка збереження');
		}
	};

	const STATUS_LABELS = {
		pending: 'На модерації',
		approved: 'Опубліковано',
		rejected: 'Відхилено',
		sold: 'Продано',
	};

	const STATUS_COLORS = {
		pending: 'bg-yellow-100 text-yellow-700',
		approved: 'bg-green-100 text-green-700',
		rejected: 'bg-red-100 text-red-700',
		sold: 'bg-blue-100 text-blue-700',
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
					) : activeTab.value === 'all_channels' ? (
						<>
							<div className='flex gap-2 mb-4 flex-wrap'>
								{['', 'pending', 'approved', 'rejected', 'sold'].map(s => (
									<button
										key={s}
										onClick={() => setStatusFilter(s)}
										className={`px-3 py-1 rounded-full text-sm font-semibold duration-300 ${
											statusFilter === s
												? 'bg-blue-500 text-white'
												: 'bg-gray-100 text-gray-600 hover:bg-gray-200'
										}`}
									>
										{s ? STATUS_LABELS[s] : 'Всі'}
									</button>
								))}
							</div>
							{allChannels.length === 0 ? (
								<p className='text-lg text-gray-500'>Немає каналів</p>
							) : (
								<div className='grid gap-4'>
									{allChannels.map(channel => (
										<div key={channel.id} className='bg-white rounded-lg shadow-md p-5'>
											<div className='flex flex-col md:flex-row md:items-center justify-between gap-3 mb-3'>
												<div className='flex items-center gap-3'>
													{channel.avatar_url ? (
														<img className='w-12 h-12 rounded-full object-cover' src={channel.avatar_url} alt='' />
													) : (
														<div className='w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center text-lg font-bold text-blue-500'>
															{channel.channel_name?.[0] || '?'}
														</div>
													)}
													<div>
														<h3 className='font-bold'>{channel.channel_name}</h3>
														<a href={channel.telegram_link} target='_blank' rel='noopener noreferrer' className='text-blue-500 text-sm hover:underline'>
															{channel.telegram_link} <FontAwesomeIcon icon={faExternalLinkAlt} size='xs' />
														</a>
													</div>
												</div>
												<div className='flex items-center gap-2'>
													<span className={`text-xs px-2 py-1 rounded-full font-semibold ${STATUS_COLORS[channel.status] || 'bg-gray-100'}`}>
														{STATUS_LABELS[channel.status] || channel.status}
													</span>
													<button onClick={() => editId === channel.id ? setEditId(null) : startEdit(channel)} className='text-blue-500 hover:text-blue-700 p-1'>
														<FontAwesomeIcon icon={faPen} />
													</button>
													<button onClick={() => handleDeleteChannel(channel.id)} className='text-red-500 hover:text-red-700 p-1'>
														<FontAwesomeIcon icon={faTrash} />
													</button>
												</div>
											</div>

											<div className='grid grid-cols-2 md:grid-cols-5 gap-2 text-sm'>
												<div className='bg-gray-50 p-2 rounded'>
													<FontAwesomeIcon icon={faUsers} className='text-gray-400 mr-1' />
													<span className='font-semibold'>{channel.subscribers_count?.toLocaleString('uk-UA') || '—'}</span>
													<p className='text-gray-400 text-xs'>підписників</p>
												</div>
												<div className='bg-gray-50 p-2 rounded'>
													<FontAwesomeIcon icon={faEye} className='text-gray-400 mr-1' />
													<span className='font-semibold'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</span>
													<p className='text-gray-400 text-xs'>переглядів</p>
												</div>
												<div className='bg-gray-50 p-2 rounded'>
													<FontAwesomeIcon icon={faBarChart} className='text-gray-400 mr-1' />
													<span className='font-semibold'>{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}</span>
													<p className='text-gray-400 text-xs'>ER</p>
												</div>
												<div className='bg-gray-50 p-2 rounded'>
													<span className='font-semibold text-green-600'>{channel.price?.toLocaleString('uk-UA')} USDT</span>
													<p className='text-gray-400 text-xs'>ціна</p>
												</div>
												<div className='bg-gray-50 p-2 rounded'>
													<FontAwesomeIcon icon={faList} className='text-gray-400 mr-1' />
													<span className='font-semibold'>{channel.category || '—'}</span>
													<p className='text-gray-400 text-xs'>категорія</p>
												</div>
											</div>

											{channel.seller_telegram && (
												<p className='mt-2 text-sm bg-purple-50 p-2 rounded'>
													<span className='font-semibold'>Telegram продавця:</span>{' '}
													<a href={`https://t.me/${channel.seller_telegram.replace('@', '')}`} target='_blank' rel='noopener noreferrer' className='text-blue-500 hover:underline'>
														{channel.seller_telegram}
													</a>
												</p>
											)}

											{channel.description && (
												<p className='mt-2 text-gray-600 text-sm bg-blue-50 p-2 rounded'>{channel.description}</p>
											)}

											{editId === channel.id && (
												<div className='mt-3 grid md:grid-cols-2 gap-3 bg-gray-50 p-3 rounded'>
													<div>
														<label className='text-xs text-gray-500'>Категорія</label>
														<input value={editData.category} onChange={e => setEditData({ ...editData, category: e.target.value })} className='w-full border rounded px-2 py-1 text-sm' />
													</div>
													<div>
														<label className='text-xs text-gray-500'>Ціна (USDT)</label>
														<input value={editData.price} onChange={e => setEditData({ ...editData, price: e.target.value })} className='w-full border rounded px-2 py-1 text-sm' />
													</div>
													<div>
														<label className='text-xs text-gray-500'>Дохід/міс (USDT)</label>
														<input value={editData.monthly_income} onChange={e => setEditData({ ...editData, monthly_income: e.target.value })} className='w-full border rounded px-2 py-1 text-sm' />
													</div>
													<div>
														<label className='text-xs text-gray-500'>Опис</label>
														<input value={editData.description} onChange={e => setEditData({ ...editData, description: e.target.value })} className='w-full border rounded px-2 py-1 text-sm' />
													</div>
													<button onClick={() => handleSaveEdit(channel.id)} className='bg-green-500 text-white px-3 py-1 rounded text-sm font-semibold hover:bg-green-600 flex items-center gap-1 w-fit'>
														<FontAwesomeIcon icon={faSave} /> Зберегти
													</button>
												</div>
											)}
										</div>
									))}
								</div>
							)}
						</>
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
