// Shared presentational pieces for the personal cabinet (/cabinet).
// Pure UI: no data fetching, no deal logic — only labels, badges and layout.
import { NavLink } from 'react-router-dom';

// Surfaces & controls aligned with the site palette (page/card/accent tokens),
// with light-theme fallbacks. All interactive controls are at least 44px tall.
export const surface = 'bg-white dark:bg-card border border-gray-200 dark:border-card-border rounded-2xl';
export const inner = 'bg-gray-50 dark:bg-card-inner border border-gray-100 dark:border-card-border/60 rounded-xl';
export const btnPrimary = 'inline-flex items-center justify-center gap-2 min-h-[44px] px-5 rounded-xl bg-accent text-black font-semibold text-sm hover:brightness-110 active:brightness-95 transition-all whitespace-nowrap';
export const btnSecondary = 'inline-flex items-center justify-center gap-2 min-h-[44px] px-4 rounded-xl border border-gray-200 dark:border-card-border bg-white dark:bg-card-inner text-gray-700 dark:text-gray-200 font-semibold text-sm hover:border-accent hover:text-gray-900 dark:hover:text-accent transition-all whitespace-nowrap';
export const btnDanger = 'inline-flex items-center justify-center gap-2 min-h-[44px] min-w-[44px] px-3 rounded-xl border border-red-200 dark:border-red-900/60 text-red-600 dark:text-red-400 font-semibold text-sm hover:bg-red-50 dark:hover:bg-red-900/20 transition-all';

const TONES = {
	green: 'bg-green-100 text-green-800 ring-green-600/20 dark:bg-green-500/10 dark:text-green-300 dark:ring-green-400/30',
	yellow: 'bg-yellow-100 text-yellow-800 ring-yellow-600/20 dark:bg-yellow-500/10 dark:text-yellow-300 dark:ring-yellow-400/30',
	red: 'bg-red-100 text-red-800 ring-red-600/20 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-400/30',
	blue: 'bg-blue-100 text-blue-800 ring-blue-600/20 dark:bg-blue-500/10 dark:text-blue-300 dark:ring-blue-400/30',
	indigo: 'bg-indigo-100 text-indigo-800 ring-indigo-600/20 dark:bg-indigo-500/10 dark:text-indigo-300 dark:ring-indigo-400/30',
	orange: 'bg-orange-100 text-orange-800 ring-orange-600/20 dark:bg-orange-500/10 dark:text-orange-300 dark:ring-orange-400/30',
	gray: 'bg-gray-100 text-gray-700 ring-gray-500/20 dark:bg-white/5 dark:text-gray-300 dark:ring-white/15',
};
const DOTS = { green: 'bg-green-500', yellow: 'bg-yellow-500', red: 'bg-red-500', blue: 'bg-blue-500', indigo: 'bg-indigo-500', orange: 'bg-orange-500', gray: 'bg-gray-400' };

export const Badge = ({ tone = 'gray', children, dot = true, className = '' }) => (
	<span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset whitespace-nowrap ${TONES[tone] || TONES.gray} ${className}`}>
		{dot && <span className={`w-1.5 h-1.5 rounded-full ${DOTS[tone] || DOTS.gray}`} />}
		{children}
	</span>
);

export const LISTING_STATUS = {
	pending: { text: 'На модерації', tone: 'yellow' },
	approved: { text: 'Опубліковано', tone: 'green' },
	rejected: { text: 'Відхилено', tone: 'red' },
	sold: { text: 'Продано', tone: 'gray' },
};

export const DEAL_STATUS = {
	created: { text: 'Підтвердження готовності', tone: 'yellow' },
	payment_pending: { text: 'Очікує оплати', tone: 'yellow' },
	paid: { text: 'Оплачено', tone: 'blue' },
	channel_transferring: { text: 'Передача каналу', tone: 'indigo' },
	awaiting_payout: { text: 'Очікує виплати', tone: 'blue' },
	payout_in_progress: { text: 'Виплата в процесі', tone: 'blue' },
	completed: { text: 'Завершено', tone: 'green' },
	disputed: { text: 'Спір', tone: 'red' },
	cancelled: { text: 'Скасовано', tone: 'gray' },
};

export const AUCTION_STATUS = {
	active: { text: 'Активний', tone: 'green' },
	scheduled: { text: 'Запланований', tone: 'yellow' },
	ended: { text: 'Завершений', tone: 'blue' },
	cancelled: { text: 'Скасований', tone: 'gray' },
};

// Next step hint for a deal card: which button label to show. It only links to
// the deal page, where the actual action happens.
export const dealNextStep = (deal, isBuyer) => {
	const mineConfirmed = isBuyer ? deal.buyer_confirmed_transfer : deal.seller_confirmed_transfer;
	switch (deal.status) {
		case 'created':
			return { text: 'Підтвердити готовність', primary: true };
		case 'payment_pending':
			return isBuyer ? { text: 'Оплатити', primary: true } : { text: 'Очікуємо оплату', primary: false };
		case 'paid':
		case 'channel_transferring':
			if (mineConfirmed) return { text: 'Очікуємо іншу сторону', primary: false };
			return isBuyer ? { text: 'Підтвердити отримання', primary: true } : { text: 'Підтвердити передачу', primary: true };
		case 'awaiting_payout':
		case 'payout_in_progress':
			return { text: 'Статус виплати', primary: false };
		case 'disputed':
			return { text: 'Перейти до спору', primary: true };
		default:
			return { text: 'Деталі угоди', primary: false };
	}
};

export const Spinner = () => (
	<div className='flex justify-center py-20' role='status' aria-label='Завантаження'>
		<div className='animate-spin rounded-full h-10 w-10 border-2 border-gray-200 dark:border-card-border border-t-accent dark:border-t-accent' />
	</div>
);

export const EmptyState = ({ icon, title, text, action }) => (
	<div className='text-center px-5 py-12 sm:py-16 rounded-2xl border border-dashed border-gray-300 dark:border-card-border bg-white/60 dark:bg-card/60'>
		<div className='text-4xl sm:text-5xl mb-4' aria-hidden='true'>{icon}</div>
		<p className='text-base sm:text-lg font-semibold text-gray-800 dark:text-white mb-2'>{title}</p>
		{text && <p className='text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-md mx-auto leading-relaxed'>{text}</p>}
		{action}
	</div>
);

export const ErrorState = ({ onRetry }) => (
	<div className='text-center px-5 py-12 rounded-2xl border border-red-200 dark:border-red-900/50 bg-red-50/60 dark:bg-red-900/10'>
		<div className='text-4xl mb-4' aria-hidden='true'>⚠️</div>
		<p className='text-base sm:text-lg font-semibold text-gray-800 dark:text-white mb-2'>Не вдалося завантажити дані</p>
		<p className='text-sm text-gray-500 dark:text-gray-400 mb-6'>Перевірте з’єднання та спробуйте ще раз.</p>
		<button type='button' onClick={onRetry} className={btnSecondary}>Спробувати ще раз</button>
	</div>
);

export const LinkButton = ({ to, primary = true, children, className = '' }) => (
	<NavLink to={to} className={`${primary ? btnPrimary : btnSecondary} ${className}`}>{children}</NavLink>
);

// Filter chip row: wraps, every chip is a 44px tap target.
export const FilterChips = ({ items, active, onChange, count }) => (
	<div className='flex flex-wrap gap-2 mb-5' role='group' aria-label='Фільтр'>
		{items.map(f => {
			const on = f === active;
			return (
				<button
					key={f.text}
					type='button'
					aria-pressed={on}
					onClick={() => onChange(f)}
					className={`inline-flex items-center gap-2 min-h-[44px] px-4 rounded-full text-sm font-medium transition-all border ${
						on
							? 'bg-accent/15 border-accent text-gray-900 dark:text-accent'
							: 'bg-white dark:bg-card border-gray-200 dark:border-card-border text-gray-600 dark:text-gray-300 hover:border-accent'
					}`}
				>
					<span className={`w-2 h-2 rounded-full ${f.dot}`} />
					{f.text}
					<span className={`text-xs tabular-nums ${on ? 'opacity-90' : 'text-gray-400'}`}>{count(f)}</span>
				</button>
			);
		})}
	</div>
);
