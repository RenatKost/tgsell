import { useEffect, useRef, useState } from 'react';
import { adminAPI, dealsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
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
	faClipboardCheck,
	faLayerGroup,
	faScaleBalanced,
	faFilter,
	faHandshake,
	faComments,
	faBan,
	faArrowRight,
	faWallet,
	faSync,
	faPaperPlane,
	faCopy,
} from '@fortawesome/free-solid-svg-icons';

const TABS = [
	{ text: 'На модерації', value: 'channels', icon: faClipboardCheck },
	{ text: 'Всі канали', value: 'all_channels', icon: faLayerGroup },
	{ text: 'Всі угоди', value: 'all_deals', icon: faHandshake },
	{ text: 'Спірні угоди', value: 'disputes', icon: faScaleBalanced },
	{ text: 'Ескроу гаманці', value: 'escrow', icon: faWallet },
];

const STATUS_FILTERS = [
	{ text: 'Всі', value: '', dot: 'bg-gray-400' },
	{ text: 'На модерації', value: 'pending', dot: 'bg-yellow-500' },
	{ text: 'Опубліковані', value: 'approved', dot: 'bg-green-500' },
	{ text: 'Відхилені', value: 'rejected', dot: 'bg-red-500' },
	{ text: 'Продані', value: 'sold', dot: 'bg-blue-500' },
];

const DEAL_STATUS_FILTERS = [
	{ text: 'Всі', value: '', dot: 'bg-gray-400' },
	{ text: 'Активні', value: 'active', dot: 'bg-blue-500' },
	{ text: 'Оплачені', value: 'paid', dot: 'bg-indigo-500' },
	{ text: 'Завершені', value: 'completed', dot: 'bg-green-500' },
	{ text: 'Спірні', value: 'disputed', dot: 'bg-red-500' },
	{ text: 'Скасовані', value: 'cancelled', dot: 'bg-gray-500' },
];

const DEAL_STATUS_LABELS = {
	created: { text: 'Очікує оплати', color: 'bg-yellow-100 text-yellow-700' },
	payment_pending: { text: 'Очікує оплати', color: 'bg-yellow-100 text-yellow-700' },
	paid: { text: 'Оплачено', color: 'bg-blue-100 text-blue-700' },
	channel_transferring: { text: 'Передача каналу', color: 'bg-indigo-100 text-indigo-700' },
	completed: { text: 'Завершено', color: 'bg-green-100 text-green-700' },
	disputed: { text: 'Спір', color: 'bg-red-100 text-red-700' },
	cancelled: { text: 'Скасовано', color: 'bg-gray-100 text-gray-600 dark:text-gray-300' },
};

// === Deal Chat Modal ===
const DealChatModal = ({ dealId, userId, onClose }) => {
	const [messages, setMessages] = useState([]);
	const [newMessage, setNewMessage] = useState('');
	const [sending, setSending] = useState(false);
	const messagesEndRef = useRef(null);

	const fetchMessages = async () => {
		try {
			const { data } = await dealsAPI.getMessages(dealId);
			setMessages(data);
		} catch (err) { /* silent */ }
	};

	useEffect(() => {
		fetchMessages();
		const interval = setInterval(fetchMessages, 5000);
		return () => clearInterval(interval);
	}, [dealId]);

	useEffect(() => {
		messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
	}, [messages]);

	const handleSend = async (e) => {
		e.preventDefault();
		const text = newMessage.trim();
		if (!text || sending) return;
		setSending(true);
		try {
			await dealsAPI.sendMessage(dealId, text);
			setNewMessage('');
			await fetchMessages();
		} catch (err) { /* silent */ }
		finally { setSending(false); }
	};

	return (
		<div className='fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4' onClick={onClose}>
			<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col animate-fadeIn' onClick={e => e.stopPropagation()}>
				<div className='bg-gradient-to-r from-[#3498db] to-[#2980b9] text-white p-5 rounded-t-2xl flex items-center justify-between'>
					<h3 className='font-bold text-lg'>💬 Чат угоди #{dealId}</h3>
					<button onClick={onClose} className='text-white/80 hover:text-white text-xl'>✕</button>
				</div>
				<div className='flex-1 overflow-y-auto p-4 bg-gray-50 dark:bg-slate-700/60 min-h-[300px]'>
					{messages.length === 0 && (
						<p className='text-gray-400 text-center mt-20 text-sm'>Повідомлень ще немає</p>
					)}
					{messages.map(msg => {
						if (msg.is_system) {
							return (
								<div key={msg.id} className='mb-3 flex justify-center'>
									<div className='bg-blue-50 text-blue-700 text-xs px-4 py-2 rounded-full font-medium'>
										{msg.text}
									</div>
								</div>
							);
						}
						const isOwn = msg.sender_id === userId;
						return (
							<div key={msg.id} className={`mb-3 flex ${isOwn ? 'justify-end' : 'justify-start'}`}>
								<div className={`max-w-[75%] px-4 py-2 rounded-lg ${isOwn ? 'bg-[#3498db] text-white rounded-br-none' : 'bg-white text-gray-800 rounded-bl-none shadow-sm'}`}>
									{!isOwn && <p className='text-xs font-bold mb-1 opacity-70'>{msg.sender_name || 'Користувач'}</p>}
									<p className='text-sm whitespace-pre-wrap break-words'>{msg.text}</p>
									<p className={`text-xs mt-1 ${isOwn ? 'text-blue-100' : 'text-gray-400'}`}>
										{new Date(msg.created_at).toLocaleString('uk-UA', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })}
									</p>
								</div>
							</div>
						);
					})}
					<div ref={messagesEndRef} />
				</div>
				<form onSubmit={handleSend} className='p-4 border-t border-gray-200 flex gap-2'>
					<input
						type='text'
						value={newMessage}
						onChange={e => setNewMessage(e.target.value)}
						placeholder='Написати як адмін...'
						maxLength={2000}
						className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent'
					/>
					<button
						type='submit'
						disabled={sending || !newMessage.trim()}
						className='bg-[#3498db] text-white px-6 py-2.5 rounded-xl font-semibold hover:bg-[#2980b9] duration-300 disabled:opacity-50'
					>
						{sending ? '...' : 'Надіслати'}
					</button>
				</form>
			</div>
		</div>
	);
};

const ModerCabinet = () => {
	const { user } = useAuth();
	const [activeTab, setActiveTab] = useState(TABS[0]);
	const [pendingChannels, setPendingChannels] = useState([]);
	const [allChannels, setAllChannels] = useState([]);
	const [disputes, setDisputes] = useState([]);
	const [allDeals, setAllDeals] = useState([]);
	const [loading, setLoading] = useState(true);
	const [rejectId, setRejectId] = useState(null);
	const [rejectReason, setRejectReason] = useState('');
	const [editId, setEditId] = useState(null);
	const [editData, setEditData] = useState({});
	const [statusFilter, setStatusFilter] = useState('');
	const [dealStatusFilter, setDealStatusFilter] = useState('');
	const [chatDealId, setChatDealId] = useState(null);
	const [escrowWallets, setEscrowWallets] = useState([]);
	const [escrowTotal, setEscrowTotal] = useState(0);
	const [sweepTarget, setSweepTarget] = useState({});
	const [sweeping, setSweeping] = useState({});

	useEffect(() => {
		loadData();
	}, [activeTab, statusFilter, dealStatusFilter]);

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
			} else if (activeTab.value === 'all_deals') {
				const params = {};
				if (dealStatusFilter === 'active') {
					// Load all; filter client-side
				} else if (dealStatusFilter) {
					params.deal_status = dealStatusFilter;
				}
				const { data } = await adminAPI.getAllDeals(params);
				let items = Array.isArray(data) ? data : data.items || [];
				if (dealStatusFilter === 'active') {
					items = items.filter(d => ['created', 'payment_pending', 'paid', 'channel_transferring'].includes(d.status));
				}
				setAllDeals(items);
			} else if (activeTab.value === 'disputes') {
				const { data } = await adminAPI.getAllDeals({ deal_status: 'disputed' });
				setDisputes(Array.isArray(data) ? data : data.items || []);
			} else if (activeTab.value === 'escrow') {
				const { data } = await adminAPI.getEscrowBalances();
				setEscrowWallets(data.wallets_with_funds || []);
				setEscrowTotal(data.total || 0);
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
			setAllDeals(prev => prev.filter(d => d.id !== dealId));
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка');
		}
	};

	const handleCancelDeal = async (dealId) => {
		if (!confirm('Скасувати цю угоду? Канал повернеться в каталог.')) return;
		try {
			await adminAPI.cancelDeal(dealId);
			setAllDeals(prev => prev.map(d => d.id === dealId ? { ...d, status: 'cancelled' } : d));
			setDisputes(prev => prev.filter(d => d.id !== dealId));
		} catch (err) {
			alert(err.response?.data?.detail || 'Помилка скасування');
		}
	};

	const handleSweep = async (dealId) => {
		const toAddr = sweepTarget[dealId];
		if (!toAddr || !toAddr.trim() || !toAddr.startsWith('T') || toAddr.length < 30) {
			alert('Введіть коректну TRC-20 адресу (починається з T)');
			return;
		}
		if (!confirm(`Перевести USDT з ескроу угоди #${dealId} на ${toAddr}?`)) return;
		setSweeping(prev => ({ ...prev, [dealId]: true }));
		try {
			const { data } = await adminAPI.sweepEscrow(dealId, toAddr.trim());
			if (data.ok) {
				alert(`Переведено ${data.amount_usdt} USDT!\nTx: ${data.usdt_tx}`);
				loadData();
			} else {
				alert(`Помилка: ${data.error}`);
			}
		} catch (err) {
			alert(err.response?.data?.detail || err.response?.data?.error || 'Помилка переводу');
		} finally {
			setSweeping(prev => ({ ...prev, [dealId]: false }));
		}
	};

	const copyToClipboard = (text) => {
		navigator.clipboard.writeText(text);
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
		<section className='pt-28 mb-16'>
			{/* Header */}
			<div className='flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8'>
				<div>
					<h1 className='text-2xl md:text-3xl font-bold text-gray-800 dark:text-white'>
						Панель модератора
					</h1>
					<p className='text-gray-500 mt-1'>Модерація каналів та вирішення спорів</p>
				</div>
				{activeTab.value === 'channels' && pendingChannels.length > 0 && (
					<span className='inline-flex items-center gap-2 bg-yellow-50 text-yellow-700 font-semibold py-2.5 px-5 rounded-xl border border-yellow-200'>
						<span className='w-2.5 h-2.5 rounded-full bg-yellow-500 animate-pulse' />
						{pendingChannels.length} очікують модерації
					</span>
				)}
			</div>

			{/* Tabs */}
			<div className='flex gap-2 mb-6 border-b border-gray-200 dark:border-slate-600'>
				{TABS.map(tab => (
					<button
						key={tab.value}
						onClick={() => setActiveTab(tab)}
						className={`flex items-center gap-2 px-5 py-3 font-semibold text-sm duration-300 border-b-2 -mb-px ${
							activeTab.value === tab.value
								? 'border-[#3498db] text-[#3498db]'
								: 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
						}`}
					>
						<FontAwesomeIcon icon={tab.icon} />
						{tab.text}
						{tab.value === 'disputes' && disputes.length > 0 && (
							<span className='bg-red-100 text-red-600 text-xs px-2 py-0.5 rounded-full'>{disputes.length}</span>
						)}
					</button>
				))}
			</div>

			{/* Content */}
			{loading ? (
				<div className='flex justify-center py-20'>
					<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
				</div>
			) : activeTab.value === 'channels' ? (
				pendingChannels.length === 0 ? (
					<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300'>
						<div className='text-5xl mb-4'>✅</div>
						<p className='text-lg font-semibold text-gray-700 mb-2'>Все перевірено!</p>
						<p className='text-gray-500'>Немає каналів, що очікують модерації</p>
					</div>
				) : (
					<div className='grid gap-6'>
						{pendingChannels.map(channel => (
							<div key={channel.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-6 hover:shadow-md duration-300'>
								<div className='flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4'>
									<div className='flex items-center gap-4'>
										{channel.avatar_url ? (
											<img className='w-14 h-14 rounded-full object-cover ring-2 ring-gray-100' src={channel.avatar_url} alt='' />
										) : (
											<div className='w-14 h-14 rounded-full bg-gradient-to-br from-blue-100 to-blue-200 flex items-center justify-center text-xl font-bold text-blue-500'>
												{channel.channel_name?.[0] || '?'}
											</div>
										)}
										<div>
											<h3 className='font-bold text-lg text-gray-800 dark:text-white'>{channel.channel_name}</h3>
											<a href={channel.telegram_link} target='_blank' rel='noopener noreferrer' className='text-blue-500 text-sm hover:underline'>
												{channel.telegram_link} <FontAwesomeIcon icon={faExternalLinkAlt} size='xs' />
											</a>
										</div>
									</div>
									<div className='flex gap-3'>
										<button
											onClick={() => handleApprove(channel.id)}
											className='bg-[#27ae60] text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-[#219a52] duration-300 flex items-center gap-2 shadow-sm'
										>
											<FontAwesomeIcon icon={faCheck} /> Схвалити
										</button>
										<button
											onClick={() => setRejectId(rejectId === channel.id ? null : channel.id)}
											className='bg-red-500 text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-red-600 duration-300 flex items-center gap-2 shadow-sm'
										>
											<FontAwesomeIcon icon={faTimes} /> Відхилити
										</button>
									</div>
								</div>

								<div className='grid grid-cols-2 md:grid-cols-4 gap-3 text-sm'>
									<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
										<FontAwesomeIcon icon={faUsers} className='text-gray-400 mr-1' />
										<span className='font-semibold'>{channel.subscribers_count?.toLocaleString('uk-UA') || '—'}</span>
										<p className='text-gray-400 text-xs mt-0.5'>підписників</p>
									</div>
									<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
										<FontAwesomeIcon icon={faEye} className='text-gray-400 mr-1' />
										<span className='font-semibold'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</span>
										<p className='text-gray-400 text-xs mt-0.5'>переглядів</p>
									</div>
									<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
										<FontAwesomeIcon icon={faBarChart} className='text-gray-400 mr-1' />
										<span className='font-semibold'>{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}</span>
										<p className='text-gray-400 text-xs mt-0.5'>ER</p>
									</div>
									<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
										<span className='font-semibold text-green-600'>{channel.price?.toLocaleString('uk-UA')} USDT</span>
										<p className='text-gray-400 text-xs mt-0.5'>ціна</p>
									</div>
								</div>

								{channel.description && (
									<p className='mt-4 text-gray-600 text-sm bg-blue-50 p-3 rounded-xl'>{channel.description}</p>
								)}

								{rejectId === channel.id && (
									<div className='mt-4 flex gap-2'>
										<input
											type='text'
											value={rejectReason}
											onChange={e => setRejectReason(e.target.value)}
											placeholder='Причина відхилення…'
											className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-transparent'
										/>
										<button
											onClick={() => handleReject(channel.id)}
											className='bg-red-500 text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-red-600 duration-300'
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
					{/* Status filter pills */}
					<div className='flex flex-wrap gap-2 mb-6'>
						{STATUS_FILTERS.map(f => (
							<button
								key={f.value}
								onClick={() => setStatusFilter(f.value)}
								className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium duration-300 ${
									statusFilter === f.value
										? 'bg-[#3498db] text-white shadow-md shadow-blue-200'
										: 'bg-white text-gray-600 border border-gray-200 dark:border-slate-600 hover:border-[#3498db] hover:text-[#3498db]'
								}`}
							>
								<span className={`w-2 h-2 rounded-full ${statusFilter === f.value ? 'bg-white' : f.dot}`} />
								{f.text}
							</button>
						))}
					</div>

					{allChannels.length === 0 ? (
						<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300'>
							<div className='text-5xl mb-4'>📋</div>
							<p className='text-lg font-semibold text-gray-700 dark:text-gray-200'>Немає каналів</p>
						</div>
					) : (
						<div className='grid gap-4'>
							{allChannels.map(channel => (
								<div key={channel.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-5 hover:shadow-md duration-300'>
									<div className='flex flex-col md:flex-row md:items-center justify-between gap-3 mb-3'>
										<div className='flex items-center gap-3'>
											{channel.avatar_url ? (
												<img className='w-12 h-12 rounded-full object-cover ring-2 ring-gray-100' src={channel.avatar_url} alt='' />
											) : (
												<div className='w-12 h-12 rounded-full bg-gradient-to-br from-blue-100 to-blue-200 flex items-center justify-center text-lg font-bold text-blue-500'>
													{channel.channel_name?.[0] || '?'}
												</div>
											)}
											<div>
												<h3 className='font-bold text-gray-800 dark:text-white'>{channel.channel_name}</h3>
												<a href={channel.telegram_link} target='_blank' rel='noopener noreferrer' className='text-blue-500 text-sm hover:underline'>
													{channel.telegram_link} <FontAwesomeIcon icon={faExternalLinkAlt} size='xs' />
												</a>
											</div>
										</div>
										<div className='flex items-center gap-2'>
											<span className={`text-xs px-3 py-1 rounded-full font-semibold ${STATUS_COLORS[channel.status] || 'bg-gray-100'}`}>
												{STATUS_LABELS[channel.status] || channel.status}
											</span>
											<button onClick={() => editId === channel.id ? setEditId(null) : startEdit(channel)} className='text-gray-400 hover:text-blue-500 p-2 rounded-lg hover:bg-blue-50 duration-300'>
												<FontAwesomeIcon icon={faPen} />
											</button>
											<button onClick={() => handleDeleteChannel(channel.id)} className='text-gray-400 hover:text-red-500 p-2 rounded-lg hover:bg-red-50 duration-300'>
												<FontAwesomeIcon icon={faTrash} />
											</button>
										</div>
									</div>

									<div className='grid grid-cols-2 md:grid-cols-5 gap-2 text-sm'>
										<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
											<FontAwesomeIcon icon={faUsers} className='text-gray-400 mr-1' />
											<span className='font-semibold'>{channel.subscribers_count?.toLocaleString('uk-UA') || '—'}</span>
											<p className='text-gray-400 text-xs'>підписників</p>
										</div>
										<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
											<FontAwesomeIcon icon={faEye} className='text-gray-400 mr-1' />
											<span className='font-semibold'>{channel.avg_views?.toLocaleString('uk-UA') || '—'}</span>
											<p className='text-gray-400 text-xs'>переглядів</p>
										</div>
										<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
											<FontAwesomeIcon icon={faBarChart} className='text-gray-400 mr-1' />
											<span className='font-semibold'>{channel.er != null ? `${channel.er.toFixed(1)}%` : '—'}</span>
											<p className='text-gray-400 text-xs'>ER</p>
										</div>
										<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
											<span className='font-semibold text-green-600'>{channel.price?.toLocaleString('uk-UA')} USDT</span>
											<p className='text-gray-400 text-xs'>ціна</p>
										</div>
										<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
											<FontAwesomeIcon icon={faList} className='text-gray-400 mr-1' />
											<span className='font-semibold'>{channel.category || '—'}</span>
											<p className='text-gray-400 text-xs'>категорія</p>
										</div>
									</div>

									{channel.seller_telegram && (
										<p className='mt-3 text-sm bg-purple-50 p-2.5 rounded-xl'>
											<span className='font-semibold'>Telegram продавця:</span>{' '}
											<a href={`https://t.me/${channel.seller_telegram.replace('@', '')}`} target='_blank' rel='noopener noreferrer' className='text-blue-500 hover:underline'>
												{channel.seller_telegram}
											</a>
										</p>
									)}

									{channel.description && (
										<p className='mt-2 text-gray-600 text-sm bg-blue-50 p-2.5 rounded-xl'>{channel.description}</p>
									)}

									{editId === channel.id && (
										<div className='mt-4 grid md:grid-cols-2 gap-3 bg-gray-50 dark:bg-slate-700/60 p-4 rounded-xl border border-gray-100'>
											<div>
												<label className='text-xs text-gray-500 font-medium'>Категорія</label>
												<input value={editData.category} onChange={e => setEditData({ ...editData, category: e.target.value })} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent' />
											</div>
											<div>
												<label className='text-xs text-gray-500 font-medium'>Ціна (USDT)</label>
												<input value={editData.price} onChange={e => setEditData({ ...editData, price: e.target.value })} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent' />
											</div>
											<div>
												<label className='text-xs text-gray-500 font-medium'>Дохід/міс (USDT)</label>
												<input value={editData.monthly_income} onChange={e => setEditData({ ...editData, monthly_income: e.target.value })} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent' />
											</div>
											<div>
												<label className='text-xs text-gray-500 font-medium'>Опис</label>
												<input value={editData.description} onChange={e => setEditData({ ...editData, description: e.target.value })} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent' />
											</div>
											<button onClick={() => handleSaveEdit(channel.id)} className='bg-[#27ae60] text-white px-5 py-2 rounded-xl text-sm font-semibold hover:bg-[#219a52] duration-300 flex items-center gap-2 w-fit shadow-sm'>
												<FontAwesomeIcon icon={faSave} /> Зберегти
											</button>
										</div>
									)}
								</div>
							))}
						</div>
					)}
				</>
			) : activeTab.value === 'all_deals' ? (
				<>
					{/* Deal status filter pills */}
					<div className='flex flex-wrap gap-2 mb-6'>
						{DEAL_STATUS_FILTERS.map(f => (
							<button
								key={f.text}
								onClick={() => setDealStatusFilter(f.value)}
								className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium duration-300 ${
									dealStatusFilter === f.value
										? 'bg-[#3498db] text-white shadow-md shadow-blue-200'
										: 'bg-white text-gray-600 border border-gray-200 dark:border-slate-600 hover:border-[#3498db] hover:text-[#3498db]'
								}`}
							>
								<span className={`w-2 h-2 rounded-full ${dealStatusFilter === f.value ? 'bg-white' : f.dot}`} />
								{f.text}
							</button>
						))}
					</div>

					{allDeals.length === 0 ? (
						<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300'>
							<div className='text-5xl mb-4'>🤝</div>
							<p className='text-lg font-semibold text-gray-700 dark:text-gray-200'>Немає угод</p>
						</div>
					) : (
						<div className='grid gap-4'>
							{allDeals.map(deal => {
								const statusInfo = DEAL_STATUS_LABELS[deal.status] || DEAL_STATUS_LABELS.created;
								const isTerminal = ['completed', 'cancelled'].includes(deal.status);
								return (
									<div key={deal.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-5 hover:shadow-md duration-300'>
										<div className='flex flex-col md:flex-row md:items-center justify-between gap-3 mb-3'>
											<div>
												<h3 className='font-bold text-gray-800 text-lg'>
													<FontAwesomeIcon icon={faHandshake} className='mr-2 text-blue-400' />
													Угода #{deal.id} — {deal.channel_name || `Канал #${deal.channel_id}`}
												</h3>
												<p className='text-gray-500 text-sm mt-1'>
													Покупець: <strong>{deal.buyer_name || '—'}</strong> · Продавець: <strong>{deal.seller_name || '—'}</strong>
												</p>
											</div>
											<span className={`text-xs px-3 py-1 rounded-full font-semibold whitespace-nowrap ${statusInfo.color}`}>
												{statusInfo.text}
											</span>
										</div>

										<div className='grid grid-cols-2 md:grid-cols-4 gap-2 text-sm mb-3'>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
												<span className='font-semibold text-green-600'>{deal.amount_usdt} USDT</span>
												<p className='text-gray-400 text-xs'>сума</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
												<span className='font-semibold'>{deal.service_fee} USDT</span>
												<p className='text-gray-400 text-xs'>комісія</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
												<span className='font-semibold'>{new Date(deal.created_at).toLocaleDateString('uk-UA')}</span>
												<p className='text-gray-400 text-xs'>створено</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
												<span className='font-semibold'>
													{deal.completed_at ? new Date(deal.completed_at).toLocaleDateString('uk-UA') : '—'}
												</span>
												<p className='text-gray-400 text-xs'>завершено</p>
											</div>
										</div>

										{deal.dispute_reason && (
											<p className='text-sm bg-red-50 text-red-700 p-3 rounded-xl mb-3'>
												<span className='font-semibold'>Причина спору:</span> {deal.dispute_reason}
											</p>
										)}

										<div className='flex flex-wrap gap-2'>
											<button
												onClick={() => setChatDealId(deal.id)}
												className='bg-[#3498db] text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-[#2980b9] duration-300 flex items-center gap-2'
											>
												<FontAwesomeIcon icon={faComments} /> Чат
											</button>
											<a
												href={`/deal/${deal.id}`}
												target='_blank'
												rel='noopener noreferrer'
												className='bg-gray-100 text-gray-700 px-4 py-2 rounded-xl text-sm font-semibold hover:bg-gray-200 duration-300 flex items-center gap-2'
											>
												<FontAwesomeIcon icon={faArrowRight} /> Відкрити угоду
											</a>
											{deal.status === 'disputed' && (
												<>
													<button
														onClick={() => handleResolve(deal.id, 'refund_buyer')}
														className='bg-orange-500 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-orange-600 duration-300'
													>
														Повернути покупцю
													</button>
													<button
														onClick={() => handleResolve(deal.id, 'release_seller')}
														className='bg-[#27ae60] text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-[#219a52] duration-300'
													>
														Перевести продавцю
													</button>
												</>
											)}
											{!isTerminal && (
												<button
													onClick={() => handleCancelDeal(deal.id)}
													className='bg-red-500 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-red-600 duration-300 flex items-center gap-2'
												>
													<FontAwesomeIcon icon={faBan} /> Скасувати
												</button>
											)}
										</div>
									</div>
								);
							})}
						</div>
					)}
				</>
			) : disputes.length === 0 ? (
				<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300'>
					<div className='text-5xl mb-4'>⚖️</div>
					<p className='text-lg font-semibold text-gray-700 mb-2'>Все спокійно</p>
					<p className='text-gray-500'>Немає спірних угод</p>
				</div>
			) : (
				<div className='grid gap-6'>
					{disputes.map(deal => (
						<div key={deal.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-6 hover:shadow-md duration-300'>
							<div className='flex items-center justify-between mb-4'>
								<h3 className='font-bold text-lg text-gray-800 dark:text-white'>
									<FontAwesomeIcon icon={faGavel} className='mr-2 text-yellow-500' />
									Угода #{deal.id}
								</h3>
								<span className='text-xs font-semibold text-yellow-700 bg-yellow-100 px-3 py-1 rounded-full'>
									Спір
								</span>
							</div>
							<p className='text-gray-600 mb-2'>
								<span className='font-semibold'>Канал:</span> {deal.channel_name || `#${deal.channel_id}`} · <span className='font-semibold'>Сума:</span> {deal.amount_usdt} USDT
							</p>
							<p className='text-gray-600 mb-2'>
								<span className='font-semibold'>Покупець:</span> {deal.buyer_name || '—'} · <span className='font-semibold'>Продавець:</span> {deal.seller_name || '—'}
							</p>
							{deal.dispute_reason && (
								<p className='text-gray-600 mb-4 bg-red-50 p-3 rounded-xl'>
									<span className='font-semibold'>Причина:</span> {deal.dispute_reason}
								</p>
							)}
							<div className='flex flex-wrap gap-3'>
								<button
									onClick={() => setChatDealId(deal.id)}
									className='bg-[#3498db] text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-[#2980b9] duration-300 shadow-sm flex items-center gap-2'
								>
									<FontAwesomeIcon icon={faComments} /> Чат
								</button>
								<button
									onClick={() => handleResolve(deal.id, 'refund_buyer')}
									className='bg-orange-500 text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-orange-600 duration-300 shadow-sm'
								>
									Повернути покупцю
								</button>
								<button
									onClick={() => handleResolve(deal.id, 'release_seller')}
									className='bg-[#27ae60] text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-[#219a52] duration-300 shadow-sm'
								>
									Перевести продавцю
								</button>
								<button
									onClick={() => handleCancelDeal(deal.id)}
									className='bg-red-500 text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-red-600 duration-300 shadow-sm flex items-center gap-2'
								>
									<FontAwesomeIcon icon={faBan} /> Скасувати
								</button>
							</div>
						</div>
					))}
				</div>
			)}

			{/* ═══ Escrow Wallets Tab ═══ */}
			{activeTab.value === 'escrow' && (
				<div>
					{/* Summary */}
					<div className='bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-2xl p-6 mb-6'>
						<div className='flex items-center justify-between flex-wrap gap-4'>
							<div>
								<p className='text-gray-500 text-sm font-medium'>Загальний баланс на ескроу</p>
								<p className='text-3xl font-bold text-gray-800 mt-1'>{escrowTotal.toFixed(2)} <span className='text-lg text-gray-500'>USDT</span></p>
							</div>
							<div className='flex items-center gap-3'>
								<span className='text-sm text-gray-500'>{escrowWallets.length} гаманців з коштами</span>
								<button
									onClick={loadData}
									className='bg-white border border-gray-200 dark:border-slate-600 text-gray-600 px-4 py-2.5 rounded-xl font-semibold hover:bg-gray-50 dark:bg-slate-700/60 duration-300 shadow-sm flex items-center gap-2'
								>
									<FontAwesomeIcon icon={faSync} /> Оновити
								</button>
							</div>
						</div>
					</div>

					{loading ? (
						<p className='text-center text-gray-400 py-8'>Завантаження балансів...</p>
					) : escrowWallets.length === 0 ? (
						<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100'>
							<FontAwesomeIcon icon={faWallet} className='text-gray-300 text-5xl mb-4' />
							<p className='text-gray-400 text-lg'>Усі ескроу гаманці порожні</p>
						</div>
					) : (
						<div className='space-y-4'>
							{escrowWallets.map(w => (
								<div key={w.deal_id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-6 hover:border-blue-200 duration-300'>
									<div className='flex flex-col lg:flex-row lg:items-start gap-4'>
										{/* Info */}
										<div className='flex-1 min-w-0'>
											<div className='flex items-center gap-3 mb-3'>
												<span className='text-lg font-bold text-gray-800 dark:text-white'>Угода #{w.deal_id}</span>
												<span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
													DEAL_STATUS_LABELS[w.status]?.color || 'bg-gray-100 text-gray-600 dark:text-gray-300'
												}`}>
													{DEAL_STATUS_LABELS[w.status]?.text || w.status}
												</span>
											</div>
											<div className='flex items-center gap-2 mb-2'>
												<span className='text-sm text-gray-500'>Ескроу:</span>
												<code className='text-sm bg-gray-50 dark:bg-slate-700/60 px-2 py-1 rounded font-mono text-gray-700 break-all'>{w.escrow}</code>
												<button
													onClick={() => copyToClipboard(w.escrow)}
													className='text-gray-400 hover:text-blue-500 duration-200'
													title='Копіювати'
												>
													<FontAwesomeIcon icon={faCopy} className='text-xs' />
												</button>
											</div>
											<p className='text-2xl font-bold text-green-600'>{w.balance_usdt.toFixed(2)} <span className='text-sm text-gray-400'>USDT</span></p>
										</div>

										{/* Sweep controls */}
										<div className='lg:w-96 flex-shrink-0'>
											<label className='text-sm text-gray-500 font-medium mb-1.5 block'>Перевести на адресу (TRC-20)</label>
											<div className='flex gap-2'>
												<input
													type='text'
													value={sweepTarget[w.deal_id] || ''}
													onChange={e => setSweepTarget(prev => ({ ...prev, [w.deal_id]: e.target.value }))}
													placeholder='TRC-20 адреса...'
													className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent'
												/>
												<button
													onClick={() => handleSweep(w.deal_id)}
													disabled={sweeping[w.deal_id]}
													className='bg-[#3498db] text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-[#2980b9] duration-300 shadow-sm flex items-center gap-2 disabled:opacity-50 whitespace-nowrap'
												>
													<FontAwesomeIcon icon={faPaperPlane} />
													{sweeping[w.deal_id] ? 'Переводимо...' : 'Перевести'}
												</button>
											</div>
											<p className='text-xs text-gray-400 mt-1.5'>Потрібен TRX на мастер-гаманці для оплати газу</p>
										</div>
									</div>
								</div>
							))}
						</div>
					)}
				</div>
			)}

			{/* Deal Chat Modal */}
			{chatDealId && (
				<DealChatModal
					dealId={chatDealId}
					userId={user?.id}
					onClose={() => setChatDealId(null)}
				/>
			)}
		</section>
	);
};

export default ModerCabinet;
