import ReactApexChart from 'react-apexcharts';

const ER = ({ stats = [], current }) => {
	const hasData = stats.length > 0;
	const dataPoints = hasData ? stats.map(s => s.er || 0) : [];
	const categories = hasData ? stats.map(s => s.date?.split('T')[0] || '') : [];

	const chartData = hasData
		? {
				options: {
					dataLabels: { enabled: false },
					stroke: { curve: 'smooth', width: 3 },
					chart: { toolbar: { show: false } },
					xaxis: {
						categories,
						labels: { show: false },
						axisTicks: { show: false },
						axisBorder: { show: false },
					},
					yaxis: {
						max: Math.max(...dataPoints),
						labels: { show: false },
						axisTicks: { show: false },
						axisBorder: { show: false },
					},
					grid: { show: false },
					legend: { show: false },
					colors: ['#009366'],
					fill: {
						colors: ['#009366'],
						type: 'gradient',
						gradient: { opacityFrom: 0.65, opacityTo: 0.5 },
					},
				},
				series: [{ name: 'Рівень залученості', data: dataPoints }],
		  }
		: null;

	const formatted = current != null ? `${current.toFixed(1)}%` : '—';

	return (
		<div className='bg-white rounded-2xl border border-gray-100 shadow-sm px-5 pt-5 w-full'>
			<div className='flex items-center justify-between mb-1'>
				<div>
					<p className='text-gray-400 text-xs'>Рівень залученості</p>
					<p className='font-bold text-xl text-gray-900'>{formatted}</p>
				</div>
			</div>
			{chartData ? (
				<ReactApexChart
					options={chartData.options}
					series={chartData.series}
					type='area'
					height={200}
					width='100%'
				/>
			) : (
				<p className='text-gray-400 text-center py-10'>Немає даних для графіку</p>
			)}
		</div>
	);
};

export default ER;
