import { useEffect, useState } from 'react';
import { channelsAPI } from '../../services/api';

const verdictConfig = {
	buy: { label: 'Купувати', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-900/20', border: 'border-emerald-200 dark:border-emerald-800', icon: '🟢' },
	hold: { label: 'Зачекати', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-200 dark:border-amber-800', icon: '🟡' },
	avoid: { label: 'Уникати', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20', border: 'border-red-200 dark:border-red-800', icon: '🔴' },
};

const methodIcons = ['💰', '📢', '🤝', '🎯', '🛒'];

const ScoreRing = ({ score }) => {
	const circumference = 2 * Math.PI * 22;
	const offset = circumference - (score / 100) * circumference;
	const color = score >= 70 ? '#10B981' : score >= 40 ? '#F59E0B' : '#EF4444';

	return (
		<div className='relative w-16 h-16 flex-shrink-0'>
			<svg className='w-16 h-16 -rotate-90' viewBox='0 0 52 52'>
				<circle cx='26' cy='26' r='22' stroke='currentColor' strokeWidth='3' fill='none'
					className='text-gray-100 dark:text-card-inner' />
				<circle cx='26' cy='26' r='22' strokeWidth='3' fill='none'
					stroke={color} strokeLinecap='round'
					strokeDasharray={circumference} strokeDashoffset={offset}
					style={{ transition: 'stroke-dashoffset 1s ease-out' }} />
			</svg>
			<div className='absolute inset-0 flex flex-col items-center justify-center'>
				<span className='text-sm font-bold leading-none' style={{ color }}>{score}</span>
				<span className='text-[8px] text-gray-400'>/ 100</span>
			</div>
		</div>
	);
};

const MonetizationCard = ({ item, index }) => {
	const [open, setOpen] = useState(false);
	return (
		<div className='bg-gray-50 dark:bg-card-inner rounded-lg border border-gray-100 dark:border-card-border overflow-hidden'>
			<button
				onClick={() => setOpen(!open)}
				className='w-full px-3 py-2.5 flex items-center gap-2.5 text-left hover:bg-gray-100 dark:hover:bg-card-hover transition-colors'
			>
				<span className='text-base flex-shrink-0'>{methodIcons[index] || '💵'}</span>
				<div className='flex-1 min-w-0'>
					<p className='text-xs font-semibold text-gray-800 dark:text-gray-200 truncate'>{item.method}</p>
					<p className='text-[10px] text-gray-500 dark:text-gray-400 truncate'>{item.description}</p>
				</div>
				<div className='text-right flex-shrink-0'>
					<p className='text-xs font-bold text-emerald-600 dark:text-emerald-400'>
						${item.income_min}–${item.income_max}
					</p>
					<p className='text-[9px] text-gray-400'>USDT/міс</p>
				</div>
				<span className='text-gray-400 text-[10px] flex-shrink-0'>{open ? '▴' : '▾'}</span>
			</button>
			{open && (
				<div className='px-3 pb-2.5 pt-0'>
					<p className='text-[11px] text-gray-600 dark:text-gray-300 leading-relaxed bg-white dark:bg-page rounded p-2'>
						{item.reasoning}
					</p>
				</div>
			)}
		</div>
	);
};

const AiAnalysis = ({ channelId }) => {
	const [data, setData] = useState(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState(null);
	const [expanded, setExpanded] = useState(false);

	const runAnalysis = async () => {
		setLoading(true);
		setError(null);
		try {
			const { data: result } = await channelsAPI.getAiAnalysis(channelId);
			setData(result);
		} catch (e) {
			setError(e.response?.data?.detail || 'Аналіз недоступний');
		} finally {
			setLoading(false);
		}
	};

	useEffect(() => { runAnalysis(); }, [channelId]);

	if (loading) {
		return (
			<div className='bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-card dark:to-card rounded-xl border border-indigo-100 dark:border-card-border p-4'>
				<div className='flex items-center gap-3'>
					<div className='w-8 h-8 rounded-lg bg-indigo-100 dark:bg-card-inner flex items-center justify-center animate-pulse'>
						<span className='text-sm'>🤖</span>
					</div>
					<div>
						<p className='text-sm font-semibold text-gray-900 dark:text-white'>Аналізую...</p>
						<p className='text-[10px] text-gray-500'>AI обробляє дані каналу</p>
					</div>
				</div>
				<div className='mt-4 space-y-2'>
					<div className='h-3 bg-indigo-100 dark:bg-card-inner rounded animate-pulse w-full' />
					<div className='h-3 bg-indigo-100 dark:bg-card-inner rounded animate-pulse w-3/4' />
					<div className='h-3 bg-indigo-100 dark:bg-card-inner rounded animate-pulse w-5/6' />
				</div>
			</div>
		);
	}

	if (error) {
		return (
			<div className='bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-100 dark:border-red-800/40 p-4'>
				<p className='text-xs text-red-600 dark:text-red-400 mb-2'>⚠️ {error}</p>
				<button onClick={runAnalysis} className='text-[11px] text-red-500 hover:underline font-medium'>
					Спробувати ще раз
				</button>
			</div>
		);
	}

	const verdict = verdictConfig[data.verdict] || verdictConfig.hold;

	return (
		<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm overflow-hidden'>
			{/* Header with score + verdict */}
			<div className='bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-card-inner dark:to-card-inner px-4 py-3 border-b border-indigo-100 dark:border-card-border'>
				<div className='flex items-center justify-between'>
					<div className='flex items-center gap-3'>
						<ScoreRing score={data.score || 50} />
						<div>
							<p className='text-sm font-bold text-gray-900 dark:text-white'>AI-аналітика</p>
							<p className='text-[10px] text-gray-500 dark:text-gray-400'>Powered by Llama 3.3 70B</p>
						</div>
					</div>
					<div className={`${verdict.bg} ${verdict.border} border rounded-lg px-3 py-1.5 text-center`}>
						<p className='text-[10px] text-gray-500 dark:text-gray-400'>Вердикт</p>
						<p className={`text-xs font-bold ${verdict.color}`}>{verdict.icon} {verdict.label}</p>
					</div>
				</div>
			</div>

			<div className='p-4 space-y-3'>
				{/* Summary */}
				<div>
					<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>Висновок</p>
					<p className='text-xs text-gray-700 dark:text-gray-300 leading-relaxed'>{data.summary}</p>
				</div>

				{/* Verdict reason */}
				{data.verdict_reason && (
					<p className={`text-[11px] ${verdict.color} ${verdict.bg} rounded-lg px-3 py-2`}>
						{data.verdict_reason}
					</p>
				)}

				{/* Total income potential */}
				{(data.total_potential_income_min || data.total_potential_income_max) && (
					<div className='bg-emerald-50 dark:bg-emerald-900/20 rounded-lg p-3 border border-emerald-100 dark:border-emerald-800/40'>
						<p className='text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold uppercase tracking-wider mb-1'>💰 Потенційний дохід</p>
						<div className='flex items-baseline gap-1.5'>
							<span className='text-lg font-bold text-emerald-600 dark:text-emerald-400'>
								${data.total_potential_income_min || '?'}–${data.total_potential_income_max || '?'}
							</span>
							<span className='text-[11px] text-emerald-500/70'>USDT / місяць</span>
						</div>
						{data.roi_months && (
							<p className='text-[10px] text-emerald-600/70 dark:text-emerald-400/70 mt-1'>
								⏱ Окупність: {data.roi_months}
							</p>
						)}
					</div>
				)}

				{/* 5 Monetization methods */}
				{data.monetization?.length > 0 && (
					<div>
						<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>
							💵 Способи монетизації ({data.monetization.length})
						</p>
						<div className='space-y-1.5'>
							{data.monetization.map((item, i) => (
								typeof item === 'object'
									? <MonetizationCard key={i} item={item} index={i} />
									: <div key={i} className='flex items-start gap-2 text-xs text-gray-600 dark:text-gray-300'>
										<span className='text-emerald-500 mt-0.5 flex-shrink-0'>●</span>
										<span className='leading-relaxed'>{item}</span>
									</div>
							))}
						</div>
					</div>
				)}

				{/* Price estimate */}
				{data.fair_price_estimate && (
				<div className='bg-gray-50 dark:bg-card-inner rounded-lg p-3'>
						<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>🏷️ Оцінка вартості</p>
						<p className='text-xs text-gray-700 dark:text-gray-300 leading-relaxed'>{data.fair_price_estimate}</p>
					</div>
				)}

				{/* Expandable details */}
				{!expanded ? (
					<button
						onClick={() => setExpanded(true)}
						className='w-full py-1.5 text-center text-[11px] text-indigo-500 hover:text-indigo-600 font-medium transition-colors'
					>
						Детальніше ▾
					</button>
				) : (
					<>
						{data.audience_quality && (
							<div>
								<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>👥 Якість аудиторії</p>
								<p className='text-xs text-gray-600 dark:text-gray-300 leading-relaxed'>{data.audience_quality}</p>
							</div>
						)}

						{data.growth_trend && (
							<div>
								<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>📈 Тренд росту</p>
								<p className='text-xs text-gray-600 dark:text-gray-300 leading-relaxed'>{data.growth_trend}</p>
							</div>
						)}

						{data.content_analysis && (
							<div>
								<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>📝 Аналіз контенту</p>
								<p className='text-xs text-gray-600 dark:text-gray-300 leading-relaxed'>{data.content_analysis}</p>
							</div>
						)}

						{data.opportunities?.length > 0 && (
							<div>
								<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1.5'>🚀 Можливості</p>
								<div className='space-y-1'>
									{data.opportunities.map((item, i) => (
										<div key={i} className='flex items-start gap-2 text-xs text-gray-600 dark:text-gray-300'>
											<span className='text-blue-500 mt-0.5 flex-shrink-0'>●</span>
											<span className='leading-relaxed'>{item}</span>
										</div>
									))}
								</div>
							</div>
						)}

						{data.risks?.length > 0 && (
							<div>
								<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1.5'>⚠️ Ризики</p>
								<div className='space-y-1'>
									{data.risks.map((item, i) => (
										<div key={i} className='flex items-start gap-2 text-xs text-gray-600 dark:text-gray-300'>
											<span className='text-red-500 mt-0.5 flex-shrink-0'>●</span>
											<span className='leading-relaxed'>{item}</span>
										</div>
									))}
								</div>
							</div>
						)}

						<button
							onClick={() => setExpanded(false)}
							className='w-full py-1.5 text-center text-[11px] text-gray-400 hover:text-gray-600 font-medium transition-colors'
						>
							Згорнути ▴
						</button>
					</>
				)}
			</div>

			{/* Disclaimer */}
			<div className='border-t border-gray-100 dark:border-card-border px-4 py-2'>
				<p className='text-[9px] text-gray-400 dark:text-gray-500 text-center'>
					AI-аналіз має інформаційний характер і не є фінансовою порадою
				</p>
			</div>
		</div>
	);
};

export default AiAnalysis;
