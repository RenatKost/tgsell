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
	faHandshake,
	faComments,
	faBan,
	faArrowRight,
	faWallet,
	faSync,
	faPaperPlane,
	faCopy,
	faTachometerAlt,
	faChartLine,
	faClock,
	faBars,
	faChevronLeft,
	faToggleOn,
	faToggleOff,
} from '@fortawesome/free-solid-svg-icons';

const SECTIONS = [
	{ id: 'dashboard', label: 'Дашборд', icon: faTachometerAlt },
	{ id: 'pending', label: 'На модерації', icon: faClipboardCheck },
	{ id: 'channels', label: 'Канали', icon: faLayerGroup },
	{ id: 'deals', label: 'Угоди', icon: faHandshake },
	{ id: 'disputes', label: 'Спори', icon: faScaleBalanced },
	{ id: 'auctions', label: 'Аукціони', icon: faGavel },
	{ id: 'activity', label: 'Активність', icon: faChartLine },
	{ id: 'escrow', label: 'Ескроу', icon: faWallet },
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

const AUCTION_STATUS_FILTERS = [
	{ text: 'Всі', value: '', dot: 'bg-gray-400' },
	{ text: 'Активні', value: 'active', dot: 'bg-green-500' },
	{ text: 'Заплановані', value: 'scheduled', dot: 'bg-yellow-500' },
	{ text: 'Завершені', value: 'ended', dot: 'bg-blue-500' },
	{ text: 'Скасовані', value: 'cancelled', dot: 'bg-red-500' },
];

const DEAL_STATUS_LABELS = {
	created: { text: 'Очікує оплати', color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },
	payment_pending: { text: 'Очікує оплати', color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },
	paid: { text: 'Оплачено', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
	channel_transferring: { text: 'Передача каналу', color: 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' },
	completed: { text: 'Завершено', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
	disputed: { text: 'Спір', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
	cancelled: { text: 'Скасовано', color: 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300' },
};

const STATUS_LABELS = {
	pending: 'На модерації',
	approved: 'Опубліковано',
	rejected: 'Відхилено',
	sold: 'Продано',
};

const STATUS_COLORS = {
	pending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
	approved: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
	rejected: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
	sold: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
};

const AUCTION_STATUS_LABELS = {
	active: { text: 'Активний', color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
	scheduled: { text: 'Запланований', color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' },
	ended: { text: 'Завершений', color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' },
	cancelled: { text: 'Скасований', color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
};

const FilterPills = ({ items, active, onChange }) => (
	<div className='flex flex-wrap gap-2 mb-6'>
		{items.map(f => (
			<button
				key={f.value}
				onClick={() => onChange(f.value)}
				className={`flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium duration-300 ${
					active === f.value
						? 'bg-[#3498db] text-white shadow-md shadow-blue-200 dark:shadow-blue-900/30'
						: 'bg-white dark:bg-slate-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-slate-600 hover:border-[#3498db] hover:text-[#3498db]'
				}`}
			>
				<span className={`w-2 h-2 rounded-full ${active === f.value ? 'bg-white' : f.dot}`} />
				{f.text}
			</button>
		))}
	</div>
);

const StatCard = ({ label, value, icon, color = 'text-gray-600 dark:text-gray-300', onClick }) => (
	<div
		onClick={onClick}
		className={`bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-5 shadow-sm hover:shadow-md duration-300 ${onClick ? 'cursor-pointer hover:border-[#3498db]' : ''}`}
	>
		<div className='flex items-center justify-between mb-3'>
			<span className='text-gray-400 dark:text-gray-500 text-sm font-medium'>{label}</span>
			<FontAwesomeIcon icon={icon} className='text-gray-300 dark:text-gray-600' />
		</div>
		<p className={`text-3xl font-bold ${color}`}>{value}</p>
	</div>
);

const EmptyState = ({ icon, title, subtitle }) => (
	<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300 dark:border-slate-600'>
		<div className='text-5xl mb-4'>{icon}</div>
		<p className='text-lg font-semibold text-gray-700 dark:text-gray-200 mb-2'>{title}</p>
		{subtitle && <p className='text-gray-500 dark:text-gray-400'>{subtitle}</p>}
	</div>
);

const Loader = () => (
	<div className='flex justify-center py-20'>
		<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
	</div>
);

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
			<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col' onClick={e => e.stopPropagation()}>
				<div className='bg-gradient-to-r from-[#3498db] to-[#2980b9] text-white p-5 rounded-t-2xl flex items-center justify-between'>
					<h3 className='font-bold text-lg'>Чат угоди #{dealId}</h3>
					<button onClick={onClose} className='text-white/80 hover:text-white text-xl font-bold'>X</button>
				</div>
				<div className='flex-1 overflow-y-auto p-4 bg-gray-50 dark:bg-slate-700/60 min-h-[300px]'>
					{messages.length === 0 && (
						<p className='text-gray-400 text-center mt-20 text-sm'>Повідомлень ще немає</p>
					)}
					{messages.map(msg => {
						if (msg.is_system) {
							return (
								<div key={msg.id} className='mb-3 flex justify-center'>
									<div className='bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 text-xs px-4 py-2 rounded-full font-medium'>
										{msg.text}
									</div>
								</div>
							);
						}
						const isOwn = msg.sender_id === userId;
						return (
							<div key={msg.id} className={`mb-3 flex ${isOwn ? 'justify-end' : 'justify-start'}`}>
								<div className={`max-w-[75%] px-4 py-2 rounded-lg ${isOwn ? 'bg-[#3498db] text-white rounded-br-none' : 'bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 rounded-bl-none shadow-sm'}`}>
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
				<form onSubmit={handleSend} className='p-4 border-t border-gray-200 dark:border-slate-600 flex gap-2'>
					<input
						type='text'
						value={newMessage}
						onChange={e => setNewMessage(e.target.value)}
						placeholder='Написати як адмін...'
						maxLength={2000}
						className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2.5 bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent'
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
	const [section, setSection] = useState('dashboard');
	const [sidebarOpen, setSidebarOpen] = useState(true);
	const [loading, setLoading] = useState(true);

	const [dashStats, setDashStats] = useState(null);

	// ── Telethon re-auth state ──
	const [reauthStatus, setReauthStatus] = useState(null);
	const [reauthStep, setReauthStep] = useState('idle'); // idle | sent | confirm | done | error
	const [reauthCode, setReauthCode] = useState('');
	const [reauthPassword, setReauthPassword] = useState('');
	const [reauthMsg, setReauthMsg] = useState('');
	const [reauthLoading, setReauthLoading] = useState(false);

	const [pendingChannels, setPendingChannels] = useState([]);
	const [allChannels, setAllChannels] = useState([]);
	const [statusFilter, setStatusFilter] = useState('');
	const [rejectId, setRejectId] = useState(null);
	const [rejectReason, setRejectReason] = useState('');
	const [editId, setEditId] = useState(null);
	const [editData, setEditData] = useState({});
	const [refreshingStats, setRefreshingStats] = useState({});
	const [refreshResult, setRefreshResult] = useState({});

	const [allDeals, setAllDeals] = useState([]);
	const [dealStatusFilter, setDealStatusFilter] = useState('');
	const [disputes, setDisputes] = useState([]);
	const [chatDealId, setChatDealId] = useState(null);

	const [auctions, setAuctions] = useState([]);
	const [auctionFilter, setAuctionFilter] = useState('');
	const [extendId, setExtendId] = useState(null);
	const [extendHours, setExtendHours] = useState(24);

	const [escrowWallets, setEscrowWallets] = useState([]);
	const [escrowTotal, setEscrowTotal] = useState(0);
	const [sweepTarget, setSweepTarget] = useState({});
	const [sweeping, setSweeping] = useState({});

	const [actConfig, setActConfig] = useState(null);
	const [actConfigDirty, setActConfigDirty] = useState(false);
	const [diagnostics, setDiagnostics] = useState(null);
	const [diagLoading, setDiagLoading] = useState(false);

	useEffect(() => {
		loadData();
	}, [section, statusFilter, dealStatusFilter, auctionFilter]);

	const loadData = async () => {
		setLoading(true);
		try {
			if (section === 'dashboard') {
				const { data } = await adminAPI.getDashboardStats();
				setDashStats(data);
				try {
					const { data: rs } = await adminAPI.getReauthStatus();
					setReauthStatus(rs);
				} catch (_) {}
			} else if (section === 'pending') {
				const { data } = await adminAPI.getPendingChannels();
				setPendingChannels(Array.isArray(data) ? data : data.items || []);
			} else if (section === 'channels') {
				const params = statusFilter ? { status: statusFilter } : {};
				const { data } = await adminAPI.getAllChannels(params);
				setAllChannels(Array.isArray(data) ? data : data.items || []);
			} else if (section === 'deals') {
				const params = {};
				if (dealStatusFilter === 'active') {
					// filter client-side
				} else if (dealStatusFilter) {
					params.deal_status = dealStatusFilter;
				}
				const { data } = await adminAPI.getAllDeals(params);
				let items = Array.isArray(data) ? data : data.items || [];
				if (dealStatusFilter === 'active') {
					items = items.filter(d => ['created', 'payment_pending', 'paid', 'channel_transferring'].includes(d.status));
				}
				setAllDeals(items);
			} else if (section === 'disputes') {
				const { data } = await adminAPI.getAllDeals({ deal_status: 'disputed' });
				setDisputes(Array.isArray(data) ? data : data.items || []);
			} else if (section === 'auctions') {
				const params = auctionFilter ? { status: auctionFilter } : {};
				const { data } = await adminAPI.getAuctions(params);
				setAuctions(data.items || []);
			} else if (section === 'activity') {
				const { data } = await adminAPI.getActivityConfig();
				setActConfig(data);
				setActConfigDirty(false);
			} else if (section === 'escrow') {
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
		} catch (err) { alert(err.response?.data?.detail || 'Помилка'); }
	};

	const handleReject = async (id) => {
		if (!rejectReason.trim()) { alert('Вкажіть причину відхилення'); return; }
		try {
			await adminAPI.rejectChannel(id, rejectReason);
			setPendingChannels(prev => prev.filter(c => c.id !== id));
			setRejectId(null);
			setRejectReason('');
		} catch (err) { alert(err.response?.data?.detail || 'Помилка'); }
	};

	const handleDeleteChannel = async (id) => {
		if (!confirm('Видалити канал?')) return;
		try {
			await adminAPI.deleteChannel(id);
			setAllChannels(prev => prev.filter(c => c.id !== id));
		} catch (err) { alert(err.response?.data?.detail || 'Помилка видалення'); }
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
		} catch (err) { alert(err.response?.data?.detail || 'Помилка збереження'); }
	};

	const handleRefreshStats = async (channelId) => {
		setRefreshingStats(prev => ({ ...prev, [channelId]: true }));
		setRefreshResult(prev => ({ ...prev, [channelId]: null }));
		try {
			const { data } = await adminAPI.refreshChannelStats(channelId);
			setRefreshResult(prev => ({ ...prev, [channelId]: data }));
			if (data.subscribers_count || data.avg_views) {
				setAllChannels(prev => prev.map(c => c.id === channelId ? {
					...c,
					subscribers_count: data.subscribers_count || c.subscribers_count,
					avg_views: data.avg_views || c.avg_views,
					er: data.er || c.er,
				} : c));
			}
		} catch (err) {
			const msg = err.response?.data?.detail || err.response?.data?.message || (err.response ? `HTTP ${err.response.status}` : err.message) || 'Невідома помилка';
			setRefreshResult(prev => ({ ...prev, [channelId]: { ok: false, error: msg } }));
		} finally {
			setRefreshingStats(prev => ({ ...prev, [channelId]: false }));
		}
	};

	const handleResolve = async (dealId, resolution) => {
		try {
			await adminAPI.resolveDeal(dealId, { resolution });
			setDisputes(prev => prev.filter(d => d.id !== dealId));
			setAllDeals(prev => prev.filter(d => d.id !== dealId));
		} catch (err) { alert(err.response?.data?.detail || 'Помилка'); }
	};

	const handleCancelDeal = async (dealId) => {
		if (!confirm('Скасувати цю угоду?')) return;
		try {
			await adminAPI.cancelDeal(dealId);
			setAllDeals(prev => prev.map(d => d.id === dealId ? { ...d, status: 'cancelled' } : d));
			setDisputes(prev => prev.filter(d => d.id !== dealId));
		} catch (err) { alert(err.response?.data?.detail || 'Помилка скасування'); }
	};

	const handleCancelAuction = async (id) => {
		if (!confirm('Скасувати аукціон?')) return;
		try {
			await adminAPI.cancelAuction(id);
			setAuctions(prev => prev.map(a => a.id === id ? { ...a, status: 'cancelled' } : a));
		} catch (err) { alert(err.response?.data?.detail || 'Помилка'); }
	};

	const handleExtendAuction = async (id) => {
		try {
			await adminAPI.extendAuction(id, extendHours);
			setExtendId(null);
			loadData();
		} catch (err) { alert(err.response?.data?.detail || 'Помилка'); }
	};

	const handleDeleteAuction = async (id) => {
		if (!confirm('Видалити аукціон і всі ставки?')) return;
		try {
			await adminAPI.deleteAuction(id);
			setAuctions(prev => prev.filter(a => a.id !== id));
		} catch (err) { alert(err.response?.data?.detail || 'Помилка'); }
	};

	const handleSweep = async (dealId) => {
		const toAddr = sweepTarget[dealId];
		if (!toAddr || !toAddr.trim() || !toAddr.startsWith('T') || toAddr.length < 30) {
			alert('Введіть коректну TRC-20 адресу (починається з T)');
			return;
		}
		if (!confirm('Перевести USDT з ескроу угоди #' + dealId + ' на ' + toAddr + '?')) return;
		setSweeping(prev => ({ ...prev, [dealId]: true }));
		try {
			const { data } = await adminAPI.sweepEscrow(dealId, toAddr.trim());
			if (data.ok) {
				alert('Переведено ' + data.amount_usdt + ' USDT!\nTx: ' + data.usdt_tx);
				loadData();
			} else { alert('Помилка: ' + data.error); }
		} catch (err) { alert(err.response?.data?.detail || 'Помилка переводу'); }
		finally { setSweeping(prev => ({ ...prev, [dealId]: false })); }
	};

	const handleActConfigChange = (key, value) => {
		setActConfig(prev => ({ ...prev, [key]: value }));
		setActConfigDirty(true);
	};

	const handleSaveActConfig = async () => {
		try {
			const { data } = await adminAPI.updateActivityConfig(actConfig);
			setActConfig(data);
			setActConfigDirty(false);
		} catch (err) { alert('Помилка збереження'); }
	};

	const handleDiagnostics = async () => {
		setDiagLoading(true);
		try {
			const { data } = await adminAPI.getTelegramDiagnostics();
			setDiagnostics(data);
		} catch (err) {
			setDiagnostics({ error: err.response?.data?.detail || 'Помилка діагностики' });
		} finally { setDiagLoading(false); }
	};

	const copyToClipboard = (text) => navigator.clipboard.writeText(text);

	const fmtDate = (iso) => iso ? new Date(iso).toLocaleString('uk-UA', {
		day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit',
	}) : '—';

	const timeLeft = (iso) => {
		if (!iso) return '—';
		const diff = new Date(iso) - Date.now();
		if (diff <= 0) return 'Завершено';
		const h = Math.floor(diff / 3600000);
		const m = Math.floor((diff % 3600000) / 60000);
		return h + 'г ' + m + 'хв';
	};

	return (
		<section className='pt-20 pb-10 flex min-h-screen'>
			<aside className={`fixed top-20 left-0 bottom-0 z-40 bg-white dark:bg-slate-900 border-r border-gray-200 dark:border-slate-700 transition-all duration-300 ${sidebarOpen ? 'w-64' : 'w-16'} flex flex-col`}>
				<div className='p-3 flex items-center justify-between border-b border-gray-100 dark:border-slate-700'>
					{sidebarOpen && <span className='text-sm font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider'>Адмін</span>}
					<button onClick={() => setSidebarOpen(!sidebarOpen)} className='p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800 text-gray-400 duration-200'>
						<FontAwesomeIcon icon={sidebarOpen ? faChevronLeft : faBars} />
					</button>
				</div>
				<nav className='flex-1 py-2 overflow-y-auto'>
					{SECTIONS.map(s => (
						<button
							key={s.id}
							onClick={() => setSection(s.id)}
							className={`w-full flex items-center gap-3 px-4 py-3 text-sm font-medium duration-200 ${
								section === s.id
									? 'bg-blue-50 dark:bg-blue-900/20 text-[#3498db] border-r-2 border-[#3498db]'
									: 'text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-slate-800 hover:text-gray-800 dark:hover:text-gray-200'
							}`}
							title={s.label}
						>
							<FontAwesomeIcon icon={s.icon} className='w-5 text-center' />
							{sidebarOpen && <span>{s.label}</span>}
							{sidebarOpen && s.id === 'pending' && pendingChannels.length > 0 && (
								<span className='ml-auto bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 text-xs px-2 py-0.5 rounded-full'>
									{pendingChannels.length}
								</span>
							)}
							{sidebarOpen && s.id === 'disputes' && disputes.length > 0 && (
								<span className='ml-auto bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 text-xs px-2 py-0.5 rounded-full'>
									{disputes.length}
								</span>
							)}
						</button>
					))}
				</nav>
			</aside>

			<main className={`flex-1 transition-all duration-300 ${sidebarOpen ? 'ml-64' : 'ml-16'} px-6 lg:px-10`}>

				{section === 'dashboard' && (
					<div>
						<h1 className='text-2xl font-bold text-gray-800 dark:text-white mb-6'>Дашборд</h1>
						{loading || !dashStats ? <Loader /> : (
							<>
								<div className='grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8'>
									<StatCard label='Всього каналів' value={dashStats.total_channels} icon={faLayerGroup} onClick={() => setSection('channels')} />
									<StatCard label='На модерації' value={dashStats.pending_channels} icon={faClipboardCheck} color='text-yellow-600' onClick={() => setSection('pending')} />
									<StatCard label='Активні угоди' value={dashStats.active_deals} icon={faHandshake} color='text-blue-600' onClick={() => setSection('deals')} />
									<StatCard label='Спори' value={dashStats.disputed_deals} icon={faScaleBalanced} color='text-red-600' onClick={() => setSection('disputes')} />
								</div>
								<div className='grid grid-cols-2 lg:grid-cols-4 gap-4'>
									<StatCard label='Аукціони' value={dashStats.active_auctions} icon={faGavel} color='text-orange-600' onClick={() => setSection('auctions')} />
									<StatCard label='Користувачі' value={dashStats.total_users} icon={faUsers} />
									<StatCard label='Угод за тиждень' value={dashStats.deals_this_week} icon={faChartLine} />
									<StatCard label='Дохід (USDT)' value={dashStats.total_revenue} icon={faWallet} color='text-green-600' />
								</div>

								{/* ── Telethon re-auth panel ── */}
								<div className='mt-8 bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-6'>
									<div className='flex items-center justify-between mb-4'>
										<div>
											<h2 className='font-bold text-gray-800 dark:text-white text-lg'>Telethon сесія</h2>
											<p className='text-sm text-gray-500 dark:text-gray-400 mt-0.5'>
												{reauthStatus
													? reauthStatus.live_client_ok
														? '✅ Підключено і авторизовано'
														: reauthStatus.db_session_exists
															? '⚠️ Сесія є в БД, але клієнт не підключений'
															: '❌ Сесія відсутня — потрібна авторизація'
													: 'Статус невідомий'}
											</p>
										</div>
										{reauthStep === 'idle' && (
											<button
												onClick={async () => {
													setReauthLoading(true); setReauthMsg('');
													try {
														await adminAPI.reauthStart();
														setReauthStep('confirm');
														setReauthMsg('Код відправлено на телефон. Введіть його нижче.');
													} catch (e) {
														setReauthMsg('Помилка: ' + (e.response?.data?.detail || e.message));
													} finally { setReauthLoading(false); }
												}}
												disabled={reauthLoading}
												className='bg-blue-600 text-white px-4 py-2 rounded-xl font-semibold hover:bg-blue-700 duration-200 disabled:opacity-50 flex items-center gap-2 text-sm'
											>
												<FontAwesomeIcon icon={faSync} className={reauthLoading ? 'animate-spin' : ''} />
												Запросити код
											</button>
										)}
									</div>

									{reauthMsg && (
										<p className={`text-sm mb-4 ${reauthMsg.startsWith('Помилка') ? 'text-red-500' : 'text-green-600 dark:text-green-400'}`}>{reauthMsg}</p>
									)}

									{reauthStep === 'confirm' && (
										<div className='flex flex-col gap-3'>
											<div className='flex gap-3'>
												<input
													value={reauthCode}
													onChange={e => setReauthCode(e.target.value)}
													placeholder='Код з SMS / Telegram'
													className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2 text-sm bg-white dark:bg-slate-700 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500'
												/>
												<button
													onClick={async () => {
														setReauthLoading(true); setReauthMsg('');
														try {
															const { data } = await adminAPI.reauthConfirm(reauthCode, reauthPassword);
															if (data.need_2fa) {
																setReauthStep('2fa');
																setReauthMsg('Введіть 2FA пароль.');
															} else {
																setReauthStep('done');
																setReauthMsg('✅ Сесія оновлена!');
																const { data: rs } = await adminAPI.getReauthStatus();
																setReauthStatus(rs);
															}
														} catch (e) {
															setReauthMsg('Помилка: ' + (e.response?.data?.detail || e.message));
														} finally { setReauthLoading(false); }
													}}
													disabled={reauthLoading || !reauthCode}
													className='bg-green-600 text-white px-5 py-2 rounded-xl font-semibold hover:bg-green-700 duration-200 disabled:opacity-50 text-sm'
												>
													{reauthLoading ? '...' : 'Підтвердити'}
												</button>
											</div>
										</div>
									)}

									{reauthStep === '2fa' && (
										<div className='flex gap-3'>
											<input
												type='password'
												value={reauthPassword}
												onChange={e => setReauthPassword(e.target.value)}
												placeholder='2FA пароль'
												className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2 text-sm bg-white dark:bg-slate-700 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500'
											/>
											<button
												onClick={async () => {
													setReauthLoading(true); setReauthMsg('');
													try {
														const { data } = await adminAPI.reauthConfirm(reauthCode, reauthPassword);
														setReauthStep('done');
														setReauthMsg('✅ Сесія оновлена!');
														const { data: rs } = await adminAPI.getReauthStatus();
														setReauthStatus(rs);
													} catch (e) {
														setReauthMsg('Помилка: ' + (e.response?.data?.detail || e.message));
													} finally { setReauthLoading(false); }
												}}
												disabled={reauthLoading || !reauthPassword}
												className='bg-green-600 text-white px-5 py-2 rounded-xl font-semibold hover:bg-green-700 duration-200 disabled:opacity-50 text-sm'
											>
												{reauthLoading ? '...' : 'Підтвердити'}
											</button>
										</div>
									)}

									{(reauthStep === 'done' || reauthStep === 'idle') && reauthStatus && !reauthStatus.live_client_ok && reauthStep !== 'done' && (
										<p className='text-xs text-gray-400 dark:text-gray-500 mt-2'>
											Клієнт підключиться автоматично при наступному циклі збору статистики (кожні 3 год).
										</p>
									)}
								</div>
							</>
						)}
					</div>
				)}

				{section === 'pending' && (
					<div>
						<div className='flex items-center justify-between mb-6'>
							<h1 className='text-2xl font-bold text-gray-800 dark:text-white'>На модерації</h1>
							{pendingChannels.length > 0 && (
								<span className='inline-flex items-center gap-2 bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-400 font-semibold py-2 px-4 rounded-xl border border-yellow-200 dark:border-yellow-800 text-sm'>
									<span className='w-2 h-2 rounded-full bg-yellow-500 animate-pulse' />
									{pendingChannels.length} очікують
								</span>
							)}
						</div>
						{loading ? <Loader /> : pendingChannels.length === 0 ? (
							<EmptyState icon='✅' title='Все перевірено!' subtitle='Немає каналів, що очікують модерації' />
						) : (
							<div className='grid gap-5'>
								{pendingChannels.map(channel => (
									<div key={channel.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-6 hover:shadow-md duration-300'>
										<div className='flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4'>
											<div className='flex items-center gap-4'>
												{channel.avatar_url ? (
													<img className='w-14 h-14 rounded-full object-cover ring-2 ring-gray-100 dark:ring-slate-600' src={channel.avatar_url} alt='' />
												) : (
													<div className='w-14 h-14 rounded-full bg-gradient-to-br from-blue-100 to-blue-200 dark:from-blue-900 dark:to-blue-800 flex items-center justify-center text-xl font-bold text-blue-500'>
														{channel.channel_name?.[0] || '?'}
													</div>
												)}
												<div>
													<h3 className='font-bold text-lg text-gray-800 dark:text-white'>{channel.channel_name}</h3>
													<div className='flex items-center gap-2 mt-1'>
														<a href={channel.telegram_link} target='_blank' rel='noopener noreferrer' className='text-blue-500 text-sm hover:underline'>
															{channel.telegram_link} <FontAwesomeIcon icon={faExternalLinkAlt} size='xs' />
														</a>
														{channel.listing_type === 'auction' && (
															<span className='text-xs px-2 py-0.5 rounded-full bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400 font-medium'>🔥 Аукціон</span>
														)}
														{channel.listing_type === 'both' && (
															<span className='text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 font-medium'>🏷️ Каталог + 🔥 Аукціон</span>
														)}
														{(!channel.listing_type || channel.listing_type === 'sale') && (
															<span className='text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 font-medium'>🏷️ Каталог</span>
														)}
													</div>
												</div>
											</div>
											<div className='flex gap-3'>
												<button onClick={() => handleApprove(channel.id)} className='bg-[#27ae60] text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-[#219a52] duration-300 flex items-center gap-2 shadow-sm'>
													<FontAwesomeIcon icon={faCheck} /> Схвалити
												</button>
												<button onClick={() => setRejectId(rejectId === channel.id ? null : channel.id)} className='bg-red-500 text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-red-600 duration-300 flex items-center gap-2 shadow-sm'>
													<FontAwesomeIcon icon={faTimes} /> Відхилити
												</button>
											</div>
										</div>
										<div className='grid grid-cols-2 md:grid-cols-4 gap-3 text-sm'>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<FontAwesomeIcon icon={faUsers} className='text-gray-400 mr-1' />
												<span className='font-semibold text-gray-800 dark:text-gray-200'>{channel.subscribers_count?.toLocaleString('uk-UA') || '—'}</span>
												<p className='text-gray-400 text-xs mt-0.5'>підписників</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<FontAwesomeIcon icon={faEye} className='text-gray-400 mr-1' />
												<span className='font-semibold text-gray-800 dark:text-gray-200'>{channel.views_hidden ? '🔒' : (channel.avg_views?.toLocaleString('uk-UA') || '—')}</span>
												<p className='text-gray-400 text-xs mt-0.5'>переглядів</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<FontAwesomeIcon icon={faBarChart} className='text-gray-400 mr-1' />
												<span className='font-semibold text-gray-800 dark:text-gray-200'>{channel.er != null ? channel.er.toFixed(1) + '%' : '—'}</span>
												<p className='text-gray-400 text-xs mt-0.5'>ER</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
												<span className='font-semibold text-green-600'>{channel.price?.toLocaleString('uk-UA')} USDT</span>
												<p className='text-gray-400 text-xs mt-0.5'>ціна</p>
											</div>
										</div>
										{(channel.listing_type === 'auction' || channel.listing_type === 'both') && channel.auction_start_price && (
											<div className='grid grid-cols-2 md:grid-cols-3 gap-3 text-sm mt-3'>
												<div className='bg-orange-50 dark:bg-orange-900/20 p-3 rounded-xl'>
													<span className='font-semibold text-orange-600'>{channel.auction_start_price} USDT</span>
													<p className='text-gray-400 text-xs mt-0.5'>старт аукціону</p>
												</div>
												<div className='bg-orange-50 dark:bg-orange-900/20 p-3 rounded-xl'>
													<span className='font-semibold text-orange-600'>{channel.auction_bid_step} USDT</span>
													<p className='text-gray-400 text-xs mt-0.5'>крок ставки</p>
												</div>
												<div className='bg-orange-50 dark:bg-orange-900/20 p-3 rounded-xl'>
													<span className='font-semibold text-orange-600'>{channel.auction_duration_hours}г</span>
													<p className='text-gray-400 text-xs mt-0.5'>тривалість</p>
												</div>
											</div>
										)}
										{channel.description && (
											<p className='mt-4 text-gray-600 dark:text-gray-300 text-sm bg-blue-50 dark:bg-blue-900/20 p-3 rounded-xl'>{channel.description}</p>
										)}
										{rejectId === channel.id && (
											<div className='mt-4 flex gap-2'>
												<input type='text' value={rejectReason} onChange={e => setRejectReason(e.target.value)} placeholder='Причина відхилення...' className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2.5 bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-red-300 focus:border-transparent' />
												<button onClick={() => handleReject(channel.id)} className='bg-red-500 text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-red-600 duration-300'>Підтвердити</button>
											</div>
										)}
									</div>
								))}
							</div>
						)}
					</div>
				)}

				{section === 'channels' && (
					<div>
						<div className='flex items-center justify-between mb-6'>
							<h1 className='text-2xl font-bold text-gray-800 dark:text-white'>Всі канали</h1>
							<button
								onClick={handleDiagnostics}
								disabled={diagLoading}
								className='bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 text-gray-600 dark:text-gray-300 px-4 py-2.5 rounded-xl font-semibold hover:bg-gray-50 dark:hover:bg-slate-700 duration-300 shadow-sm flex items-center gap-2 disabled:opacity-50'
							>
								<FontAwesomeIcon icon={faTachometerAlt} className={diagLoading ? 'animate-spin' : ''} />
								Діагностика Telegram
							</button>
						</div>
						{diagnostics && (
							<div className={`mb-6 p-5 rounded-2xl border ${diagnostics.error ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800' : 'bg-white dark:bg-slate-800 border-gray-100 dark:border-slate-700'}`}>
								{diagnostics.error ? (
									<p className='text-red-600 dark:text-red-400 font-semibold'>{diagnostics.error}</p>
								) : (
									<div className='grid grid-cols-2 md:grid-cols-4 gap-3 text-sm'>
										<div className={`p-3 rounded-xl ${diagnostics.bot_api_ok ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
											<p className='font-semibold text-gray-700 dark:text-gray-300'>Bot API</p>
											<p className={diagnostics.bot_api_ok ? 'text-green-600' : 'text-red-600'}>{diagnostics.bot_api_ok ? '✓ Працює' : '✗ ' + (diagnostics.bot_api_error || 'Помилка')}</p>
										</div>
										<div className={`p-3 rounded-xl ${diagnostics.telethon_ok ? 'bg-green-50 dark:bg-green-900/20' : 'bg-red-50 dark:bg-red-900/20'}`}>
											<p className='font-semibold text-gray-700 dark:text-gray-300'>Telethon</p>
											<p className={diagnostics.telethon_ok ? 'text-green-600' : 'text-red-600'}>{diagnostics.telethon_ok ? '✓ Підключено' : '✗ ' + (diagnostics.telethon_error || 'Відключено')}</p>
										</div>
										<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
											<p className='font-semibold text-gray-700 dark:text-gray-300'>API ID</p>
											<p className='text-gray-600 dark:text-gray-400'>{diagnostics.telegram_api_id ? '✓ Встановлено' : '✗ Відсутній'}</p>
										</div>
										<div className='bg-gray-50 dark:bg-slate-700/60 p-3 rounded-xl'>
											<p className='font-semibold text-gray-700 dark:text-gray-300'>Аналітика</p>
											<p className={diagnostics.analytics_available ? 'text-green-600' : 'text-yellow-600'}>{diagnostics.analytics_available ? '✓ Повна' : diagnostics.basic_stats_only ? '⚠ Тільки базова' : '✗ Недоступна'}</p>
										</div>
									</div>
								)}
								<button onClick={() => setDiagnostics(null)} className='mt-3 text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'>Закрити</button>
							</div>
						)}
						<FilterPills items={STATUS_FILTERS} active={statusFilter} onChange={setStatusFilter} />
						{loading ? <Loader /> : allChannels.length === 0 ? (
							<EmptyState icon='📋' title='Немає каналів' />
						) : (
							<div className='grid gap-4'>
								{allChannels.map(channel => (
									<div key={channel.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-5 hover:shadow-md duration-300'>
										<div className='flex flex-col md:flex-row md:items-center justify-between gap-3 mb-3'>
											<div className='flex items-center gap-3'>
												{channel.avatar_url ? (
													<img className='w-12 h-12 rounded-full object-cover ring-2 ring-gray-100 dark:ring-slate-600' src={channel.avatar_url} alt='' />
												) : (
													<div className='w-12 h-12 rounded-full bg-gradient-to-br from-blue-100 to-blue-200 dark:from-blue-900 dark:to-blue-800 flex items-center justify-center text-lg font-bold text-blue-500'>
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
												<span className={`text-xs px-3 py-1 rounded-full font-semibold ${STATUS_COLORS[channel.status] || 'bg-gray-100 dark:bg-gray-700'}`}>
													{STATUS_LABELS[channel.status] || channel.status}
												</span>
												<button
													onClick={() => handleRefreshStats(channel.id)}
													disabled={refreshingStats[channel.id]}
													className='text-gray-400 hover:text-green-500 p-2 rounded-lg hover:bg-green-50 dark:hover:bg-green-900/20 duration-300 disabled:opacity-50'
													title='Оновити статистику'
												>
													<FontAwesomeIcon icon={faSync} className={refreshingStats[channel.id] ? 'animate-spin' : ''} />
												</button>
												<button onClick={() => editId === channel.id ? setEditId(null) : startEdit(channel)} className='text-gray-400 hover:text-blue-500 p-2 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 duration-300'>
													<FontAwesomeIcon icon={faPen} />
												</button>
												<button onClick={() => handleDeleteChannel(channel.id)} className='text-gray-400 hover:text-red-500 p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 duration-300'>
													<FontAwesomeIcon icon={faTrash} />
												</button>
											</div>
										</div>
										<div className='grid grid-cols-2 md:grid-cols-5 gap-2 text-sm'>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
												<FontAwesomeIcon icon={faUsers} className='text-gray-400 mr-1' />
												<span className='font-semibold text-gray-800 dark:text-gray-200'>{channel.subscribers_count?.toLocaleString('uk-UA') || '—'}</span>
												<p className='text-gray-400 text-xs'>підписників</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
												<FontAwesomeIcon icon={faEye} className='text-gray-400 mr-1' />
												<span className='font-semibold text-gray-800 dark:text-gray-200'>{channel.views_hidden ? '🔒' : (channel.avg_views?.toLocaleString('uk-UA') || '—')}</span>
												<p className='text-gray-400 text-xs'>переглядів</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
												<FontAwesomeIcon icon={faBarChart} className='text-gray-400 mr-1' />
												<span className='font-semibold text-gray-800 dark:text-gray-200'>{channel.er != null ? channel.er.toFixed(1) + '%' : '—'}</span>
												<p className='text-gray-400 text-xs'>ER</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
												<span className='font-semibold text-green-600'>{channel.price?.toLocaleString('uk-UA')} USDT</span>
												<p className='text-gray-400 text-xs'>ціна</p>
											</div>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
												<FontAwesomeIcon icon={faList} className='text-gray-400 mr-1' />
												<span className='font-semibold text-gray-800 dark:text-gray-200'>{channel.category || '—'}</span>
												<p className='text-gray-400 text-xs'>категорія</p>
											</div>
										</div>
										{channel.seller_telegram && (
											<p className='mt-3 text-sm bg-purple-50 dark:bg-purple-900/20 text-gray-700 dark:text-gray-300 p-2.5 rounded-xl'>
												<span className='font-semibold'>Telegram:</span>{' '}
												<a href={'https://t.me/' + channel.seller_telegram.replace('@', '')} target='_blank' rel='noopener noreferrer' className='text-blue-500 hover:underline'>
													{channel.seller_telegram}
												</a>
											</p>
										)}
										{editId === channel.id && (
											<div className='mt-4 grid md:grid-cols-2 gap-3 bg-gray-50 dark:bg-slate-700/60 p-4 rounded-xl border border-gray-100 dark:border-slate-600'>
												<div>
													<label className='text-xs text-gray-500 dark:text-gray-400 font-medium'>Категорія</label>
													<input value={editData.category} onChange={e => setEditData({ ...editData, category: e.target.value })} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent' />
												</div>
												<div>
													<label className='text-xs text-gray-500 dark:text-gray-400 font-medium'>Ціна (USDT)</label>
													<input value={editData.price} onChange={e => setEditData({ ...editData, price: e.target.value })} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent' />
												</div>
												<div>
													<label className='text-xs text-gray-500 dark:text-gray-400 font-medium'>Дохід/міс (USDT)</label>
													<input value={editData.monthly_income} onChange={e => setEditData({ ...editData, monthly_income: e.target.value })} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent' />
												</div>
												<div>
													<label className='text-xs text-gray-500 dark:text-gray-400 font-medium'>Опис</label>
													<input value={editData.description} onChange={e => setEditData({ ...editData, description: e.target.value })} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent' />
												</div>
												<button onClick={() => handleSaveEdit(channel.id)} className='bg-[#27ae60] text-white px-5 py-2 rounded-xl text-sm font-semibold hover:bg-[#219a52] duration-300 flex items-center gap-2 w-fit shadow-sm'>
													<FontAwesomeIcon icon={faSave} /> Зберегти
												</button>
											</div>
										)}
										{refreshResult[channel.id] && (
											<div className={`mt-3 text-sm p-3 rounded-xl ${refreshResult[channel.id].ok ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400' : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400'}`}>
												{refreshResult[channel.id].ok ? (
													<>
														<span className='font-semibold'>Статистику оновлено:</span>{' '}
														{refreshResult[channel.id].new_stats_records} нових записів, {refreshResult[channel.id].new_posts} нових постів
														{refreshResult[channel.id].telethon_data ? ' (Telethon ✓)' : ' (тільки Bot API)'}
													</>
												) : (
													<><span className='font-semibold'>Помилка:</span> {refreshResult[channel.id].error || 'Невідома помилка'}</>
												)}
											</div>
										)}
									</div>
								))}
							</div>
						)}
					</div>
				)}

				{section === 'deals' && (
					<div>
						<h1 className='text-2xl font-bold text-gray-800 dark:text-white mb-6'>Всі угоди</h1>
						<FilterPills items={DEAL_STATUS_FILTERS} active={dealStatusFilter} onChange={setDealStatusFilter} />
						{loading ? <Loader /> : allDeals.length === 0 ? (
							<EmptyState icon='🤝' title='Немає угод' />
						) : (
							<div className='grid gap-4'>
								{allDeals.map(deal => {
									const statusInfo = DEAL_STATUS_LABELS[deal.status] || DEAL_STATUS_LABELS.created;
									const isTerminal = ['completed', 'cancelled'].includes(deal.status);
									return (
										<div key={deal.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-5 hover:shadow-md duration-300'>
											<div className='flex flex-col md:flex-row md:items-center justify-between gap-3 mb-3'>
												<div>
													<h3 className='font-bold text-gray-800 dark:text-white text-lg'>
														<FontAwesomeIcon icon={faHandshake} className='mr-2 text-blue-400' />
														Угода #{deal.id} — {deal.channel_name || ('Канал #' + deal.channel_id)}
													</h3>
													<p className='text-gray-500 dark:text-gray-400 text-sm mt-1'>
														Покупець: <strong className='text-gray-700 dark:text-gray-300'>{deal.buyer_name || '—'}</strong> · Продавець: <strong className='text-gray-700 dark:text-gray-300'>{deal.seller_name || '—'}</strong>
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
													<span className='font-semibold text-gray-800 dark:text-gray-200'>{deal.service_fee} USDT</span>
													<p className='text-gray-400 text-xs'>комісія</p>
												</div>
												<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
													<span className='font-semibold text-gray-800 dark:text-gray-200'>{fmtDate(deal.created_at)}</span>
													<p className='text-gray-400 text-xs'>створено</p>
												</div>
												<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
													<span className='font-semibold text-gray-800 dark:text-gray-200'>{fmtDate(deal.completed_at)}</span>
													<p className='text-gray-400 text-xs'>завершено</p>
												</div>
											</div>
											{deal.dispute_reason && (
												<p className='text-sm bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400 p-3 rounded-xl mb-3'>
													<span className='font-semibold'>Причина спору:</span> {deal.dispute_reason}
												</p>
											)}
											<div className='flex flex-wrap gap-2'>
												<button onClick={() => setChatDealId(deal.id)} className='bg-[#3498db] text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-[#2980b9] duration-300 flex items-center gap-2'>
													<FontAwesomeIcon icon={faComments} /> Чат
												</button>
												<a href={'/deal/' + deal.id} target='_blank' rel='noopener noreferrer' className='bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-300 px-4 py-2 rounded-xl text-sm font-semibold hover:bg-gray-200 dark:hover:bg-slate-600 duration-300 flex items-center gap-2'>
													<FontAwesomeIcon icon={faArrowRight} /> Відкрити
												</a>
												{deal.status === 'disputed' && (
													<>
														<button onClick={() => handleResolve(deal.id, 'refund_buyer')} className='bg-orange-500 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-orange-600 duration-300'>
															Повернути покупцю
														</button>
														<button onClick={() => handleResolve(deal.id, 'release_seller')} className='bg-[#27ae60] text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-[#219a52] duration-300'>
															Перевести продавцю
														</button>
													</>
												)}
												{!isTerminal && (
													<button onClick={() => handleCancelDeal(deal.id)} className='bg-red-500 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-red-600 duration-300 flex items-center gap-2'>
														<FontAwesomeIcon icon={faBan} /> Скасувати
													</button>
												)}
											</div>
										</div>
									);
								})}
							</div>
						)}
					</div>
				)}

				{section === 'disputes' && (
					<div>
						<h1 className='text-2xl font-bold text-gray-800 dark:text-white mb-6'>Спірні угоди</h1>
						{loading ? <Loader /> : disputes.length === 0 ? (
							<EmptyState icon='⚖️' title='Все спокійно' subtitle='Немає спірних угод' />
						) : (
							<div className='grid gap-5'>
								{disputes.map(deal => (
									<div key={deal.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-6 hover:shadow-md duration-300'>
										<div className='flex items-center justify-between mb-4'>
											<h3 className='font-bold text-lg text-gray-800 dark:text-white'>
												<FontAwesomeIcon icon={faGavel} className='mr-2 text-yellow-500' />
												Угода #{deal.id}
											</h3>
											<span className='text-xs font-semibold text-yellow-700 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900/30 px-3 py-1 rounded-full'>Спір</span>
										</div>
										<p className='text-gray-600 dark:text-gray-300 mb-2'>
											<span className='font-semibold'>Канал:</span> {deal.channel_name || ('#' + deal.channel_id)} · <span className='font-semibold'>Сума:</span> {deal.amount_usdt} USDT
										</p>
										<p className='text-gray-600 dark:text-gray-300 mb-2'>
											<span className='font-semibold'>Покупець:</span> {deal.buyer_name || '—'} · <span className='font-semibold'>Продавець:</span> {deal.seller_name || '—'}
										</p>
										{deal.dispute_reason && (
											<p className='text-gray-600 dark:text-gray-300 mb-4 bg-red-50 dark:bg-red-900/20 p-3 rounded-xl'>
												<span className='font-semibold'>Причина:</span> {deal.dispute_reason}
											</p>
										)}
										<div className='flex flex-wrap gap-3'>
											<button onClick={() => setChatDealId(deal.id)} className='bg-[#3498db] text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-[#2980b9] duration-300 shadow-sm flex items-center gap-2'>
												<FontAwesomeIcon icon={faComments} /> Чат
											</button>
											<button onClick={() => handleResolve(deal.id, 'refund_buyer')} className='bg-orange-500 text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-orange-600 duration-300 shadow-sm'>
												Повернути покупцю
											</button>
											<button onClick={() => handleResolve(deal.id, 'release_seller')} className='bg-[#27ae60] text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-[#219a52] duration-300 shadow-sm'>
												Перевести продавцю
											</button>
											<button onClick={() => handleCancelDeal(deal.id)} className='bg-red-500 text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-red-600 duration-300 shadow-sm flex items-center gap-2'>
												<FontAwesomeIcon icon={faBan} /> Скасувати
											</button>
										</div>
									</div>
								))}
							</div>
						)}
					</div>
				)}

				{section === 'auctions' && (
					<div>
						<h1 className='text-2xl font-bold text-gray-800 dark:text-white mb-6'>Аукціони</h1>
						<FilterPills items={AUCTION_STATUS_FILTERS} active={auctionFilter} onChange={setAuctionFilter} />
						{loading ? <Loader /> : auctions.length === 0 ? (
							<EmptyState icon='🔨' title='Немає аукціонів' />
						) : (
							<div className='grid gap-4'>
								{auctions.map(auction => {
									const statusInfo = AUCTION_STATUS_LABELS[auction.status] || { text: auction.status, color: 'bg-gray-100' };
									const isActive = auction.status === 'active' || auction.status === 'scheduled';
									return (
										<div key={auction.id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-5 hover:shadow-md duration-300'>
											<div className='flex flex-col md:flex-row md:items-center justify-between gap-3 mb-4'>
												<div className='flex items-center gap-3'>
													{auction.channel_avatar ? (
														<img className='w-12 h-12 rounded-full object-cover ring-2 ring-gray-100 dark:ring-slate-600' src={auction.channel_avatar} alt='' />
													) : (
														<div className='w-12 h-12 rounded-full bg-gradient-to-br from-orange-100 to-orange-200 dark:from-orange-900 dark:to-orange-800 flex items-center justify-center text-lg font-bold text-orange-500'>
															🔨
														</div>
													)}
													<div>
														<h3 className='font-bold text-gray-800 dark:text-white'>{auction.channel_name || ('Канал #' + auction.channel_id)}</h3>
														<p className='text-gray-500 dark:text-gray-400 text-sm'>Продавець: {auction.seller_name || '—'}</p>
													</div>
												</div>
												<span className={`text-xs px-3 py-1 rounded-full font-semibold ${statusInfo.color}`}>
													{statusInfo.text}
												</span>
											</div>
											<div className='grid grid-cols-2 md:grid-cols-5 gap-2 text-sm mb-4'>
												<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
													<span className='font-semibold text-gray-800 dark:text-gray-200'>{auction.start_price} USDT</span>
													<p className='text-gray-400 text-xs'>старт</p>
												</div>
												<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
													<span className='font-semibold text-green-600'>{auction.current_price} USDT</span>
													<p className='text-gray-400 text-xs'>поточна</p>
												</div>
												<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
													<span className='font-semibold text-gray-800 dark:text-gray-200'>{auction.buyout_price ? (auction.buyout_price + ' USDT') : '—'}</span>
													<p className='text-gray-400 text-xs'>викуп</p>
												</div>
												<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
													<span className='font-semibold text-gray-800 dark:text-gray-200'>{auction.bid_count}</span>
													<p className='text-gray-400 text-xs'>ставок</p>
												</div>
												<div className='bg-gray-50 dark:bg-slate-700/60 p-2.5 rounded-xl'>
													<span className='font-semibold text-gray-800 dark:text-gray-200'>{isActive ? timeLeft(auction.ends_at) : fmtDate(auction.ends_at)}</span>
													<p className='text-gray-400 text-xs'>{isActive ? 'залишилось' : 'завершено'}</p>
												</div>
											</div>
											{auction.winner_name && (
												<p className='text-sm bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 p-2.5 rounded-xl mb-3'>
													<span className='font-semibold'>Переможець:</span> {auction.winner_name} (ID: {auction.winner_id})
												</p>
											)}
											{extendId === auction.id && (
												<div className='flex items-center gap-3 bg-blue-50 dark:bg-blue-900/20 p-3 rounded-xl mb-3'>
													<span className='text-sm text-gray-600 dark:text-gray-300'>Продовжити на:</span>
													<input type='number' min={1} max={168} value={extendHours} onChange={e => setExtendHours(parseInt(e.target.value) || 1)} className='w-20 border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-1.5 text-sm bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300' />
													<span className='text-sm text-gray-500'>годин</span>
													<button onClick={() => handleExtendAuction(auction.id)} className='bg-[#3498db] text-white px-4 py-1.5 rounded-lg text-sm font-semibold hover:bg-[#2980b9] duration-300'>Підтвердити</button>
													<button onClick={() => setExtendId(null)} className='text-gray-400 hover:text-gray-600 text-sm'>Скасувати</button>
												</div>
											)}
											<div className='flex flex-wrap gap-2'>
												{isActive && (
													<>
														<button onClick={() => setExtendId(extendId === auction.id ? null : auction.id)} className='bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 px-4 py-2 rounded-xl text-sm font-semibold hover:bg-blue-200 dark:hover:bg-blue-900/50 duration-300 flex items-center gap-2'>
															<FontAwesomeIcon icon={faClock} /> Продовжити
														</button>
														<button onClick={() => handleCancelAuction(auction.id)} className='bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 px-4 py-2 rounded-xl text-sm font-semibold hover:bg-red-200 dark:hover:bg-red-900/50 duration-300 flex items-center gap-2'>
															<FontAwesomeIcon icon={faBan} /> Скасувати
														</button>
													</>
												)}
												<button onClick={() => handleDeleteAuction(auction.id)} className='bg-gray-100 dark:bg-slate-700 text-gray-600 dark:text-gray-300 px-4 py-2 rounded-xl text-sm font-semibold hover:bg-gray-200 dark:hover:bg-slate-600 duration-300 flex items-center gap-2'>
													<FontAwesomeIcon icon={faTrash} /> Видалити
												</button>
											</div>
										</div>
									);
								})}
							</div>
						)}
					</div>
				)}

				{section === 'activity' && (
					<div>
						<div className='flex items-center justify-between mb-6'>
							<h1 className='text-2xl font-bold text-gray-800 dark:text-white'>Фейк активність</h1>
							{actConfigDirty && (
								<button onClick={handleSaveActConfig} className='bg-[#27ae60] text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-[#219a52] duration-300 flex items-center gap-2 shadow-sm'>
									<FontAwesomeIcon icon={faSave} /> Зберегти
								</button>
							)}
						</div>
						{loading || !actConfig ? <Loader /> : (
							<div className='space-y-6'>
								<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-6 shadow-sm'>
									<div className='flex items-center justify-between'>
										<div>
											<h3 className='font-bold text-lg text-gray-800 dark:text-white'>Генерація активності</h3>
											<p className='text-gray-500 dark:text-gray-400 text-sm mt-1'>Фейк дані для стрічки та статистики</p>
										</div>
										<button
											onClick={() => handleActConfigChange('enabled', !actConfig.enabled)}
											className={`text-3xl duration-300 ${actConfig.enabled ? 'text-green-500' : 'text-gray-300 dark:text-gray-600'}`}
										>
											<FontAwesomeIcon icon={actConfig.enabled ? faToggleOn : faToggleOff} />
										</button>
									</div>
								</div>
								{actConfig.enabled && (
									<>
										<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-6 shadow-sm'>
											<h3 className='font-bold text-gray-800 dark:text-white mb-4'>Діапазони буст-значень</h3>
											<p className='text-gray-500 dark:text-gray-400 text-sm mb-5'>Min/Max для кожного показника. Реальні дані додаються зверху, буст зменшується при їх рості.</p>
											<div className='grid md:grid-cols-2 gap-4'>
												{[
													{ label: 'Онлайн інвесторів', minKey: 'online_investors_min', maxKey: 'online_investors_max' },
													{ label: 'Угод за тиждень', minKey: 'deals_week_min', maxKey: 'deals_week_max' },
													{ label: 'Ставок сьогодні', minKey: 'bids_today_min', maxKey: 'bids_today_max' },
													{ label: 'Активних аукціонів', minKey: 'active_auctions_min', maxKey: 'active_auctions_max' },
													{ label: 'Каналів в каталозі', minKey: 'channels_min', maxKey: 'channels_max' },
												].map(({ label, minKey, maxKey }) => (
													<div key={minKey} className='bg-gray-50 dark:bg-slate-700/60 p-4 rounded-xl'>
														<p className='text-sm font-medium text-gray-700 dark:text-gray-300 mb-3'>{label}</p>
														<div className='flex items-center gap-3'>
															<div className='flex-1'>
																<label className='text-xs text-gray-400'>Min</label>
																<input type='number' value={actConfig[minKey]} onChange={e => handleActConfigChange(minKey, parseInt(e.target.value) || 0)} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300' />
															</div>
															<span className='text-gray-400 mt-4'>—</span>
															<div className='flex-1'>
																<label className='text-xs text-gray-400'>Max</label>
																<input type='number' value={actConfig[maxKey]} onChange={e => handleActConfigChange(maxKey, parseInt(e.target.value) || 0)} className='w-full border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300' />
															</div>
														</div>
													</div>
												))}
											</div>
										</div>
										<div className='bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-6 shadow-sm'>
											<h3 className='font-bold text-gray-800 dark:text-white mb-4'>Стрічка подій</h3>
											<div className='bg-gray-50 dark:bg-slate-700/60 p-4 rounded-xl'>
												<p className='text-sm font-medium text-gray-700 dark:text-gray-300 mb-2'>Кількість згенерованих подій на день</p>
												<div className='flex items-center gap-3'>
													<input type='number' min={0} max={50} value={actConfig.feed_generated_count} onChange={e => handleActConfigChange('feed_generated_count', parseInt(e.target.value) || 0)} className='w-24 border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300' />
													<span className='text-sm text-gray-500 dark:text-gray-400'>подій (реальні додаються автоматично)</span>
												</div>
											</div>
										</div>
									</>
								)}
							</div>
						)}
					</div>
				)}

				{section === 'escrow' && (
					<div>
						<h1 className='text-2xl font-bold text-gray-800 dark:text-white mb-6'>Ескроу гаманці</h1>
						<div className='bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-200 dark:border-blue-800 rounded-2xl p-6 mb-6'>
							<div className='flex items-center justify-between flex-wrap gap-4'>
								<div>
									<p className='text-gray-500 dark:text-gray-400 text-sm font-medium'>Загальний баланс на ескроу</p>
									<p className='text-3xl font-bold text-gray-800 dark:text-white mt-1'>{escrowTotal.toFixed(2)} <span className='text-lg text-gray-500'>USDT</span></p>
								</div>
								<div className='flex items-center gap-3'>
									<span className='text-sm text-gray-500 dark:text-gray-400'>{escrowWallets.length} гаманців з коштами</span>
									<button onClick={loadData} className='bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 text-gray-600 dark:text-gray-300 px-4 py-2.5 rounded-xl font-semibold hover:bg-gray-50 dark:hover:bg-slate-700 duration-300 shadow-sm flex items-center gap-2'>
										<FontAwesomeIcon icon={faSync} /> Оновити
									</button>
								</div>
							</div>
						</div>
						{loading ? <Loader /> : escrowWallets.length === 0 ? (
							<EmptyState icon='💳' title='Усі ескроу порожні' />
						) : (
							<div className='space-y-4'>
								{escrowWallets.map(w => (
									<div key={w.deal_id} className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 p-6 hover:border-blue-200 dark:hover:border-blue-700 duration-300'>
										<div className='flex flex-col lg:flex-row lg:items-start gap-4'>
											<div className='flex-1 min-w-0'>
												<div className='flex items-center gap-3 mb-3'>
													<span className='text-lg font-bold text-gray-800 dark:text-white'>Угода #{w.deal_id}</span>
													<span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${DEAL_STATUS_LABELS[w.status]?.color || 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'}`}>
														{DEAL_STATUS_LABELS[w.status]?.text || w.status}
													</span>
												</div>
												<div className='flex items-center gap-2 mb-2'>
													<span className='text-sm text-gray-500 dark:text-gray-400'>Ескроу:</span>
													<code className='text-sm bg-gray-50 dark:bg-slate-700/60 px-2 py-1 rounded font-mono text-gray-700 dark:text-gray-300 break-all'>{w.escrow}</code>
													<button onClick={() => copyToClipboard(w.escrow)} className='text-gray-400 hover:text-blue-500 duration-200' title='Копіювати'>
														<FontAwesomeIcon icon={faCopy} className='text-xs' />
													</button>
												</div>
												<p className='text-2xl font-bold text-green-600'>{w.balance_usdt.toFixed(2)} <span className='text-sm text-gray-400'>USDT</span></p>
											</div>
											<div className='lg:w-96 flex-shrink-0'>
												<label className='text-sm text-gray-500 dark:text-gray-400 font-medium mb-1.5 block'>Перевести на адресу (TRC-20)</label>
												<div className='flex gap-2'>
													<input type='text' value={sweepTarget[w.deal_id] || ''} onChange={e => setSweepTarget(prev => ({ ...prev, [w.deal_id]: e.target.value }))} placeholder='TRC-20 адреса...' className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-2.5 text-sm font-mono bg-white dark:bg-slate-700 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-transparent' />
													<button onClick={() => handleSweep(w.deal_id)} disabled={sweeping[w.deal_id]} className='bg-[#3498db] text-white px-5 py-2.5 rounded-xl font-semibold hover:bg-[#2980b9] duration-300 shadow-sm flex items-center gap-2 disabled:opacity-50 whitespace-nowrap'>
														<FontAwesomeIcon icon={faPaperPlane} />
														{sweeping[w.deal_id] ? '...' : 'Перевести'}
													</button>
												</div>
												<p className='text-xs text-gray-400 dark:text-gray-500 mt-1.5'>TRX потрібен на мастер-гаманці для газу</p>
											</div>
										</div>
									</div>
								))}
							</div>
						)}
					</div>
				)}

				{chatDealId && (
					<DealChatModal dealId={chatDealId} userId={user?.id} onClose={() => setChatDealId(null)} />
				)}
			</main>
		</section>
	);
};

export default ModerCabinet;
