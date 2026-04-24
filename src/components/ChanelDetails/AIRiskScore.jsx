const AIRiskScore = ({ health, loading }) => {
	if (loading) {
		return (
			<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon px-4 pt-4 pb-3 w-full'>
				<p className='text-gray-400 text-xs'>TgSell Скор</p>
				<div className='flex justify-center py-6'>
					<div className='w-32 h-16 rounded-t-full bg-gray-100 dark:bg-card-inner animate-pulse' />
				</div>
			</div>
		);
	}

	if (!health) {
		return (
			<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon px-4 pt-4 pb-3 w-full'>
				<p className='text-gray-400 text-xs'>TgSell Скор</p>
				<p className='text-gray-500 text-center py-8 text-xs'>Немає даних</p>
			</div>
		);
	}

	const score = health.health_score ?? 0;
	const color = score >= 70 ? '#10B981' : score >= 40 ? '#F59E0B' : '#EF4444';

	// Semi-circular gauge
	const cx = 80, cy = 65, r = 55;
	const bgPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
	const scoreAngle = (score / 100) * Math.PI;
	const endX = cx - r * Math.cos(scoreAngle);
	const endY = cy - r * Math.sin(scoreAngle);
	// Gauge is always ≤ 180°, so large-arc is always 0; sweep=1 draws the upper arc
	const scorePath = score > 0
		? `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${endX} ${endY}`
		: '';

	return (
		<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon px-4 pt-4 pb-3 w-full'>
				<p className='text-gray-400 text-xs mb-1'>TgSell Скор</p>
			<div className='flex flex-col items-center'>
				<svg width='160' height='85' viewBox='0 0 160 85'>
					{/* Background arc */}
					<path d={bgPath} fill='none' stroke='#1A3A2A' strokeWidth='10' strokeLinecap='round' />
					{/* Colored gradient arc */}
					<defs>
						<linearGradient id='gaugeGrad' x1='0%' y1='0%' x2='100%' y2='0%'>
							<stop offset='0%' stopColor='#EF4444' />
							<stop offset='50%' stopColor='#F59E0B' />
							<stop offset='100%' stopColor='#10B981' />
						</linearGradient>
					</defs>
					{scorePath && (
						<path d={scorePath} fill='none' stroke='url(#gaugeGrad)' strokeWidth='10' strokeLinecap='round' />
					)}
					{/* Needle indicator */}
					{score > 0 && (
						<circle cx={endX} cy={endY} r='5' fill={color} stroke='#080E0E' strokeWidth='2' />
					)}
				</svg>
				<div className='text-center -mt-5'>
					<p className='text-gray-500 dark:text-gray-400 text-[10px]'>TgSell</p>
					<p className='font-extrabold text-2xl leading-tight'>
						<span style={{ color }}>{score}</span>
						<span className='text-gray-500 text-sm font-normal'>/100</span>
					</p>
				</div>
			</div>
		</div>
	);
};

export default AIRiskScore;
