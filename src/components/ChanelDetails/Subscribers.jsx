import ReactApexChart from 'react-apexcharts';

const Subscribers = ({ stats = [], current }) => {
	const hasData = stats.length > 0;
	const dataPoints = hasData ? stats.map(s => s.subscribers) : [];
	const categories = hasData ? stats.map(s => s.date?.split('T')[0] || '') : [];

	const minVal = Math.min(...dataPoints);
	const maxVal = Math.max(...dataPoints);
	const range = maxVal - minVal || maxVal * 0.1 || 1;
	const yMin = Math.max(0, Math.floor(minVal - range * 0.15));
	const yMax = Math.ceil(maxVal + range * 0.1);

	const chartData = hasData
		? {
				options: {
					dataLabels: { enabled: false },
					stroke: { curve: 'smooth', width: 2.5 },
					chart: { toolbar: { show: false }, sparkline: { enabled: false } },
					xaxis: {
						categories,
						labels: { show: false },
						axisTicks: { show: false },
						axisBorder: { show: false },
					},
					yaxis: {
						min: yMin,
						max: yMax,
						labels: { show: false },
						axisTicks: { show: false },
						axisBorder: { show: false },
					},
					grid: { show: true, borderColor: '#f3f4f6', strokeDashArray: 4, xaxis: { lines: { show: false } } },
					legend: { show: false },
					tooltip: { y: { formatter: v => v?.toLocaleString('uk-UA') } },
					colors: ['#27ACD2'],
					fill: {
						colors: ['#27ACD2'],
						type: 'gradient',
						gradient: { opacityFrom: 0.5, opacityTo: 0.05, shadeIntensity: 1 },
					},
				},
				series: [{ name: 'Підписники', data: dataPoints }],
		  }
		: null;

	const formatted = (current || dataPoints[dataPoints.length - 1])?.toLocaleString('uk-UA') || '—';

	return (
		<div className='bg-white rounded-2xl border border-gray-100 shadow-sm px-5 pt-5 w-full'>
			<div className='flex items-center justify-between mb-1'>
				<div>
					<p className='text-gray-400 text-xs'>Підписники</p>
					<p className='font-bold text-xl text-gray-900'>{formatted}</p>
				</div>
			</div>
			{chartData ? (
				<ReactApexChart
					options={chartData.options}
					series={chartData.series}
					type='area'
					height={180}
					width='100%'
				/>
			) : (
				<p className='text-gray-400 text-center py-10'>Немає даних для графіку</p>
			)}
		</div>
	);
};

export default Subscribers;
