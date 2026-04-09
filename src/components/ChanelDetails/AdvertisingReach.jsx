const AdvertisingReach = ({ channel }) => {
	const avgReach = channel?.avg_views;
	const reach12h = channel?.adv_reach_12h;
	const reach24h = channel?.adv_reach_24h;
	const reach48h = channel?.adv_reach_48h;

	const hasAnyData = avgReach || reach12h || reach24h || reach48h;

	if (!hasAnyData) {
		return (
			<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm px-4 py-4 w-full'>
				<p className='text-gray-400 text-xs mb-1'>Рекламне охоплення</p>
				<p className='text-gray-300 text-center py-6 text-xs'>Дані поки відсутні</p>
			</div>
		);
	}

	const rows = [
		{ value: reach12h, label: 'за 12 годин', bg: 'bg-pink-50 dark:bg-pink-900/20', text: 'text-pink-600 dark:text-pink-400' },
		{ value: reach24h, label: 'за 24 годин', bg: 'bg-emerald-50 dark:bg-emerald-900/20', text: 'text-emerald-600 dark:text-emerald-400' },
		{ value: reach48h, label: 'за 48 годин', bg: 'bg-orange-50 dark:bg-orange-900/20', text: 'text-orange-600 dark:text-orange-400' },
	];

	return (
		<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm px-4 py-4 w-full'>
			<p className='text-gray-400 text-xs mb-0.5'>Рекламне охоплення</p>
			<p className='font-bold text-lg text-gray-900 dark:text-white mb-3'>
				{avgReach?.toLocaleString('uk-UA') || '—'}
			</p>
			<div className='space-y-2'>
				{rows.map((r, idx) => r.value != null && (
					<div key={idx} className={`flex items-center justify-between ${r.bg} rounded-xl px-4 py-3`}>
						<p className={`font-bold ${r.text}`}>{r.value.toLocaleString('uk-UA')}</p>
						<p className='text-gray-500 dark:text-gray-400 text-sm'>{r.label}</p>
					</div>
				))}
			</div>
		</div>
	);
};

export default AdvertisingReach;
