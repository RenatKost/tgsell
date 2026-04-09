import { useEffect, useState } from 'react';
import { channelsAPI } from '../../services/api';

const verdictConfig = {
	buy: { label: 'Купувати', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-900/20', border: 'border-emerald-200 dark:border-emerald-800', icon: '🟢' },
	hold: { label: 'Зачекати', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-200 dark:border-amber-800', icon: '🟡' },
	avoid: { label: 'Уникати', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20', border: 'border-red-200 dark:border-red-800', icon: '🔴' },
};

const ScoreRing = ({ score }) => {
	const circumference = 2 * Math.PI * 20;
	const offset = circumference - (score / 100) * circumference;
	const color = score >= 70 ? '#10B981' : score >= 40 ? '#F59E0B' : '#EF4444';

	return (
		<div className='relative w-14 h-14 flex-shrink-0'>
			<svg className='w-14 h-14 -rotate-90' viewBox='0 0 48 48'>
				<circle cx='24' cy='24' r='20' stroke='currentColor' strokeWidth='3' fill='none'
					className='text-gray-100 dark:text-slate-700' />
				<circle cx='24' cy='24' r='20' strokeWidth='3' fill='none'
					stroke={color} strokeLinecap='round'
					strokeDasharray={circumference} strokeDashoffset={offset}
					style={{ transition: 'stroke-dashoffset 1s ease-out' }} />
			</svg>
			<div className='absolute inset-0 flex items-center justify-center'>
				<span className='text-xs font-bold' style={{ color }}>{score}</span>
			</div>
		</div>
	);
};

const AiAnalysis = ({ channelId }) => {
	const [data, setData] = useState(null);
	const [loading, setLoading] = useState(false);
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

	// Don't auto-run — let user trigger it
	if (!data && !loading && !error) {
		return (
			<div className='bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800/40 p-4'>
				<div className='flex items-center gap-3 mb-3'>
					<div className='w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-800/50 flex items-center justify-center'>
						<span className='text-sm'>🤖</span>
					</div>
					<div>
						<p className='text-sm font-semibold text-gray-900 dark:text-white'>AI-аналітика</p>
						<p className='text-[10px] text-gray-500 dark:text-gray-400'>Глибокий аналіз від нейромережі</p>
					</div>
				</div>
				<p className='text-xs text-gray-500 dark:text-gray-400 mb-3 leading-relaxed'>
					Нейромережа проаналізує контент, аудиторію, способи монетизації та ризики каналу.
				</p>
				<button
					onClick={runAnalysis}
					className='w-full py-2 rounded-lg text-xs font-semibold bg-indigo-500 hover:bg-indigo-600 text-white transition-all shadow-sm'
				>
					✨ Запустити AI-аналіз
				</button>
			</div>
		);
	}

	if (loading) {
		return (
			<div className='bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 rounded-xl border border-indigo-100 dark:border-indigo-800/40 p-4'>
				<div className='flex items-center gap-3'>
					<div className='w-8 h-8 rounded-lg bg-indigo-100 dark:bg-indigo-800/50 flex items-center justify-center animate-pulse'>
						<span className='text-sm'>🤖</span>
					</div>
					<div>
						<p className='text-sm font-semibold text-gray-900 dark:text-white'>Аналізую...</p>
						<p className='text-[10px] text-gray-500'>AI обробляє дані каналу</p>
					</div>
				</div>
				<div className='mt-4 space-y-2'>
					<div className='h-3 bg-indigo-100 dark:bg-indigo-800/30 rounded animate-pulse w-full' />
					<div className='h-3 bg-indigo-100 dark:bg-indigo-800/30 rounded animate-pulse w-3/4' />
					<div className='h-3 bg-indigo-100 dark:bg-indigo-800/30 rounded animate-pulse w-5/6' />
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
		<div className='bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm overflow-hidden'>
			{/* Header with score */}
			<div className='bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 px-4 py-3 border-b border-indigo-100 dark:border-indigo-800/30'>
				<div className='flex items-center justify-between'>
					<div className='flex items-center gap-3'>
						<ScoreRing score={data.score || 50} />
						<div>
							<p className='text-sm font-bold text-gray-900 dark:text-white'>AI-аналітика</p>
							<p className='text-[10px] text-gray-500 dark:text-gray-400'>Powered by Gemini</p>
						</div>
					</div>
					{/* Verdict badge */}
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

				{/* Price estimate */}
				{data.fair_price_estimate && (
					<div className='bg-gray-50 dark:bg-slate-700/50 rounded-lg p-3'>
						<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>💰 Оцінка вартості</p>
						<p className='text-xs text-gray-700 dark:text-gray-300 leading-relaxed'>{data.fair_price_estimate}</p>
					</div>
				)}

				{/* Monetization */}
				{data.monetization?.length > 0 && (
					<div>
						<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1.5'>💵 Способи монетизації</p>
						<div className='space-y-1'>
							{data.monetization.map((item, i) => (
								<div key={i} className='flex items-start gap-2 text-xs text-gray-600 dark:text-gray-300'>
									<span className='text-emerald-500 mt-0.5 flex-shrink-0'>●</span>
									<span className='leading-relaxed'>{item}</span>
								</div>
							))}
						</div>
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
						{/* Audience quality */}
						{data.audience_quality && (
							<div>
								<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>👥 Якість аудиторії</p>
								<p className='text-xs text-gray-600 dark:text-gray-300 leading-relaxed'>{data.audience_quality}</p>
							</div>
						)}

						{/* Growth trend */}
						{data.growth_trend && (
							<div>
								<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>📈 Тренд росту</p>
								<p className='text-xs text-gray-600 dark:text-gray-300 leading-relaxed'>{data.growth_trend}</p>
							</div>
						)}

						{/* Content analysis */}
						{data.content_analysis && (
							<div>
								<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>📝 Аналіз контенту</p>
								<p className='text-xs text-gray-600 dark:text-gray-300 leading-relaxed'>{data.content_analysis}</p>
							</div>
						)}

						{/* Opportunities */}
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

						{/* Risks */}
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
			<div className='border-t border-gray-100 dark:border-slate-700 px-4 py-2'>
				<p className='text-[9px] text-gray-400 dark:text-gray-500 text-center'>
					AI-аналіз має інформаційний характер і не є фінансовою порадою
				</p>
			</div>
		</div>
	);
};

export default AiAnalysis;
