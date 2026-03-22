import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { dealsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';

const STATUS_LABELS = {
	created: { text: 'Очікує підтвердження готовності', color: 'bg-yellow-500' },
	payment_pending: { text: 'Очікує оплати', color: 'bg-yellow-500' },
	paid: { text: 'Оплачено — передайте канал', color: 'bg-blue-500' },
	channel_transferring: { text: 'Передача каналу', color: 'bg-blue-500' },
	awaiting_payout: { text: 'Очікує виплати продавцю', color: 'bg-purple-500' },
	completed: { text: 'Завершено', color: 'bg-green-500' },
	disputed: { text: 'Спір', color: 'bg-red-500' },
	cancelled: { text: 'Скасовано', color: 'bg-gray-500' },
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
		<div className='bg-white rounded-2xl shadow-lg p-6 mb-6'>
			<div className='flex items-center justify-between mb-4'>
				<h3 className='font-bold text-lg'>💬 Чат угоди</h3>
				{deal && !['completed', 'cancelled'].includes(deal.status) && (
					<button
						onClick={handleCallAdmin}
						disabled={callingAdmin}
						className='bg-yellow-500 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-yellow-600 duration-300 disabled:opacity-50'
					>
						{callingAdmin ? '...' : '🛡️ Викликати адміна'}
					</button>
				)}
			</div>
			<div ref={chatContainerRef} className='bg-gray-50 rounded-xl p-4 h-80 overflow-y-auto mb-4'>
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
			<form onSubmit={handleSend} className='flex gap-2'>
				<input
					type='text'
					value={newMessage}
					onChange={(e) => setNewMessage(e.target.value)}
					placeholder='Напишіть повідомлення...'
					maxLength={2000}
					className='flex-1 border border-gray-300 rounded-md px-4 py-2 focus:border-[#3498db] focus:outline-none'
				/>
				<button
					type='submit'
					disabled={sending || !newMessage.trim()}
					className='bg-[#3498db] text-white px-6 py-2 rounded-md font-bold hover:bg-blue-600 duration-300 disabled:opacity-50'
				>
					{sending ? '...' : 'Надіслати'}
				</button>
			</form>
			<p className='text-gray-400 text-xs mt-2'>
				Усі повідомлення зберігаються для арбітражу
			</p>
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

	const statusInfo = STATUS_LABELS[deal.status] || STATUS_LABELS.created;
	const isBuyer = user?.id === deal.buyer_id;
	const isSeller = user?.id === deal.seller_id;

	return (
		<section className='my-28 max-w-3xl mx-auto px-4'>
			<h1 className='text-3xl font-bold text-[#3498db] mb-8'>
				Угода #{deal.id}
			</h1>

			{/* Error Toast */}
			{error && (
				<div className='bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl mb-6 text-sm'>
					{error}
				</div>
			)}

			{/* Status Badge */}
			<div className={`${statusInfo.color} text-white text-center py-3 rounded-xl mb-8 font-bold text-lg`}>
				{statusInfo.text}
			</div>

			{/* Deal Info Card */}
			<div className='bg-white rounded-2xl shadow-lg p-6 mb-6'>
				<h3 className='font-bold text-lg mb-4'>Деталі угоди</h3>
				<div className='grid grid-cols-2 gap-4'>
					<div>
						<p className='text-gray-500 text-sm'>Канал</p>
						<p className='font-bold'>{deal.channel_name || `Канал #${deal.channel_id}`}</p>
					</div>
					<div>
						<p className='text-gray-500 text-sm'>Сума</p>
						<p className='font-bold text-[#27ae60]'>{deal.amount_usdt} USDT</p>
					</div>
					<div>
						<p className='text-gray-500 text-sm'>Покупець</p>
						<p className='font-bold'>{deal.buyer_name || 'Покупець'}</p>
					</div>
					<div>
						<p className='text-gray-500 text-sm'>Продавець</p>
						<p className='font-bold'>{deal.seller_name || 'Продавець'}</p>
					</div>
				</div>
			</div>

			{/* Step 1: Confirm Readiness (status: created) */}
			{deal.status === 'created' && (
				<div className='bg-white rounded-2xl shadow-lg p-6 mb-6'>
					<h3 className='font-bold text-lg mb-4'>🤝 Підтвердження готовності</h3>
					<p className='text-gray-600 mb-4'>
						Обидві сторони повинні підтвердити готовність до угоди, перш ніж покупець зможе оплатити.
					</p>
					<div className='flex items-center gap-4 mb-4'>
						<div className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold ${deal.buyer_ready ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
							{deal.buyer_ready ? '✅' : '⏳'} Покупець
						</div>
						<div className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold ${deal.seller_ready ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
							{deal.seller_ready ? '✅' : '⏳'} Продавець
						</div>
					</div>
					{((isBuyer && !deal.buyer_ready) || (isSeller && !deal.seller_ready)) && (
						<button
							onClick={handleConfirmReady}
							disabled={actionLoading}
							className='font-bold bg-[#3498db] text-white py-3 px-8 rounded-xl shadow-lg hover:bg-blue-600 duration-300 disabled:opacity-50'
						>
							{actionLoading ? 'Зачекайте...' : '✅ Підтвердити готовність'}
						</button>
					)}
					{((isBuyer && deal.buyer_ready) || (isSeller && deal.seller_ready)) && (
						<p className='text-green-600 font-semibold text-sm'>
							Ви підтвердили готовність. Очікуйте підтвердження іншої сторони.
						</p>
					)}
				</div>
			)}

			{/* Step 2: Payment (status: payment_pending) */}
			{deal.status === 'payment_pending' && isBuyer && (
				<div className='bg-white rounded-2xl shadow-lg p-6 mb-6'>
					<h3 className='font-bold text-lg mb-4'>💰 Оплата</h3>
					<p className='mb-2'>Переведіть <strong>{deal.amount_usdt} USDT (TRC-20)</strong> на адресу:</p>
					<div className='bg-gray-100 p-4 rounded-xl font-mono text-sm break-all select-all mb-4'>
						{deal.escrow_wallet_address}
					</div>
					<p className='text-gray-500 text-sm'>
						⏳ Оплата автоматично перевіряється кожні 30 секунд.
					</p>
					<p className='text-red-500 text-sm mt-2'>
						⚠️ Переводьте тільки USDT через мережу TRC-20!
					</p>
				</div>
			)}

			{deal.status === 'payment_pending' && isSeller && (
				<div className='bg-white rounded-2xl shadow-lg p-6 mb-6'>
					<h3 className='font-bold text-lg mb-4'>⏳ Очікування оплати</h3>
					<p className='text-gray-600'>
						Покупець здійснює оплату. Ви отримаєте повідомлення, коли кошти надійдуть.
					</p>
				</div>
			)}

			{/* Step 3: Channel Transfer (status: paid) */}
			{deal.status === 'paid' && (
				<div className='bg-white rounded-2xl shadow-lg p-6 mb-6'>
					<h3 className='font-bold text-lg mb-4'>📤 Передача каналу</h3>
					{isSeller && (
						<>
							<p className='mb-4'>
								Кошти отримані! Передайте права власності на канал покупцю через Telegram:
								<br />
								<span className='text-gray-500 text-sm'>Settings → Channel → Administrators → Transfer Ownership</span>
							</p>
							<div className='flex items-center gap-4 mb-4'>
								<div className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold ${deal.seller_confirmed_transfer ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
									{deal.seller_confirmed_transfer ? '✅' : '⏳'} Ви (продавець)
								</div>
								<div className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold ${deal.buyer_confirmed_transfer ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
									{deal.buyer_confirmed_transfer ? '✅' : '⏳'} Покупець
								</div>
							</div>
							{!deal.seller_confirmed_transfer && (
								<button
									onClick={handleConfirmTransfer}
									disabled={actionLoading}
									className='font-bold bg-[#27ae60] text-white py-3 px-8 rounded-xl shadow-lg hover:bg-green-600 duration-300 disabled:opacity-50 mr-4'
								>
									{actionLoading ? 'Зачекайте...' : '✅ Підтвердити передачу'}
								</button>
							)}
						</>
					)}
					{isBuyer && (
						<>
							<p className='mb-4'>
								Продавець передає вам канал. Перевірте, чи ви отримали права власності.
							</p>
							<div className='flex items-center gap-4 mb-4'>
								<div className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold ${deal.buyer_confirmed_transfer ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
									{deal.buyer_confirmed_transfer ? '✅' : '⏳'} Ви (покупець)
								</div>
								<div className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold ${deal.seller_confirmed_transfer ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
									{deal.seller_confirmed_transfer ? '✅' : '⏳'} Продавець
								</div>
							</div>
							{!deal.buyer_confirmed_transfer && (
								<>
									<button
										onClick={handleConfirmTransfer}
										disabled={actionLoading}
										className='font-bold bg-[#27ae60] text-white py-3 px-8 rounded-xl shadow-lg hover:bg-green-600 duration-300 disabled:opacity-50 mr-4'
									>
										{actionLoading ? 'Зачекайте...' : '✅ Підтвердити отримання'}
									</button>
									<button
										onClick={handleDispute}
										disabled={actionLoading}
										className='font-bold bg-red-500 text-white py-3 px-8 rounded-xl shadow-lg hover:bg-red-600 duration-300 disabled:opacity-50'
									>
										⚠️ Відкрити спір
									</button>
								</>
							)}
						</>
					)}
				</div>
			)}

			{/* Step 4: Seller Wallet (status: awaiting_payout) */}
			{deal.status === 'awaiting_payout' && isSeller && (
				<div className='bg-white rounded-2xl shadow-lg p-6 mb-6'>
					<h3 className='font-bold text-lg mb-4'>💳 Адреса для виплати</h3>
					<p className='text-gray-600 mb-4'>
						Канал передано! Вкажіть вашу USDT (TRC-20) адресу для отримання коштів.
						<br />
						<span className='text-sm text-gray-400'>Комісія сервісу: 3%</span>
					</p>
					<div className='flex gap-2'>
						<input
							type='text'
							value={walletAddress}
							onChange={(e) => setWalletAddress(e.target.value)}
							placeholder='T...'
							maxLength={100}
							className='flex-1 border border-gray-300 rounded-xl px-4 py-3 focus:border-[#3498db] focus:outline-none font-mono text-sm'
						/>
						<button
							onClick={handleSubmitWallet}
							disabled={actionLoading || !walletAddress.trim()}
							className='font-bold bg-[#27ae60] text-white px-8 py-3 rounded-xl shadow-lg hover:bg-green-600 duration-300 disabled:opacity-50'
						>
							{actionLoading ? 'Переказ...' : '💸 Отримати кошти'}
						</button>
					</div>
					<p className='text-red-500 text-xs mt-2'>
						⚠️ Перевірте адресу! Помилка в адресі призведе до втрати коштів.
					</p>
				</div>
			)}

			{deal.status === 'awaiting_payout' && isBuyer && (
				<div className='bg-white rounded-2xl shadow-lg p-6 mb-6'>
					<h3 className='font-bold text-lg mb-4'>⏳ Виплата продавцю</h3>
					<p className='text-gray-600'>
						Канал передано! Продавець вказує адресу для отримання коштів.
					</p>
				</div>
			)}

			{/* Step 5: Completed */}
			{deal.status === 'completed' && (
				<div className='bg-green-50 rounded-2xl shadow-lg p-6 mb-6 text-center'>
					<h3 className='font-bold text-xl mb-2 text-green-600'>✅ Угода завершена!</h3>
					<p className='text-gray-600'>Дякуємо за використання TgSell!</p>
					{deal.payout_tx_hash && (
						<p className='text-gray-400 text-xs mt-3 font-mono break-all'>
							TX: {deal.payout_tx_hash}
						</p>
					)}
				</div>
			)}

			{/* Deal Chat */}
			<DealChat dealId={deal.id} userId={user?.id} onCallAdmin={handleCallAdmin} deal={deal} />

			{/* Timeline */}
			<div className='bg-white rounded-2xl shadow-lg p-6'>
				<h3 className='font-bold text-lg mb-4'>📋 Хронологія</h3>
				<div className='space-y-3'>
					<div className='flex items-center gap-3'>
						<div className='w-3 h-3 rounded-full bg-green-500'></div>
						<p className='text-sm'>Угода створена — {new Date(deal.created_at).toLocaleString('uk-UA')}</p>
					</div>
					{deal.paid_at && (
						<div className='flex items-center gap-3'>
							<div className='w-3 h-3 rounded-full bg-green-500'></div>
							<p className='text-sm'>Оплата отримана — {new Date(deal.paid_at).toLocaleString('uk-UA')}</p>
						</div>
					)}
					{deal.completed_at && (
						<div className='flex items-center gap-3'>
							<div className='w-3 h-3 rounded-full bg-green-500'></div>
							<p className='text-sm'>Угода завершена — {new Date(deal.completed_at).toLocaleString('uk-UA')}</p>
						</div>
					)}
				</div>
			</div>
		</section>
	);
};

export default DealPage;
