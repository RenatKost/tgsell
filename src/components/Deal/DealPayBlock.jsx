import { useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { fmtUsdt, rawUsdt } from '../../utils/money';
import { formatCountdown, formatKyivDateTime } from '../../utils/topFunnel';
import '../Services/topGlow.css';

/** Buyer payment card: address, amount, TRC-20, copy, QR, countdown. Display only. */
const DealPayBlock = ({ deal }) => {
	const [nowMs, setNowMs] = useState(() => Date.now());
	const [copied, setCopied] = useState(null); // 'address' | 'amount'

	useEffect(() => {
		const t = setInterval(() => setNowMs(Date.now()), 1000);
		return () => clearInterval(t);
	}, []);

	const address = deal.escrow_wallet_address || '';
	const amount = rawUsdt(deal.amount_usdt);
	const countdown = formatCountdown(deal.payment_deadline_at, nowMs);
	const until = formatKyivDateTime(deal.payment_deadline_at);

	const copy = async (field, value) => {
		if (!value) return;
		try {
			await navigator.clipboard.writeText(String(value));
		} catch { /* ignore */ }
		setCopied(field);
		setTimeout(() => setCopied((cur) => (cur === field ? null : cur)), 2000);
	};

	return (
		<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-lg border border-gray-100 dark:border-slate-700 p-4 sm:p-6 mb-6 lot-top-glow'>
			<p className='text-[11px] font-semibold uppercase tracking-wider text-accent mb-1'>Оплата через гаранта</p>
			<h3 className='font-bold text-lg mb-1 text-gray-900 dark:text-white'>Перекажіть точну суму</h3>
			<p className='text-gray-500 dark:text-gray-400 text-sm mb-5'>
				Мережа <strong className='text-gray-800 dark:text-white'>TRC-20</strong>
				{' · '}
				сума <strong className='text-gray-800 dark:text-white tabular-nums [overflow-wrap:anywhere]'>{amount} USDT</strong>
			</p>

			{countdown && (
				<div className='mb-5 px-4 py-3 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40'>
					<p className='font-semibold text-amber-800 dark:text-amber-200 text-sm'>{countdown}</p>
					{until && (
						<p className='text-xs text-amber-700 dark:text-amber-300 mt-0.5'>Дедлайн: {until} (Kyiv)</p>
					)}
				</div>
			)}

			<div className='flex flex-col sm:flex-row gap-5 items-center sm:items-start'>
				{address ? (
					<div className='bg-white p-3 rounded-xl border border-gray-100 dark:border-slate-600 shrink-0'>
						<QRCodeSVG value={address} size={148} />
					</div>
				) : null}
				<div className='flex-1 min-w-0 w-full'>
					<label className='block text-[11px] font-semibold uppercase tracking-wider text-gray-400 mb-1.5'>Адреса ескроу</label>
					<div className='bg-gray-50 dark:bg-slate-700/60 border border-gray-200 dark:border-slate-600 p-3 rounded-xl flex flex-col sm:flex-row sm:items-center gap-2'>
						<p className='font-mono text-[13px] sm:text-sm break-all [overflow-wrap:anywhere] min-w-0 flex-1 select-all text-gray-700 dark:text-gray-200'>
							{address}
						</p>
						<button
							type='button'
							onClick={() => copy('address', address)}
							className='self-stretch sm:self-auto shrink-0 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-xs font-semibold text-gray-600 dark:text-gray-300 hover:text-accent hover:border-accent transition-all'
						>
							{copied === 'address' ? 'Скопійовано' : 'Копіювати адресу'}
						</button>
					</div>

					<label className='block text-[11px] font-semibold uppercase tracking-wider text-gray-400 mt-4 mb-1.5'>Сума до переказу</label>
					<div className='bg-gray-50 dark:bg-slate-700/60 border border-gray-200 dark:border-slate-600 p-3 rounded-xl flex flex-col sm:flex-row sm:items-center gap-2'>
						<p className='font-mono text-base sm:text-lg font-bold tabular-nums min-w-0 flex-1 text-gray-900 dark:text-white'>
							{amount} <span className='text-sm font-semibold text-accent'>USDT</span>
						</p>
						<button
							type='button'
							onClick={() => copy('amount', amount)}
							className='self-stretch sm:self-auto shrink-0 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-600 rounded-lg px-3 py-2 text-xs font-semibold text-gray-600 dark:text-gray-300 hover:text-accent hover:border-accent transition-all'
						>
							{copied === 'amount' ? 'Скопійовано' : 'Копіювати суму'}
						</button>
					</div>
				</div>
			</div>

			<div className='bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800/40 rounded-xl p-4 mt-5'>
				<div className='flex flex-col sm:flex-row sm:justify-between gap-0.5 text-sm mb-2 sm:mb-1'>
					<span className='text-gray-600 dark:text-gray-300'>Вартість каналу:</span>
					<span className='font-semibold text-gray-800 dark:text-white'>{fmtUsdt(deal.amount_usdt)} USDT</span>
				</div>
				<div className='flex flex-col sm:flex-row sm:justify-between gap-0.5 text-sm mb-2 sm:mb-1'>
					<span className='text-gray-600 dark:text-gray-300'>Комісія сервісу (3%):</span>
					<span className='text-gray-500'>{fmtUsdt(deal.service_fee)} USDT — утримується при виплаті продавцю</span>
				</div>
				<div className='flex flex-col sm:flex-row sm:justify-between gap-0.5 text-sm'>
					<span className='text-gray-600 dark:text-gray-300'>Комісія мережі:</span>
					<span className='text-gray-500'>~1-2 TRX (~0.1-0.2 USDT)</span>
				</div>
			</div>

			<div className='flex items-start gap-2 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800/40 rounded-xl px-4 py-3 mt-4'>
				<span className='text-yellow-500 text-sm mt-0.5'>⚠️</span>
				<div className='text-xs text-yellow-800 dark:text-yellow-200'>
					<p className='font-semibold'>Переказуйте тільки USDT і тільки мережею TRC-20, точною сумою.</p>
					<p className='mt-0.5 text-yellow-700 dark:text-yellow-300'>Інша мережа або інша сума можуть призвести до втрати коштів. Оплата перевіряється автоматично кожні 30 секунд.</p>
				</div>
			</div>
		</div>
	);
};

export default DealPayBlock;
