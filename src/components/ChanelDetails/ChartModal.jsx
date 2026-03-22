import ReactApexChart from 'react-apexcharts';
import { useState, useEffect } from 'react';

const TF = [
	{ label: 'Все', days: 0 },
	{ label: '30д', days: 30 },
	{ label: '14д', days: 14 },
	{ label: '7д', days: 7 },
];

const ChartModal = ({ open, onClose, stats = [], title, color, dataKey, tooltipFmt, seriesName }) => {
	const [tf, setTf] = useState(0);

	useEffect(() => {
		if (open) document.body.style.overflow = 'hidden';
		else document.body.style.overflow = '';
		return () => { document.body.style.overflow = ''; };
	}, [open]);

	useEffect(() => {
		const onKey = e => { if (e.key === 'Escape') onClose(); };
		if (open) window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	}, [open, onClose]);

	if (!open) return null;

	const now = Date.now();
	const filtered = TF[tf].days === 0 ? stats : stats.filter(s => {
		const d = new Date(s.date).getTime();
		return (now - d) / 86400000 <= TF[tf].days;
	});

	const hasData = filtered.length > 0;
	const dataPoints = hasData ? filtered.map(s => typeof dataKey === 'function' ? dataKey(s) : (s[dataKey] || 0)) : [];
	const categories = hasData ? filtered.map(s => {
		const d = new Date(s.date);
		return `${d.getDate()}.${String(d.getMonth() + 1).padStart(2, '0')}`;
	}) : [];

	const minVal = Math.min(...dataPoints);
	const maxVal = Math.max(...dataPoints, 0.1);
	const range = maxVal - minVal || maxVal * 0.1 || 1;
	const yMin = Math.max(0, dataKey === 'er' ? +(minVal - range * 0.3).toFixed(2) : Math.floor(minVal - range * 0.3));
	const yMax = dataKey === 'er' ? +(maxVal + range * 0.3).toFixed(2) : Math.ceil(maxVal + range * 0.3);

	// Stats summary
	const avg = dataPoints.length ? dataPoints.reduce((a, b) => a + b, 0) / dataPoints.length : 0;
	const min = dataPoints.length ? Math.min(...dataPoints) : 0;
	const max = dataPoints.length ? Math.max(...dataPoints) : 0;
	const last = dataPoints[dataPoints.length - 1] || 0;
	const first = dataPoints[0] || 0;
	const diff = last - first;
	const pct = first ? ((diff / first) * 100).toFixed(1) : '0';
	const isPercent = dataKey === 'er';
	const fmt = v => isPercent ? `${v.toFixed(2)}%` : v.toLocaleString('uk-UA');

	const options = {
		dataLabels: { enabled: false },
		stroke: { curve: 'smooth', width: 2.5 },
		chart: {
			toolbar: { show: true, tools: { download: true, selection: true, zoom: true, zoomin: true, zoomout: true, pan: true, reset: true } },
			animations: { enabled: true, easing: 'easeinout', speed: 600 },
			zoom: { enabled: true },
		},
		xaxis: {
			categories,
			tickAmount: Math.min(categories.length, 15),
			labels: { show: true, rotate: -45, rotateAlways: false, style: { colors: '#6b7280', fontSize: '11px' }, hideOverlappingLabels: true, maxHeight: 80 },
			axisTicks: { show: true, color: '#e5e7eb' },
			axisBorder: { show: true, color: '#e5e7eb' },
			tooltip: { enabled: false },
		},
		yaxis: {
			min: yMin,
			max: yMax,
			labels: { show: true, style: { colors: '#6b7280', fontSize: '12px' }, formatter: v => isPercent ? `${v.toFixed(1)}%` : v.toLocaleString('uk-UA') },
		},
		grid: { show: true, borderColor: '#f3f4f6', strokeDashArray: 3, xaxis: { lines: { show: true } } },
		legend: { show: false },
		tooltip: {
			y: { formatter: tooltipFmt || (v => v?.toLocaleString('uk-UA')) },
			x: { show: true },
		},
		markers: { size: 3, colors: [color], strokeWidth: 0, hover: { size: 6 } },
		colors: [color],
		fill: {
			colors: [color],
			type: 'gradient',
			gradient: { opacityFrom: 0.35, opacityTo: 0.02, shadeIntensity: 1, stops: [0, 90, 100] },
		},
	};

	return (
		<div className='fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm' onClick={onClose}>
			<div className='bg-white rounded-2xl shadow-2xl w-[95vw] max-w-5xl max-h-[92vh] overflow-auto animate-fadeIn' onClick={e => e.stopPropagation()}>
				{/* Header */}
				<div className='flex items-center justify-between px-6 py-4 border-b border-gray-100'>
					<div>
						<p className='text-gray-400 text-xs'>{title}</p>
						<p className='font-bold text-2xl text-gray-900'>{fmt(last)}</p>
					</div>
					<div className='flex items-center gap-3'>
						<div className='flex gap-1'>
							{TF.map((t, i) => (
								<button key={i} onClick={() => setTf(i)}
									className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
										tf === i ? 'text-white' : 'bg-gray-50 text-gray-400 hover:bg-gray-100'
									}`}
									style={tf === i ? { backgroundColor: color } : {}}
								>{t.label}</button>
							))}
						</div>
						<button onClick={onClose} className='w-9 h-9 rounded-xl bg-gray-50 hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-all text-lg'>✕</button>
					</div>
				</div>

				{/* Summary stats */}
				<div className='grid grid-cols-2 sm:grid-cols-5 gap-3 px-6 py-4'>
					<div className='bg-gray-50 rounded-xl p-3 text-center'>
						<p className='text-gray-400 text-xs mb-0.5'>Поточне</p>
						<p className='font-bold text-gray-800 text-sm'>{fmt(last)}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3 text-center'>
						<p className='text-gray-400 text-xs mb-0.5'>Середнє</p>
						<p className='font-bold text-gray-800 text-sm'>{fmt(isPercent ? +avg.toFixed(2) : Math.round(avg))}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3 text-center'>
						<p className='text-gray-400 text-xs mb-0.5'>Мінімум</p>
						<p className='font-bold text-gray-800 text-sm'>{fmt(min)}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3 text-center'>
						<p className='text-gray-400 text-xs mb-0.5'>Максимум</p>
						<p className='font-bold text-gray-800 text-sm'>{fmt(max)}</p>
					</div>
					<div className='bg-gray-50 rounded-xl p-3 text-center'>
						<p className='text-gray-400 text-xs mb-0.5'>Зміна</p>
						<p className={`font-bold text-sm ${diff >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
							{diff >= 0 ? '↑' : '↓'} {fmt(isPercent ? +Math.abs(diff).toFixed(2) : Math.abs(Math.round(diff)))} ({diff >= 0 ? '+' : ''}{pct}%)
						</p>
					</div>
				</div>

				{/* Chart */}
				<div className='px-6 pb-6'>
					{hasData ? (
						<ReactApexChart
							options={options}
							series={[{ name: seriesName, data: dataPoints }]}
							type='area'
							height={420}
							width='100%'
						/>
					) : (
						<p className='text-gray-400 text-center py-16'>Немає даних для графіку</p>
					)}
				</div>
			</div>
		</div>
	);
};

export default ChartModal;
