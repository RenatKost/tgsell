const AdvertisingReach = ({ channel }) => {
	const avgReach = channel?.avg_views;
	// These will be populated once the backend stats collector gathers this data
	const reach12h = channel?.adv_reach_12h;
	const reach24h = channel?.adv_reach_24h;
	const reach48h = channel?.adv_reach_48h;

	const hasAnyData = avgReach || reach12h || reach24h || reach48h;

	if (!hasAnyData) {
		return (
			<div className='bg-white rounded-md shadow-lg px-4 py-4 2xl:w-[425px] w-full'>
				<h4 className='font-bold text-lg mb-4'>Рекламне охоплення</h4>
				<p className='text-gray-400 text-center py-6'>Дані поки відсутні</p>
			</div>
		);
	}

	return (
		<div className='bg-white rounded-md shadow-lg px-4 py-4 2xl:w-[425px] w-full'>
			<div className='flex items-start justify-between mb-5'>
				<p className='font-bold text-lg'>
					{avgReach?.toLocaleString('uk-UA') || '—'}
				</p>
				<h4 className='font-bold text-end text-lg'>Рекламне охоплення</h4>
			</div>
			{reach12h != null && (
				<div className='grid grid-cols-2 w-[75%] mx-auto mb-2 bg-pink-500 bg-opacity-30 p-2 rounded-md'>
					<p className='font-bold'>{reach12h.toLocaleString('uk-UA')}</p>
					<p>за 12 годин</p>
				</div>
			)}
			{reach24h != null && (
				<div className='grid grid-cols-2 w-[75%] mx-auto mb-2 bg-green-500 bg-opacity-30 p-2 rounded-md'>
					<p className='font-bold'>{reach24h.toLocaleString('uk-UA')}</p>
					<p>за 24 годин</p>
				</div>
			)}
			{reach48h != null && (
				<div className='grid grid-cols-2 w-[75%] mx-auto mb-2 bg-orange-500 bg-opacity-30 p-2 rounded-md'>
					<p className='font-bold'>{reach48h.toLocaleString('uk-UA')}</p>
					<p>за 48 годин</p>
				</div>
			)}
		</div>
	);
};

export default AdvertisingReach;
