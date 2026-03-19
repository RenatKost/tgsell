import ReactApexChart from 'react-apexcharts';

const Subscribers = ({ stats = [], current }) => {
	const hasData = stats.length > 0;
	const dataPoints = hasData ? stats.map(s => s.subscribers) : [];
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
					colors: ['#27ACD2'],
					fill: {
						colors: ['#27ACD2'],
						type: 'gradient',
						gradient: { opacityFrom: 0.65, opacityTo: 0.5 },
					},
				},
				series: [{ name: 'Підписники', data: dataPoints }],
		  }
		: null;

	const formatted = (current || dataPoints[dataPoints.length - 1])?.toLocaleString('uk-UA') || '—';

	return (
		<div className='bg-white rounded-md shadow-lg px-4 pt-4 2xl:w-[425px] w-full'>
			<div className='flex items-center justify-between'>
				<p className='font-bold text-lg'>{formatted}</p>
				<h4 className='font-bold text-lg'>Підписники</h4>
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
