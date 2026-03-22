import ReactApexChart from 'react-apexcharts';
import { useState } from 'react';

const TF = [
	{ label: '30д', days: 30 },
	{ label: '14д', days: 14 },
	{ label: '7д', days: 7 },
];

const Views = ({ stats = [], current }) => {
	const [tf, setTf] = useState(0);

	const now = Date.now();
	const filtered = stats.filter(s => {
		const d = new Date(s.date).getTime();
		return (now - d) / 86400000 <= TF[tf].days;
	});

	const hasData = filtered.length > 0;
	const dataPoints = hasData ? filtered.map(s => s.avg_views || 0) : [];
	const categories = hasData ? filtered.map(s => {
		const d = new Date(s.date);
		return `${d.getDate()}.${String(d.getMonth() + 1).padStart(2, '0')}`;
	}) : [];

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
						categories,
						labels: { show: false },
						axisTicks: { show: false },
						axisBorder: { show: false },
						tooltip: { enabled: false },
					},
					yaxis: {
						min: yMin,
						max: yMax,
						labels: { show: false },
					},
					grid: { show: true, borderColor: '#f3f4f6', strokeDashArray: 4, xaxis: { lines: { show: false } }, padding: { bottom: 0 } },
					legend: { show: false },
					tooltip: { y: { formatter: v => v?.toLocaleString('uk-UA') } },
					colors: ['#EC4899'],
					fill: {
						colors: ['#EC4899'],
						type: 'gradient',
						gradient: { opacityFrom: 0.45, opacityTo: 0.02, shadeIntensity: 1, stops: [0, 90, 100] },
					},
				},
				series: [{ name: 'Добовий перегляд', data: dataPoints }],
		  }
		: null;

	const formatted = (current || dataPoints[dataPoints.length - 1])?.toLocaleString('uk-UA') || '—';

	return (
		<div className='bg-white rounded-2xl border border-gray-100 shadow-sm px-5 pt-5 w-full'>
			<div className='flex items-center justify-between mb-1'>
				<div>
					<p className='text-gray-400 text-xs'>Добовий перегляд</p>
					<p className='font-bold text-xl text-gray-900'>{formatted}</p>
				</div>
				<div className='flex gap-1'>
					{TF.map((t, i) => (
						<button key={i} onClick={() => setTf(i)}
							className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all ${
								tf === i ? 'bg-[#EC4899] text-white' : 'bg-gray-50 text-gray-400 hover:bg-gray-100'
							}`}>{t.label}</button>
					))}
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

export default Views;
