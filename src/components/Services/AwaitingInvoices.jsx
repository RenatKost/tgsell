import { useEffect, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { fmtNum } from '../../utils/money';
import { formatCountdown, formatKyivDateTime, openInvoices } from '../../utils/topFunnel';
import { btnSecondary } from '../Cabinet/ui';
import { surface } from '../Cabinet/ui';

const STATUS_LIVE = {
	awaiting_payment: 'Очікує оплату',
	active: 'Топ увімкнено',
	paid: 'Оплачено, в черзі',
	cancelled: 'Скасовано (не оплачено)',
	expired: 'Завершено',
};

const copyText = async (text) => {
	try {
		await navigator.clipboard.writeText(text);
		return true;
	} catch {
		try {
			const el = document.createElement('textarea');
			el.value = text;
			el.setAttribute('readonly', '');
			el.style.position = 'fixed';
			el.style.left = '-9999px';
			document.body.appendChild(el);
			el.select();
			const ok = document.execCommand('copy');
			document.body.removeChild(el);
			return ok;
		} catch {
			return false;
		}
	}
};

const InvoiceCard = ({ order, onOpen }) => {
	const [copied, setCopied] = useState(false);
	const [now, setNow] = useState(() => Date.now());
	useEffect(() => {
		const t = setInterval(() => setNow(Date.now()), 30000);
		return () => clearInterval(t);
	}, []);
	const countdown = formatCountdown(order.payment_deadline_at, now);
	const until = formatKyivDateTime(order.payment_deadline_at);
	const addr = order.escrow_wallet_address || '';
	return (
		<div className={`${surface} p-4 sm:p-5 flex flex-col sm:flex-row gap-4 items-start`}>
			{addr && (
				<div className='bg-white p-2 rounded-xl shrink-0 mx-auto sm:mx-0'>
					<QRCodeSVG value={addr} size={112} />
				</div>
			)}
			<div className='min-w-0 flex-1 space-y-1.5'>
				<p className='font-semibold text-gray-900 dark:text-white text-sm'>
					{order.title || 'Топ каталогу'}{order.channel_name ? ` · ${order.channel_name}` : ''}
				</p>
				<p className='text-sm text-gray-600 dark:text-gray-300'>
					Надішліть <b className='tabular-nums'>{fmtNum(order.price_usdt)} USDT</b> ({order.network || 'USDT TRC-20'}) на адресу:
				</p>
				<p className='font-mono text-xs break-all bg-gray-50 dark:bg-slate-900 border border-gray-200 dark:border-card-border rounded-lg px-3 py-2 text-gray-800 dark:text-gray-100'>{addr}</p>
				<div className='flex flex-wrap gap-2 pt-1'>
					<button type='button' className={btnSecondary} onClick={async () => {
						const ok = await copyText(addr);
						if (ok) { setCopied(true); setTimeout(() => setCopied(false), 2000); }
					}}>{copied ? 'Скопійовано' : 'Скопіювати'}</button>
					{onOpen && (
						<button type='button' className={btnSecondary} onClick={() => onOpen(order)}>Відкрити заявку</button>
					)}
				</div>
				<p className='text-xs text-gray-500 dark:text-gray-400'>
					Статус: {order.status_label || STATUS_LIVE[order.status] || order.status}
					{countdown ? ` · ${countdown}` : ''}
					{until ? ` · до ${until} (Київ)` : ''}
				</p>
				<p className='text-xs text-gray-400'>Оплату буде зараховано автоматично протягом кількох хвилин.</p>
			</div>
		</div>
	);
};

/** Cabinet block: open invoices from GET /services/orders/my. */
const AwaitingInvoices = ({ orders, onOpen }) => {
	const items = openInvoices(orders);
	if (!items.length) return null;
	return (
		<section className='mb-5' aria-label='Очікують оплату'>
			<h2 className='text-sm font-bold text-gray-900 dark:text-white mb-3'>Очікують оплату</h2>
			<div className='space-y-3'>
				{items.map((o) => <InvoiceCard key={o.id} order={o} onOpen={onOpen} />)}
			</div>
		</section>
	);
};

export default AwaitingInvoices;
export { InvoiceCard, copyText };
