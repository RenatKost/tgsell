import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { dealsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';

const STATUS_LABELS = {
	created: { text: 'Очікує оплати', color: 'bg-yellow-500' },
	payment_pending: { text: 'Очікує оплати', color: 'bg-yellow-500' },
	paid: { text: 'Оплачено — передайте канал', color: 'bg-blue-500' },
	channel_transferring: { text: 'Передача каналу', color: 'bg-blue-500' },
	completed: { text: 'Завершено', color: 'bg-green-500' },
	disputed: { text: 'Спір', color: 'bg-red-500' },
	cancelled: { text: 'Скасовано', color: 'bg-gray-500' },
};

const DealChat = ({ dealId, userId }) => {
	const [messages, setMessages] = useState([]);
	const [newMessage, setNewMessage] = useState('');
	const [sending, setSending] = useState(false);
	const messagesEndRef = useRef(null);

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
		} catch (err) {
			// silent
		} finally {
			setSending(false);
		}
	};

	return (
		<div className='bg-white rounded-md shadow-lg p-6 mb-6'>
			<h3 className='font-bold text-lg mb-4'>💬 Чат угоди</h3>
			<div className='bg-gray-50 rounded-md p-4 h-80 overflow-y-auto mb-4'>
				{messages.length === 0 && (
					<p className='text-gray-400 text-center mt-20 text-sm'>
						Повідомлень ще немає. Напишіть першими!
					</p>
				)}
				{messages.map((msg) => {
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

	useEffect(() => {
		const fetchDeal = async () => {
			try {
				const { data } = await dealsAPI.getById(id);
				setDeal(data);
			} catch (err) {
				setError('Не вдалося завантажити угоду');
			} finally {
				setLoading(false);
			}
		};
		fetchDeal();
		// Poll for updates every 30s
		const interval = setInterval(fetchDeal, 30000);
		return () => clearInterval(interval);
	}, [id]);

	const handleConfirmTransfer = async () => {
		try {
			await dealsAPI.confirmTransfer(id);
			const { data } = await dealsAPI.getById(id);
			setDeal(data);
		} catch (err) {
			setError('Помилка підтвердження');
		}
	};

	const handleDispute = async () => {
		const reason = prompt('Опишіть причину спору:');
		if (!reason) return;
		try {
			await dealsAPI.dispute(id, reason);
			const { data } = await dealsAPI.getById(id);
			setDeal(data);
		} catch (err) {
			setError('Помилка відкриття спору');
		}
	};

	if (loading) {
		return (
			<div className='my-28 flex justify-center'>
				<div className='animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#3498db]'></div>
			</div>
		);
	}

	if (error || !deal) {
		return (
			<div className='my-28 text-center'>
				<p className='text-red-500 text-xl'>{error || 'Угоду не знайдено'}</p>
			</div>
		);
	}

	const statusInfo = STATUS_LABELS[deal.status] || STATUS_LABELS.created;
	const isBuyer = user?.id === deal.buyer_id;
	const isSeller = user?.id === deal.seller_id;

	return (
		<section className='my-28 max-w-3xl mx-auto'>
			<h1 className='text-3xl font-bold text-[#3498db] mb-8'>
				Угода #{deal.id}
			</h1>

			{/* Status Badge */}
			<div className={`${statusInfo.color} text-white text-center py-3 rounded-md mb-8 font-bold text-lg`}>
				{statusInfo.text}
			</div>

			{/* Deal Info Card */}
			<div className='bg-white rounded-md shadow-lg p-6 mb-6'>
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
						<p className='font-bold'>{deal.buyer_name || 'Ви'}</p>
					</div>
					<div>
						<p className='text-gray-500 text-sm'>Продавець</p>
						<p className='font-bold'>{deal.seller_name || 'Продавець'}</p>
					</div>
				</div>
			</div>

			{/* Payment Info */}
			{(deal.status === 'created' || deal.status === 'payment_pending') && isBuyer && (
				<div className='bg-white rounded-md shadow-lg p-6 mb-6'>
					<h3 className='font-bold text-lg mb-4'>💰 Оплата</h3>
					<p className='mb-2'>Переведіть <strong>{deal.amount_usdt} USDT (TRC-20)</strong> на адресу:</p>
					<div className='bg-gray-100 p-4 rounded-md font-mono text-sm break-all select-all mb-4'>
						{deal.escrow_wallet_address}
					</div>
					<p className='text-gray-500 text-sm'>
						⏳ Оплата автоматично перевіряється кожні 30 секунд. Після надходження коштів статус оновиться.
					</p>
					<p className='text-red-500 text-sm mt-2'>
						⚠️ Переводьте тільки USDT через мережу TRC-20!
					</p>
				</div>
			)}

			{/* Channel Transfer */}
			{deal.status === 'paid' && isSeller && (
				<div className='bg-white rounded-md shadow-lg p-6 mb-6'>
					<h3 className='font-bold text-lg mb-4'>📤 Передача каналу</h3>
					<p className='mb-4'>
						Кошти отримані! Передайте права власності на канал покупцю через Telegram
						(Settings → Channel → Administrators → Transfer Ownership).
					</p>
					<p className='text-gray-500 text-sm'>
						Після передачі покупець підтвердить отримання, і кошти будуть переведені вам.
					</p>
				</div>
			)}

			{deal.status === 'paid' && isBuyer && (
				<div className='bg-white rounded-md shadow-lg p-6 mb-6'>
					<h3 className='font-bold text-lg mb-4'>📥 Отримання каналу</h3>
					<p className='mb-4'>
						Продавець повинен передати вам канал. Після отримання натисніть кнопку підтвердження.
					</p>
					<button
						onClick={handleConfirmTransfer}
						className='font-bold bg-[#27ae60] text-white py-3 px-8 rounded-md shadow-lg hover:shadow-green-400 duration-500 mr-4'
					>
						✅ Підтвердити отримання
					</button>
					<button
						onClick={handleDispute}
						className='font-bold bg-red-500 text-white py-3 px-8 rounded-md shadow-lg hover:shadow-red-400 duration-500'
					>
						⚠️ Відкрити спір
					</button>
				</div>
			)}

			{/* Completed */}
			{deal.status === 'completed' && (
				<div className='bg-green-50 rounded-md shadow-lg p-6 mb-6 text-center'>
					<h3 className='font-bold text-lg mb-2 text-green-600'>✅ Угода завершена!</h3>
					<p>Кошти переведені продавцю. Дякуємо за використання TgSell!</p>
				</div>
			)}

			{/* Telegram Deal Group */}
			{deal.deal_group_chat_id && (
				<div className='bg-white rounded-md shadow-lg p-6 mb-6 text-center'>
					<h3 className='font-bold text-lg mb-4'>Чат в Telegram</h3>
					<p className='text-gray-500 mb-4'>Перейдіть до групи угоди в Telegram для спілкування з іншою стороною та ботом.</p>
					<a
						href={`https://t.me/c/${deal.deal_group_chat_id}`}
						target='_blank'
						rel='noopener noreferrer'
						className='font-bold bg-[#3498db] text-white py-3 px-8 rounded-md shadow-md hover:shadow-[#3498db] duration-500 inline-block'
					>
						Відкрити в Telegram
					</a>
				</div>
			)}

			{/* Deal Chat */}
			<DealChat dealId={deal.id} userId={user?.id} />

			{/* Timeline */}
			<div className='bg-white rounded-md shadow-lg p-6'>
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
