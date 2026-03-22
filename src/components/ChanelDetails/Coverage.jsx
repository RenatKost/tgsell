import ReactApexChart from 'react-apexcharts';
import { useState } from 'react';
import ChartModal from './ChartModal';

const TF = [
	{ label: 'Все', days: 0 },
	{ label: '30д', days: 30 },
	{ label: '14д', days: 14 },
	{ label: '7д', days: 7 },
];

const Coverage = ({ stats = [], current }) => {
	const [tf, setTf] = useState(0);
	const [modal, setModal] = useState(false);

	const now = Date.now();
	const filtered = TF[tf].days === 0 ? stats : stats.filter(s => {
		const d = new Date(s.date).getTime();
		return (now - d) / 86400000 <= TF[tf].days;
	});

	const hasData = filtered.length > 0;
	const dataPoints = hasData ? filtered.map(s => s.avg_reach || s.avg_views || 0) : [];

	const minVal = Math.min(...dataPoints);
	const maxVal = Math.max(...dataPoints);
	const range = maxVal - minVal || maxVal * 0.1 || 1;
	const yMin = Math.max(0, Math.floor(minVal - range * 0.3));
	const yMax = Math.ceil(maxVal + range * 0.3);

	const chartData = hasData
		? {
				options: {
					dataLabels: { enabled: false },
					stroke: { curve: 'smooth', width: 2.5 },
					chart: { toolbar: { show: false }, animations: { enabled: true, easing: 'easeinout', speed: 600 } },
					xaxis: {
						labels: { show: false },
						axisTicks: { show: false },
						axisBorder: { show: false },
						tooltip: { enabled: false },
					},
					yaxis: { min: yMin, max: yMax, labels: { show: false } },
					grid: { show: true, borderColor: '#f3f4f6', strokeDashArray: 4, xaxis: { lines: { show: false } }, padding: { bottom: 0 } },
					legend: { show: false },
					tooltip: { y: { formatter: v => v?.toLocaleString('uk-UA') } },
					colors: ['#F97316'],
					fill: { colors: ['#F97316'], type: 'gradient', gradient: { opacityFrom: 0.45, opacityTo: 0.02, shadeIntensity: 1, stops: [0, 90, 100] } },
				},
				series: [{ name: 'Охоплення публікацій', data: dataPoints }],
		  }
		: null;

	const formatted = (current || dataPoints[dataPoints.length - 1])?.toLocaleString('uk-UA') || '—';

	return (
		<div className='bg-white rounded-2xl border border-gray-100 shadow-sm px-5 pt-5 w-full'>
			<div className='flex items-center justify-between mb-1'>
				<div>
					<p className='text-gray-400 text-xs'>Охоплення публікацій</p>
					<p className='font-bold text-xl text-gray-900'>{formatted}</p>
				</div>
				<div className='flex items-center gap-1'>
					{TF.map((t, i) => (
						<button key={i} onClick={() => setTf(i)}
							className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
								tf === i ? 'bg-[#F97316] text-white' : 'bg-gray-50 text-gray-400 hover:bg-gray-100'
							}`}>{t.label}</button>
					))}
					<button onClick={() => setModal(true)} className='ml-1 w-7 h-7 rounded-lg bg-gray-50 hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-all' title='Розгорнути'>
						<svg width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' strokeLinecap='round' strokeLinejoin='round'><path d='M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7'/></svg>
					</button>
				</div>
			</div>
			{chartData ? (
				<ReactApexChart options={chartData.options} series={chartData.series} type='area' height={180} width='100%' />
			) : (
				<p className='text-gray-400 text-center py-10'>Немає даних для графіку</p>
			)}
			<ChartModal open={modal} onClose={() => setModal(false)} stats={stats} title='Охоплення публікацій' color='#F97316' dataKey={s => s.avg_reach || s.avg_views || 0} seriesName='Охоплення' />
		</div>
	);
};

export default Coverage;
