import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { dealsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';

const STEPS = [
	{ key: 'created', label: 'Готовність', icon: '🤝' },
	{ key: 'payment_pending', label: 'Оплата', icon: '💰' },
	{ key: 'paid', label: 'Передача', icon: '📤' },
	{ key: 'awaiting_payout', label: 'Виплата', icon: '💳' },
	{ key: 'completed', label: 'Завершено', icon: '✅' },
];

const STATUS_META = {
	created: { stepIndex: 0 },
	payment_pending: { stepIndex: 1 },
	paid: { stepIndex: 2 },
	channel_transferring: { stepIndex: 2 },
	awaiting_payout: { stepIndex: 3 },
	completed: { stepIndex: 4 },
	disputed: { stepIndex: -1 },
	cancelled: { stepIndex: -1 },
};

const StepProgress = ({ status }) => {
	const meta = STATUS_META[status] || { stepIndex: -1 };
	const currentIdx = meta.stepIndex;

	if (currentIdx === -1) return null;

	return (
		<div className='flex items-center justify-between mb-8 px-2'>
			{STEPS.map((step, i) => {
				const done = i < currentIdx;
				const active = i === currentIdx;
				return (
					<div key={step.key} className='flex items-center flex-1 last:flex-none'>
						<div className='flex flex-col items-center'>
							<div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold transition-all duration-500 ${
								done ? 'bg-green-500 text-white shadow-md shadow-green-200' :
								active ? 'bg-[#3498db] text-white shadow-lg shadow-blue-200 scale-110' :
								'bg-gray-100 text-gray-400'
							}`}>
								{done ? '✓' : step.icon}
							</div>
							<span className={`text-xs mt-1.5 font-medium whitespace-nowrap ${
								active ? 'text-[#3498db]' : done ? 'text-green-600' : 'text-gray-400'
							}`}>
								{step.label}
							</span>
						</div>
						{i < STEPS.length - 1 && (
							<div className={`flex-1 h-0.5 mx-2 mt-[-16px] rounded-full transition-all duration-500 ${
								i < currentIdx ? 'bg-green-400' : 'bg-gray-200'
							}`} />
						)}
					</div>
				);
			})}
		</div>
	);
};

const DealChat = ({ dealId, userId, onCallAdmin, deal }) => {
	const [messages, setMessages] = useState([]);
	const [newMessage, setNewMessage] = useState('');
	const [sending, setSending] = useState(false);
	const [callingAdmin, setCallingAdmin] = useState(false);
	const messagesEndRef = useRef(null);
	const chatContainerRef = useRef(null);
	const prevMessageCount = useRef(0);

	const fetchMessages = async () => {
		try {
			const { data } = await dealsAPI.getMessages(dealId);
			setMessages(data);
		} catch (err) {
			// silent
		}
	};

	useEffect(() => {
		fetchMessages();
		const interval = setInterval(fetchMessages, 5000);
		return () => clearInterval(interval);
	}, [dealId]);

	useEffect(() => {
		const container = chatContainerRef.current;
		if (!container) return;
		// Auto-scroll only if user is near the bottom or new messages arrived
		const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
		const isNewMessage = messages.length > prevMessageCount.current;
		if (isNearBottom || isNewMessage) {
			messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
		}
		prevMessageCount.current = messages.length;
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
		} catch (err) {
			// silent
		} finally {
			setSending(false);
		}
	};

	const handleCallAdmin = async () => {
		if (callingAdmin) return;
		setCallingAdmin(true);
		try {
			await onCallAdmin?.();
		} finally {
			setCallingAdmin(false);
		}
	};

	return (
		<div className='bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden mb-6'>
			<div className='flex items-center justify-between px-6 py-4 border-b border-gray-100'>
				<h3 className='font-bold text-lg'>Чат</h3>
				{deal && !['completed', 'cancelled'].includes(deal.status) && (
					<button
						onClick={handleCallAdmin}
						disabled={callingAdmin}
						className='bg-yellow-50 text-yellow-700 border border-yellow-200 px-4 py-2 rounded-xl text-sm font-semibold hover:bg-yellow-100 transition-all duration-300 disabled:opacity-50'
					>
						{callingAdmin ? '...' : '🛡️ Викликати адміна'}
					</button>
				)}
			</div>
			<div ref={chatContainerRef} className='bg-gray-50 p-4 h-80 overflow-y-auto'>
				{messages.length === 0 && (
					<p className='text-gray-400 text-center mt-20 text-sm'>
						Повідомлень ще немає. Напишіть першими!
					</p>
				)}
				{messages.map((msg) => {
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
						<div
							key={msg.id}
							className={`mb-3 flex ${isOwn ? 'justify-end' : 'justify-start'}`}
						>
							<div
								className={`max-w-[75%] px-4 py-2 rounded-lg ${
									isOwn
										? 'bg-[#3498db] text-white rounded-br-none'
										: 'bg-gray-200 text-gray-800 rounded-bl-none'
								}`}
							>
								{!isOwn && (
									<p className='text-xs font-bold mb-1 opacity-70'>
										{msg.sender_name || 'Користувач'}
									</p>
								)}
								<p className='text-sm whitespace-pre-wrap break-words'>{msg.text}</p>
								<p className={`text-xs mt-1 ${isOwn ? 'text-blue-100' : 'text-gray-400'}`}>
									{new Date(msg.created_at).toLocaleString('uk-UA', {
										hour: '2-digit',
										minute: '2-digit',
										day: '2-digit',
										month: '2-digit',
									})}
								</p>
							</div>
						</div>
					);
				})}
				<div ref={messagesEndRef} />
			</div>
			<form onSubmit={handleSend} className='flex gap-2 p-4 border-t border-gray-100'>
				<input
					type='text'
					value={newMessage}
					onChange={(e) => setNewMessage(e.target.value)}
					placeholder='Напишіть повідомлення...'
					maxLength={2000}
					className='flex-1 border border-gray-200 rounded-xl px-4 py-2.5 focus:border-[#3498db] focus:ring-2 focus:ring-blue-100 focus:outline-none transition-all'
				/>
				<button
					type='submit'
					disabled={sending || !newMessage.trim()}
					className='bg-[#3498db] text-white px-6 py-2.5 rounded-xl font-bold hover:bg-blue-600 transition-all duration-300 disabled:opacity-50'
				>
					{sending ? '...' : '→'}
				</button>
			</form>
		</div>
	);
};

const DealPage = () => {
	const { id } = useParams();
	const { user } = useAuth();
	const [deal, setDeal] = useState(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState(null);
	const [actionLoading, setActionLoading] = useState(false);
	const [walletAddress, setWalletAddress] = useState('');
	const [copied, setCopied] = useState(false);

	const refreshDeal = async () => {
		try {
			const { data } = await dealsAPI.getById(id);
			setDeal(data);
		} catch (err) {
			setError('Не вдалося завантажити угоду');
		}
	};

	useEffect(() => {
		const fetchDeal = async () => {
			await refreshDeal();
			setLoading(false);
		};
		fetchDeal();
		const interval = setInterval(refreshDeal, 10000);
		return () => clearInterval(interval);
	}, [id]);

	const handleAction = async (action) => {
		setActionLoading(true);
		try {
			await action();
			await refreshDeal();
		} catch (err) {
			setError(err.response?.data?.detail || 'Помилка');
			setTimeout(() => setError(null), 4000);
		} finally {
			setActionLoading(false);
		}
	};

	const handleConfirmReady = () => handleAction(() => dealsAPI.confirmReady(id));
	const handleConfirmTransfer = () => handleAction(() => dealsAPI.confirmChannelTransfer(id));
	const handleSubmitWallet = () => {
		if (!walletAddress.trim()) return;
		handleAction(() => dealsAPI.setSellerWallet(id, walletAddress.trim()));
	};
	const handleCallAdmin = () => handleAction(() => dealsAPI.callAdmin(id));

	const handleDispute = async () => {
		const reason = prompt('Опишіть причину спору:');
		if (!reason) return;
		handleAction(() => dealsAPI.dispute(id, reason));
	};

	const copyToClipboard = (text) => {
		navigator.clipboard.writeText(text);
		setCopied(true);
		setTimeout(() => setCopied(false), 2000);
	};

	if (loading) {
		return (
			<div className='my-28 flex justify-center'>
				<div className='animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#3498db]'></div>
			</div>
		);
	}

	if (error && !deal) {
		return (
			<div className='my-28 text-center'>
				<p className='text-red-500 text-xl'>{error}</p>
			</div>
		);
	}

	if (!deal) return null;

	const isBuyer = user?.id === deal.buyer_id;
	const isSeller = user?.id === deal.seller_id;
	const isSpecialStatus = ['disputed', 'cancelled'].includes(deal.status);

	return (
		<section className='my-28 max-w-3xl mx-auto px-4'>

			{/* Error toast */}
			{error && (
				<div className='bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-2xl mb-6 text-sm animate-fadeIn'>
					{error}
				</div>
			)}

			{/* Hero header */}
			<div className='bg-gradient-to-br from-[#3498db] to-[#2573a7] rounded-2xl p-6 mb-6 text-white shadow-xl shadow-blue-100'>
				<div className='flex items-start justify-between'>
					<div>
						<p className='text-blue-200 text-xs font-medium uppercase tracking-wider mb-1'>
							{isBuyer ? 'Ви купуєте' : 'Ви продаєте'}
						</p>
						<h1 className='text-2xl font-bold mb-1'>
							{deal.channel_name || `Канал #${deal.channel_id}`}
						</h1>
						<p className='text-blue-100 text-sm'>
							{isBuyer ? deal.seller_name || 'Продавець' : deal.buyer_name || 'Покупець'} · {new Date(deal.created_at).toLocaleDateString('uk-UA')}
						</p>
					</div>
					<div className='text-right'>
						<p className='text-3xl font-extrabold'>{deal.amount_usdt}</p>
						<p className='text-blue-200 text-sm font-medium'>USDT</p>
					</div>
				</div>
			</div>

			{/* Special statuses */}
			{deal.status === 'disputed' && (
				<div className='bg-red-50 border border-red-200 rounded-2xl p-5 mb-6 text-center'>
					<p className='text-red-600 font-bold text-lg'>⚠️ Спір</p>
					<p className='text-red-500 text-sm mt-1'>Адміністратор розглядає це питання</p>
				</div>
			)}
			{deal.status === 'cancelled' && (
				<div className='bg-gray-50 border border-gray-200 rounded-2xl p-5 mb-6 text-center'>
					<p className='text-gray-500 font-bold text-lg'>Угода скасована</p>
				</div>
			)}

			{/* Step Progress */}
			{!isSpecialStatus && <StepProgress status={deal.status} />}

			{/* Step 1: Confirm Readiness */}
			{deal.status === 'created' && (
				<div className='bg-white rounded-2xl shadow-lg border border-gray-100 p-6 mb-6'>
					<h3 className='font-bold text-lg mb-2'>Підтвердіть готовність до угоди</h3>
					<p className='text-gray-500 text-sm mb-5'>
						Обидві сторони повинні підтвердити готовність. Після цього покупець зможе оплатити.
					</p>
					<div className='flex gap-3 mb-5'>
						<div className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 transition-all duration-300 ${
							deal.buyer_ready ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50'
						}`}>
							<div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
								deal.buyer_ready ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-400'
							}`}>
								{deal.buyer_ready ? '✓' : '1'}
							</div>
							<div>
								<p className='font-semibold text-sm'>Покупець</p>
								<p className={`text-xs ${deal.buyer_ready ? 'text-green-600' : 'text-gray-400'}`}>
									{deal.buyer_ready ? 'Готовий' : 'Очікує'}
								</p>
							</div>
						</div>
						<div className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 transition-all duration-300 ${
							deal.seller_ready ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50'
						}`}>
							<div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
								deal.seller_ready ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-400'
							}`}>
								{deal.seller_ready ? '✓' : '2'}
							</div>
							<div>
								<p className='font-semibold text-sm'>Продавець</p>
								<p className={`text-xs ${deal.seller_ready ? 'text-green-600' : 'text-gray-400'}`}>
									{deal.seller_ready ? 'Готовий' : 'Очікує'}
								</p>
							</div>
						</div>
					</div>
					{((isBuyer && !deal.buyer_ready) || (isSeller && !deal.seller_ready)) ? (
						<button
							onClick={handleConfirmReady}
							disabled={actionLoading}
							className='w-full font-bold bg-[#3498db] text-white py-3.5 rounded-xl shadow-lg shadow-blue-100 hover:bg-blue-600 transition-all duration-300 disabled:opacity-50'
						>
							{actionLoading ? 'Зачекайте...' : 'Підтвердити готовність'}
						</button>
					) : (
						<div className='bg-blue-50 text-blue-600 text-sm font-medium px-4 py-3 rounded-xl text-center'>
							Ви підтвердили. Очікуйте іншу сторону
						</div>
					)}
				</div>
			)}

			{/* Step 2: Payment */}
			{deal.status === 'payment_pending' && isBuyer && (
				<div className='bg-white rounded-2xl shadow-lg border border-gray-100 p-6 mb-6'>
					<h3 className='font-bold text-lg mb-2'>Оплата</h3>
					<p className='text-gray-500 text-sm mb-5'>
						Переведіть <strong className='text-gray-800'>{deal.amount_usdt} USDT</strong> через мережу <strong className='text-gray-800'>TRC-20</strong>
					</p>
					<div className='relative bg-gray-50 border border-gray-200 p-4 rounded-xl mb-4 group'>
						<p className='font-mono text-sm break-all pr-10 select-all text-gray-700'>
							{deal.escrow_wallet_address}
						</p>
						<button
							onClick={() => copyToClipboard(deal.escrow_wallet_address)}
							className='absolute top-3 right-3 bg-white border border-gray-200 rounded-lg px-2.5 py-1.5 text-xs font-medium text-gray-500 hover:text-[#3498db] hover:border-[#3498db] transition-all'
						>
							{copied ? '✓' : 'Копіювати'}
						</button>
					</div>
					<div className='flex items-start gap-2 bg-yellow-50 border border-yellow-200 rounded-xl px-4 py-3'>
						<span className='text-yellow-500 text-sm mt-0.5'>⚠️</span>
						<div className='text-xs text-yellow-700'>
							<p className='font-semibold'>Переводьте тільки USDT через TRC-20!</p>
							<p className='mt-0.5 text-yellow-600'>Оплата перевіряється автоматично кожні 30 секунд</p>
						</div>
					</div>
				</div>
			)}
			{deal.status === 'payment_pending' && isSeller && (
				<div className='bg-white rounded-2xl shadow-lg border border-gray-100 p-6 mb-6'>
					<div className='flex items-center gap-3'>
						<div className='w-10 h-10 rounded-full bg-yellow-50 flex items-center justify-center'>
							<span className='text-xl'>⏳</span>
						</div>
						<div>
							<h3 className='font-bold'>Очікування оплати</h3>
							<p className='text-gray-500 text-sm'>Покупець здійснює переказ</p>
						</div>
					</div>
				</div>
			)}

			{/* Step 3: Channel Transfer */}
			{deal.status === 'paid' && (
				<div className='bg-white rounded-2xl shadow-lg border border-gray-100 p-6 mb-6'>
					<h3 className='font-bold text-lg mb-2'>Передача каналу</h3>
					{isSeller && (
						<p className='text-gray-500 text-sm mb-5'>
							Кошти отримані! Передайте канал через Telegram:
							<span className='block text-gray-400 text-xs mt-1'>Settings → Channel → Administrators → Transfer Ownership</span>
						</p>
					)}
					{isBuyer && (
						<p className='text-gray-500 text-sm mb-5'>
							Кошти на рахунку. Перевірте, чи ви отримали права на канал.
						</p>
					)}
					<div className='flex gap-3 mb-5'>
						<div className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 transition-all duration-300 ${
							deal.buyer_confirmed_transfer ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50'
						}`}>
							<div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
								deal.buyer_confirmed_transfer ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-400'
							}`}>
								{deal.buyer_confirmed_transfer ? '✓' : '⏳'}
							</div>
							<div>
								<p className='font-semibold text-sm'>Покупець</p>
								<p className={`text-xs ${deal.buyer_confirmed_transfer ? 'text-green-600' : 'text-gray-400'}`}>
									{deal.buyer_confirmed_transfer ? 'Підтвердив' : 'Очікує'}
								</p>
							</div>
						</div>
						<div className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 transition-all duration-300 ${
							deal.seller_confirmed_transfer ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50'
						}`}>
							<div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
								deal.seller_confirmed_transfer ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-400'
							}`}>
								{deal.seller_confirmed_transfer ? '✓' : '⏳'}
							</div>
							<div>
								<p className='font-semibold text-sm'>Продавець</p>
								<p className={`text-xs ${deal.seller_confirmed_transfer ? 'text-green-600' : 'text-gray-400'}`}>
									{deal.seller_confirmed_transfer ? 'Підтвердив' : 'Очікує'}
								</p>
							</div>
						</div>
					</div>
					{((isBuyer && !deal.buyer_confirmed_transfer) || (isSeller && !deal.seller_confirmed_transfer)) ? (
						<div className='flex gap-3'>
							<button
								onClick={handleConfirmTransfer}
								disabled={actionLoading}
								className='flex-1 font-bold bg-[#27ae60] text-white py-3.5 rounded-xl shadow-lg shadow-green-100 hover:bg-green-600 transition-all duration-300 disabled:opacity-50'
							>
								{actionLoading ? 'Зачекайте...' : isBuyer ? 'Підтвердити отримання' : 'Підтвердити передачу'}
							</button>
							{isBuyer && (
								<button
									onClick={handleDispute}
									disabled={actionLoading}
									className='bg-red-50 text-red-500 border border-red-200 px-5 py-3.5 rounded-xl font-semibold hover:bg-red-100 transition-all duration-300 disabled:opacity-50'
								>
									Спір
								</button>
							)}
						</div>
					) : (
						<div className='bg-blue-50 text-blue-600 text-sm font-medium px-4 py-3 rounded-xl text-center'>
							Ви підтвердили. Очікуйте іншу сторону
						</div>
					)}
				</div>
			)}

			{/* Step 4: Seller Wallet */}
			{deal.status === 'awaiting_payout' && isSeller && (
				<div className='bg-white rounded-2xl shadow-lg border border-gray-100 p-6 mb-6'>
					<h3 className='font-bold text-lg mb-2'>Отримання коштів</h3>
					<p className='text-gray-500 text-sm mb-1'>
						Канал успішно передано! Вкажіть вашу USDT (TRC-20) адресу.
					</p>
					<p className='text-gray-400 text-xs mb-5'>Комісія сервісу: 3%</p>
					<div className='flex gap-2 mb-3'>
						<input
							type='text'
							value={walletAddress}
							onChange={(e) => setWalletAddress(e.target.value)}
							placeholder='TRC-20 адреса (T...)'
							maxLength={100}
							className='flex-1 border border-gray-200 rounded-xl px-4 py-3.5 focus:border-[#3498db] focus:ring-2 focus:ring-blue-100 focus:outline-none font-mono text-sm transition-all'
						/>
						<button
							onClick={handleSubmitWallet}
							disabled={actionLoading || !walletAddress.trim()}
							className='font-bold bg-[#27ae60] text-white px-6 py-3.5 rounded-xl shadow-lg shadow-green-100 hover:bg-green-600 transition-all duration-300 disabled:opacity-50 whitespace-nowrap'
						>
							{actionLoading ? 'Переказ...' : 'Отримати'}
						</button>
					</div>
					<p className='text-red-400 text-xs'>
						⚠️ Ретельно перевірте адресу — помилка призведе до втрати коштів
					</p>
				</div>
			)}
			{deal.status === 'awaiting_payout' && isBuyer && (
				<div className='bg-white rounded-2xl shadow-lg border border-gray-100 p-6 mb-6'>
					<div className='flex items-center gap-3'>
						<div className='w-10 h-10 rounded-full bg-purple-50 flex items-center justify-center'>
							<span className='text-xl'>💳</span>
						</div>
						<div>
							<h3 className='font-bold'>Виплата продавцю</h3>
							<p className='text-gray-500 text-sm'>Продавець отримує кошти</p>
						</div>
					</div>
				</div>
			)}

			{/* Step 5: Completed */}
			{deal.status === 'completed' && (
				<div className='bg-gradient-to-br from-green-50 to-emerald-50 border border-green-200 rounded-2xl p-8 mb-6 text-center'>
					<div className='w-16 h-16 rounded-full bg-green-500 text-white flex items-center justify-center text-3xl mx-auto mb-4 shadow-lg shadow-green-200'>
						✓
					</div>
					<h3 className='font-bold text-xl text-green-700 mb-1'>Угода завершена</h3>
					<p className='text-green-600 text-sm'>Дякуємо за використання TgSell!</p>
					{deal.payout_tx_hash && (
						<p className='text-gray-400 text-xs mt-4 font-mono break-all'>
							TX: {deal.payout_tx_hash}
						</p>
					)}
				</div>
			)}

			{/* Deal Chat */}
			<DealChat dealId={deal.id} userId={user?.id} onCallAdmin={handleCallAdmin} deal={deal} />
		</section>
	);
};

export default DealPage;
