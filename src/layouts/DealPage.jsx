import DealChat from '../components/DealChat/DealChat';
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Handshake, DollarSign, Send, CreditCard, CheckCircle2, Check } from 'lucide-react';
import { dealsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import TransferChecklist from '../components/Deal/TransferChecklist';

const STEPS = [
	{ key: 'created',         label: 'Готовність', LIcon: Handshake,    preset: 'blue'   },
	{ key: 'payment_pending', label: 'Оплата',     LIcon: DollarSign,   preset: 'gold'   },
	{ key: 'paid',            label: 'Передача',    LIcon: Send,         preset: 'purple' },
	{ key: 'awaiting_payout', label: 'Виплата',     LIcon: CreditCard,   preset: 'cyan'   },
	{ key: 'completed',       label: 'Завершено',   LIcon: CheckCircle2, preset: 'green'  },
];

const STATUS_META = {
	created: { stepIndex: 0 },
	payment_pending: { stepIndex: 1 },
	paid: { stepIndex: 2 },
	channel_transferring: { stepIndex: 2 },
	awaiting_payout: { stepIndex: 3 },
	payout_in_progress: { stepIndex: 3 },
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
				const IconCmp = step.LIcon;
				return (
					<div key={step.key} className='flex items-center flex-1 min-w-0 last:flex-none'>
						<div className='flex flex-col items-center min-w-0 w-full'>
							<div className={`w-8 h-8 sm:w-10 sm:h-10 rounded-full flex items-center justify-center transition-all duration-500 flex-shrink-0 ${
								done   ? 'shadow-md' :
								active ? 'scale-110 shadow-lg' :
								'bg-gray-100 dark:bg-card-inner'
							}`} style={done ? {background:'linear-gradient(145deg,#10b981,#059669)',boxShadow:'0 4px 14px rgba(16,185,129,0.5)'} : active ? {background:'linear-gradient(145deg,#38bdf8,#0ea5e9)',boxShadow:'0 4px 14px rgba(56,189,248,0.5)'} : {}}>
								{done
									? <Check size={18} color='#fff' strokeWidth={2.5} />
									: <IconCmp size={18} color={active ? '#fff' : '#9CA3AF'} strokeWidth={1.8} />
								}
							</div>
							<span className={`text-[10px] sm:text-xs mt-1.5 font-medium text-center leading-tight break-words px-0.5 ${
								active ? 'text-sky-400' : done ? 'text-emerald-500' : 'text-gray-400'
							}`}>
								{step.label}
							</span>
						</div>
						{i < STEPS.length - 1 && (
							<div className={`flex-1 h-0.5 mx-1 sm:mx-2 mt-[-14px] sm:mt-[-16px] rounded-full transition-all duration-500 ${
								i < currentIdx ? 'bg-green-400' : 'bg-gray-200'
							}`} />
						)}
					</div>
				);
			})}
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
	const [checklist, setChecklist] = useState(null);
	const [payoutStatus, setPayoutStatus] = useState(null);
	const [notice, setNotice] = useState(null);
	const [refundAddress, setRefundAddress] = useState('');

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

	const handleSubmitRefundAddress = () => {
		if (!refundAddress.trim()) return;
		handleAction(async () => {
			await dealsAPI.setOverpayRefundAddress(id, refundAddress.trim());
			setNotice('Адресу для повернення переплати збережено.');
			setTimeout(() => setNotice(null), 8000);
		});
	};

	const handleConfirmReady = () => handleAction(() => dealsAPI.confirmReady(id));
	const handleConfirmTransfer = () => handleAction(() => dealsAPI.confirmChannelTransfer(id));
	const handleSubmitWallet = () => {
		if (!walletAddress.trim()) return;
		handleAction(async () => {
			const res = await dealsAPI.setSellerWallet(id, walletAddress.trim());
			if (res.status === 202) {
				setNotice('Виплату поставлено в чергу. Статус оновиться після підтвердження мережею.');
				setTimeout(() => setNotice(null), 8000);
			}
		});
	};

	// Poll payout progress while the payout is being processed (worker + receipt).
	useEffect(() => {
		if (!deal || deal.status !== 'payout_in_progress') { setPayoutStatus(null); return; }
		let stop = false;
		const tick = async () => {
			try {
				const { data } = await dealsAPI.payoutStatus(id);
				if (stop) return;
				setPayoutStatus(data);
				if (data.deal_status !== 'payout_in_progress') refreshDeal();
			} catch { /* ignore */ }
		};
		tick();
		const t = setInterval(tick, 5000);
		return () => { stop = true; clearInterval(t); };
	}, [deal?.status, id]);
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
	const isTransferStatus = ['paid', 'channel_transferring'].includes(deal.status);
	const mySideKey = isBuyer ? 'buyer' : isSeller ? 'seller' : null;
	const mySideChecklist = checklist && mySideKey ? checklist[mySideKey] : null;
	const myChecklistOpen = mySideChecklist ? mySideChecklist.required_total - mySideChecklist.required_done : null;
	const showError = (msg) => {
		setError(msg);
		setTimeout(() => setError(null), 5000);
	};

	return (
		<section className='my-28 max-w-3xl mx-auto px-4'>

			{/* Error toast */}
			{error && (
				<div className='bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-2xl mb-6 text-sm animate-fadeIn'>
					{error}
				</div>
			)}

			{/* Hero header */}
			<div className='bg-gradient-to-br from-[#3498db] to-[#1a6fb5] rounded-2xl p-6 mb-6 text-white shadow-lg overflow-hidden relative'>
				<div className='absolute top-0 right-0 w-40 h-40 bg-white/5 rounded-full -mr-10 -mt-10' />
				<div className='absolute bottom-0 left-0 w-24 h-24 bg-white/5 rounded-full -ml-6 -mb-6' />
				<div className='relative flex items-center gap-5'>
					{deal.channel_avatar_url ? (
						<img
							src={deal.channel_avatar_url}
							alt={deal.channel_name}
							className='w-16 h-16 rounded-2xl object-cover border-2 border-white/20 shadow-md flex-shrink-0'
						/>
					) : (
						<div className='w-16 h-16 rounded-2xl bg-white/15 backdrop-blur-sm border-2 border-white/20 flex items-center justify-center flex-shrink-0 shadow-md'>
							<svg className='w-7 h-7 text-white/80' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={1.5}>
								<path strokeLinecap='round' strokeLinejoin='round' d='M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5' />
							</svg>
						</div>
					)}
					<div className='flex-1 min-w-0'>
						<p className='text-blue-200 text-xs font-medium uppercase tracking-wider mb-1'>
							{isBuyer ? 'Ви купуєте' : 'Ви продаєте'}
						</p>
						<h1 className='text-xl md:text-2xl font-bold truncate'>
							{deal.channel_name || `Канал #${deal.channel_id}`}
						</h1>
						<p className='text-blue-200 text-sm mt-0.5'>
							{isBuyer ? deal.seller_name || 'Продавець' : deal.buyer_name || 'Покупець'} · {new Date(deal.created_at).toLocaleDateString('uk-UA')}
						</p>
					</div>
					<div className='text-right flex-shrink-0'>
						<p className='text-3xl md:text-4xl font-extrabold tracking-tight'>{deal.amount_usdt}</p>
						<p className='text-blue-200 text-xs font-semibold uppercase tracking-wider mt-0.5'>USDT</p>
					</div>
				</div>
			</div>

			{/* Special statuses */}
			{deal.status === 'disputed' && (
				<div className='bg-amber-50 border border-amber-200 rounded-2xl p-5 mb-6 flex items-center gap-4'>
					<div className='w-10 h-10 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0'>
						<svg className='w-5 h-5 text-amber-600' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
							<path strokeLinecap='round' strokeLinejoin='round' d='M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z' />
						</svg>
					</div>
					<div>
						<p className='font-bold text-amber-800'>Спір</p>
						<p className='text-amber-600 text-sm'>Адміністратор розглядає це питання</p>
					</div>
				</div>
			)}
			{deal.status === 'cancelled' && (
				<div className='bg-gray-50 dark:bg-slate-700/60 border border-gray-200 dark:border-slate-600 rounded-2xl p-5 mb-6 flex items-center gap-4'>
					<div className='w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center flex-shrink-0'>
						<svg className='w-5 h-5 text-gray-500' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
							<path strokeLinecap='round' strokeLinejoin='round' d='M6 18L18 6M6 6l12 12' />
						</svg>
					</div>
					<div>
						<p className='font-bold text-gray-700 dark:text-gray-200'>Угоду скасовано</p>
					</div>
				</div>
			)}

			{/* Step Progress */}
			{!isSpecialStatus && <StepProgress status={deal.status} />}

			{/* Step 1: Confirm Readiness */}
			{deal.status === 'created' && (
				<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-gray-100 dark:border-slate-700 p-6 mb-6'>
					<h3 className='font-bold text-lg mb-2'>Підтвердіть готовність до угоди</h3>
					<p className='text-gray-500 text-sm mb-5'>
						Обидві сторони повинні підтвердити готовність. Після цього покупець зможе оплатити.
					</p>
					<div className='flex gap-3 mb-5'>
						<div className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 transition-all duration-300 ${
							deal.buyer_ready ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50 dark:bg-slate-700'
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
							deal.seller_ready ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50 dark:bg-slate-700'
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
						<div className='bg-blue-50 dark:bg-blue-900/20 text-blue-600 text-sm font-medium px-4 py-3 rounded-xl text-center'>
							Ви підтвердили. Очікуйте іншу сторону
						</div>
					)}
				</div>
			)}

			{/* Partial payment */}
			{['created', 'payment_pending'].includes(deal.status) && deal.received_usdt > 0 && deal.received_usdt < deal.amount_usdt && (
				<div className='bg-orange-50 dark:bg-orange-900/20 border border-orange-200 rounded-2xl p-5 mb-6'>
					<p className='font-semibold text-orange-800 dark:text-orange-200'>
						Отримано {deal.received_usdt} з {deal.amount_usdt} USDT, доплатіть {(Math.round((deal.amount_usdt - deal.received_usdt) * 1e6) / 1e6)} USDT
					</p>
					<p className='text-xs text-orange-700 dark:text-orange-300 mt-1'>
						⚠️ Біржа або гаманець можуть утримати комісію за виведення — надсилайте так, щоб на escrow надійшла повна сума.
					</p>
				</div>
			)}

			{/* Overpayment refund */}
			{deal.overpay_units > 0 && (isBuyer || isSeller) && (
				<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-gray-100 dark:border-slate-700 p-6 mb-6'>
					<h3 className='font-bold text-lg mb-2'>Переплата {deal.overpay_units / 1e6} USDT</h3>
					{deal.overpay_status === 'awaiting_address' && isBuyer && !deal.overpay_refund_address && (
						<>
							<p className='text-gray-500 text-sm mb-3'>
								Переплату буде повернено після виплати продавцю. Вкажіть свою TRON-адресу (TRC-20 USDT). Адресу відправника (біржі) не використовуємо.
							</p>
							<div className='flex gap-2'>
								<input value={refundAddress} onChange={(e) => setRefundAddress(e.target.value)} placeholder='T...'
									className='flex-1 border border-gray-200 dark:border-slate-600 dark:bg-slate-700 rounded-xl px-3 py-2 font-mono text-sm' />
								<button onClick={handleSubmitRefundAddress} disabled={actionLoading}
									className='bg-[#3498db] text-white rounded-xl px-4 py-2 text-sm font-semibold disabled:opacity-50'>Зберегти</button>
							</div>
						</>
					)}
					{deal.overpay_refund_address && (
						<p className='text-sm text-gray-600 dark:text-gray-300 break-all'>Адреса повернення: <span className='font-mono'>{deal.overpay_refund_address}</span></p>
					)}
					<p className='text-sm text-gray-500 mt-2'>
						{{ awaiting_address: deal.overpay_refund_address ? 'Очікує виплати продавцю' : 'Очікує адресу покупця',
							queued: 'Повернення в черзі ⏳', done: 'Повернено ✅', failed: 'Повернення не виконано — адміністратор розбирається' }[deal.overpay_status] || ''}
					</p>
				</div>
			)}

			{/* Step 2: Payment */}
			{deal.status === 'payment_pending' && isBuyer && (
				<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-gray-100 dark:border-slate-700 p-6 mb-6'>
					<h3 className='font-bold text-lg mb-2'>Оплата</h3>
					<p className='text-gray-500 text-sm mb-5'>
						Переведіть <strong className='text-gray-800 dark:text-white'>{deal.amount_usdt} USDT</strong> через мережу <strong className='text-gray-800 dark:text-white'>TRC-20</strong>
					</p>
					<div className='bg-blue-50 dark:bg-blue-900/20 border border-blue-200 rounded-xl p-4 mb-4'>
						<div className='flex justify-between text-sm mb-1'>
							<span className='text-gray-600 dark:text-gray-300'>Вартість каналу:</span>
							<span className='font-semibold text-gray-800 dark:text-white'>{deal.amount_usdt} USDT</span>
						</div>
						<div className='flex justify-between text-sm mb-1'>
							<span className='text-gray-600 dark:text-gray-300'>Комісія сервісу (3%):</span>
							<span className='text-gray-500'>{deal.service_fee} USDT — утримується при виплаті продавцю</span>
						</div>
						<div className='flex justify-between text-sm'>
							<span className='text-gray-600 dark:text-gray-300'>Комісія мережі:</span>
							<span className='text-gray-500'>~1-2 TRX (~0.1-0.2 USDT)</span>
						</div>
					</div>
					<div className='relative bg-gray-50 dark:bg-slate-700/60 border border-gray-200 dark:border-slate-600 p-4 rounded-xl mb-4 group'>
						<p className='font-mono text-sm break-all pr-10 select-all text-gray-700 dark:text-gray-200'>
							{deal.escrow_wallet_address}
						</p>
						<button
							onClick={() => copyToClipboard(deal.escrow_wallet_address)}
							className='absolute top-3 right-3 bg-white border border-gray-200 dark:border-slate-600 rounded-lg px-2.5 py-1.5 text-xs font-medium text-gray-500 hover:text-[#3498db] hover:border-[#3498db] transition-all'
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
				<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-gray-100 dark:border-slate-700 p-6 mb-6'>
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
			{isTransferStatus && (
				<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-gray-100 dark:border-slate-700 p-6 mb-6'>
					<h3 className='font-bold text-lg mb-2'>Передача каналу</h3>
					{isSeller && (
						<p className='text-gray-500 text-sm mb-5'>
							Кошти отримані! Передайте канал через Telegram і відмічайте пункти чек-листа:
							<span className='block text-gray-400 text-xs mt-1'>Settings → Channel → Administrators → Transfer Ownership</span>
						</p>
					)}
					{isBuyer && (
						<p className='text-gray-500 text-sm mb-5'>
							Кошти на рахунку. Перевірте, чи ви отримали права на канал, і відмітьте свої пункти чек-листа.
						</p>
					)}
					<TransferChecklist
						dealId={deal.id}
						dealStatus={deal.status}
						onLoaded={setChecklist}
						onChange={refreshDeal}
						onError={showError}
					/>
					<div className='flex gap-3 mb-5'>
						<div className={`flex-1 flex items-center gap-3 p-4 rounded-xl border-2 transition-all duration-300 ${
							deal.buyer_confirmed_transfer ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50 dark:bg-slate-700'
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
							deal.seller_confirmed_transfer ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-gray-50 dark:bg-slate-700'
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
						<>
						{myChecklistOpen > 0 && (
							<p className='text-xs text-amber-600 dark:text-amber-400 mb-2'>
								Щоб підтвердити, виконайте ще {myChecklistOpen} обов’язков{myChecklistOpen === 1 ? 'ий пункт' : myChecklistOpen < 5 ? 'і пункти' : 'их пунктів'} вашого чек-листа.
							</p>
						)}
						<div className='flex gap-3'>
							<button
								onClick={handleConfirmTransfer}
								disabled={actionLoading || myChecklistOpen > 0}
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
						</>
					) : (
						<div className='bg-blue-50 dark:bg-blue-900/20 text-blue-600 text-sm font-medium px-4 py-3 rounded-xl text-center'>
							Ви підтвердили. Очікуйте іншу сторону
						</div>
					)}
				</div>
			)}

			{/* Step 4: Seller Wallet */}
			{deal.status === 'awaiting_payout' && isSeller && (
				<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-gray-100 dark:border-slate-700 p-6 mb-6'>
					<h3 className='font-bold text-lg mb-2'>Отримання коштів</h3>
					<p className='text-gray-500 text-sm mb-1'>
						Канал успішно передано! Вкажіть вашу USDT (TRC-20) адресу.
					</p>
					<div className='bg-green-50 border border-green-200 rounded-xl p-4 mb-4'>
						<div className='flex justify-between text-sm mb-1'>
							<span className='text-gray-600 dark:text-gray-300'>Вартість каналу:</span>
							<span className='font-semibold text-gray-800 dark:text-white'>{deal.amount_usdt} USDT</span>
						</div>
						<div className='flex justify-between text-sm mb-1'>
							<span className='text-gray-600 dark:text-gray-300'>Комісія сервісу (3%):</span>
							<span className='text-red-500'>−{deal.service_fee} USDT</span>
						</div>
						<div className='border-t border-green-200 mt-2 pt-2 flex justify-between text-sm font-bold'>
							<span className='text-green-700'>До виплати:</span>
							<span className='text-green-700'>{(deal.amount_usdt - deal.service_fee).toFixed(2)} USDT</span>
						</div>
					</div>
					<div className='flex gap-2 mb-3'>
						<input
							type='text'
							value={walletAddress}
							onChange={(e) => setWalletAddress(e.target.value)}
							placeholder='TRC-20 адреса (T...)'
							maxLength={100}
							className='flex-1 border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-3.5 focus:border-[#3498db] focus:ring-2 focus:ring-blue-100 focus:outline-none font-mono text-sm transition-all'
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
			{deal.status === 'payout_in_progress' && (
				<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-cyan-200 dark:border-slate-700 p-6 mb-6'>
					<div className='flex items-center gap-3'>
						<div className='w-10 h-10 rounded-full bg-cyan-50 flex items-center justify-center animate-pulse'>
							<span className='text-xl'>⏳</span>
						</div>
						<div className='min-w-0'>
							<h3 className='font-bold'>Виплата обробляється</h3>
							<p className='text-gray-500 text-sm'>
								{payoutStatus?.last_transfer?.state === 'broadcast'
									? 'Транзакцію відправлено, очікуємо підтвердження мережі TRON…'
									: 'Виплату поставлено в чергу…'}
							</p>
							{payoutStatus?.last_transfer?.tx_hash && (
								<p className='text-gray-400 text-xs mt-1 font-mono break-all'>TX: {payoutStatus.last_transfer.tx_hash}</p>
							)}
						</div>
					</div>
				</div>
			)}
			{notice && (
				<div className='bg-cyan-50 dark:bg-cyan-900/20 text-cyan-700 text-sm font-medium px-4 py-3 rounded-xl text-center mb-6'>{notice}</div>
			)}
			{deal.status === 'awaiting_payout' && isBuyer && (
				<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-gray-100 dark:border-slate-700 p-6 mb-6'>
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
