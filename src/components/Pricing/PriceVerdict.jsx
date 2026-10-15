// Task 21: market price estimate badge + details block.
const VERDICTS = {
	cheaper: { label: 'Дешевше ринку', cls: 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/40' },
	fair: { label: 'Ринкова ціна', cls: 'bg-sky-50 dark:bg-sky-900/20 text-sky-600 dark:text-sky-400 border-sky-200 dark:border-sky-800/40' },
	expensive: { label: 'Дорожче ринку', cls: 'bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-800/40' },
	inflated: { label: 'Можлива накрутка', cls: 'bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800/40' },
};

const fmt = (v) => (v == null ? '—' : Math.round(v).toLocaleString('uk-UA'));
const fmtUnit = (v) => {
	if (v == null) return '—';
	if (v >= 1) return v.toFixed(2);
	if (v >= 0.01) return v.toFixed(3);
	return v.toFixed(4);
};

export const PriceVerdictBadge = ({ channel, className = '' }) => {
	const v = VERDICTS[channel?.price_verdict];
	if (!v || channel.bundle_id) return null;
	const title = channel.fair_price_range
		? `Справедлива ціна: ${fmt(channel.fair_price_range[0])}–${fmt(channel.fair_price_range[1])} USDT`
		: undefined;
	return (
		<span title={title} className={`inline-flex items-center max-w-full truncate text-[11px] font-semibold px-2.5 py-1 rounded-lg border ${v.cls} ${className}`}>
			{v.label}
		</span>
	);
};

export const PriceEstimate = ({ channel }) => {
	if (!channel || channel.bundle_id) return null;
	const v = VERDICTS[channel.price_verdict];
	return (
		<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon p-4 min-w-0'>
			<div className='flex flex-wrap items-center gap-2 mb-3'>
				<h4 className='font-semibold text-gray-900 dark:text-white text-xs uppercase tracking-wider'>Оцінка ціни</h4>
				{v && <PriceVerdictBadge channel={channel} className='ml-auto' />}
			</div>
			<div className='grid grid-cols-2 gap-2'>
				<div className='bg-gray-50 dark:bg-card-inner rounded-lg p-2 min-w-0'>
					<p className='text-gray-400 text-[10px]'>Ціна за підписника</p>
					<p className='font-bold text-sm text-gray-800 dark:text-gray-100 truncate'>{channel.price_per_sub != null ? `${fmtUnit(channel.price_per_sub)} USDT` : '—'}</p>
				</div>
				<div className='bg-gray-50 dark:bg-card-inner rounded-lg p-2 min-w-0'>
					<p className='text-gray-400 text-[10px]'>Ціна за перегляд</p>
					<p className='font-bold text-sm text-gray-800 dark:text-gray-100 truncate'>{channel.price_per_view != null ? `${fmtUnit(channel.price_per_view)} USDT` : '—'}</p>
				</div>
			</div>
			{channel.fair_price_range ? (
				<>
					<p className='text-xs text-gray-600 dark:text-gray-300 mt-3 break-words'>
						Справедливий діапазон: <span className='font-semibold'>{fmt(channel.fair_price_range[0])}–{fmt(channel.fair_price_range[1])} USDT</span>
					</p>
					<p className='text-[10px] text-gray-400 mt-1 leading-snug'>
						Медіана двох оцінок (ціна за підписника та за свіжий перегляд) за ринковими цінами в категорії, ±25%.
					</p>
				</>
			) : channel.price_verdict === 'inflated' ? (
				<p className='text-[11px] text-amber-600 dark:text-amber-400 mt-3'>
					Співвідношення переглядів і підписників нетипове — можлива накрутка. Ціну не оцінюємо.
				</p>
			) : v ? (
				<p className='text-[11px] text-gray-400 mt-3'>
					Оцінка за загальною медіаною ринку: для цієї категорії замало даних, тому точний діапазон не показуємо.
				</p>
			) : channel.price_per_sub != null && !channel.is_closed ? (
				<p className='text-[11px] text-gray-400 mt-3'>
					Ціна надто відрізняється від ринкової оцінки (понад 3 рази) — оцінка ненадійна, тому не показуємо її.
				</p>
			) : (
				<p className='text-[11px] text-gray-400 mt-3'>
					Недостатньо даних для оцінки{channel.is_closed ? ' — закритий канал' : ''}.
				</p>
			)}
		</div>
	);
};
