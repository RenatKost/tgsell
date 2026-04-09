import { useEffect, useState } from 'react';
import { channelsAPI } from '../../services/api';

const verdictConfig = {
	buy: { label: 'Купувати', color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-900/20', border: 'border-emerald-200 dark:border-emerald-800', icon: '🟢' },
	hold: { label: 'Зачекати', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-200 dark:border-amber-800', icon: '🟡' },
	avoid: { label: 'Уникати', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20', border: 'border-red-200 dark:border-red-800', icon: '🔴' },
};

const methodIcons = ['💰', '📢', '🤝', '🎯', '🛒'];

const ReachBar = ({ value, label, color, maxVal }) => {
	const pct = maxVal > 0 ? Math.min(100, (value / maxVal) * 100) : 0;
	return (
		<div className='flex items-center justify-between gap-3'>
			<div className='flex-1'>
				<div className='flex items-center justify-between mb-0.5'>
					<span className='text-[11px] text-gray-400'>{label}</span>
					<span className={`text-[11px] font-bold ${color}`}>{value?.toLocaleString('uk-UA')}</span>
				</div>
				<div className='w-full h-1.5 rounded-full bg-gray-700/30'>
					<div className={`h-full rounded-full transition-all duration-700`} style={{ width: `${pct}%`, backgroundColor: color === 'text-pink-400' ? '#EC4899' : color === 'text-emerald-400' ? '#10B981' : '#F97316' }} />
				</div>
			</div>
		</div>
	);
};

const AiAnalysis = ({ channelId, channel }) => {
	const [data, setData] = useState(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState(null);

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

	// AdvertisingReach data from channel
	const reach12h = channel?.adv_reach_12h;
	const reach24h = channel?.adv_reach_24h;
	const reach48h = channel?.adv_reach_48h;
	const maxReach = Math.max(reach12h || 0, reach24h || 0, reach48h || 0, 1);

	if (loading) {
		return (
			<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm p-4'>
				<div className='flex items-center gap-3 mb-4'>
					<div className='w-8 h-8 rounded-lg bg-indigo-100 dark:bg-card-inner flex items-center justify-center animate-pulse'>
						<span className='text-sm'>🤖</span>
					</div>
					<div>
						<p className='text-sm font-semibold text-gray-900 dark:text-white'>Аналізую...</p>
						<p className='text-[10px] text-gray-500'>AI обробляє дані каналу</p>
					</div>
				</div>
				<div className='grid grid-cols-2 gap-3'>
					{[1,2,3,4].map(i => (
						<div key={i} className='bg-gray-50 dark:bg-card-inner rounded-lg p-3 animate-pulse'>
							<div className='h-3 bg-gray-200 dark:bg-card-hover rounded w-20 mb-2' />
							<div className='h-2 bg-gray-200 dark:bg-card-hover rounded w-full mb-1' />
							<div className='h-2 bg-gray-200 dark:bg-card-hover rounded w-3/4' />
						</div>
					))}
				</div>
			</div>
		);
	}

	if (error) {
		return (
			<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm p-4'>
				{/* Still show AdvReach even if AI fails */}
				{(reach12h || reach24h || reach48h) && (
					<div className='mb-4'>
						<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>Перегляди реклами (за 12, 24, 48 год)</p>
						<div className='space-y-2'>
							{reach12h != null && <ReachBar value={reach12h} label='за 12 годин' color='text-pink-400' maxVal={maxReach} />}
							{reach24h != null && <ReachBar value={reach24h} label='за 24 годин' color='text-emerald-400' maxVal={maxReach} />}
							{reach48h != null && <ReachBar value={reach48h} label='за 48 годин' color='text-orange-400' maxVal={maxReach} />}
						</div>
					</div>
				)}
				<div className='bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-100 dark:border-red-800/40 p-3'>
					<p className='text-xs text-red-600 dark:text-red-400 mb-2'>⚠️ {error}</p>
					<button onClick={runAnalysis} className='text-[11px] text-red-500 hover:underline font-medium'>Спробувати ще раз</button>
				</div>
			</div>
		);
	}

	const verdict = verdictConfig[data.verdict] || verdictConfig.hold;

	return (
		<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm overflow-hidden'>
			{/* Header */}
			<div className='px-4 py-3 border-b border-gray-100 dark:border-card-border'>
				<div className='flex items-center justify-between'>
					<div className='flex items-center gap-2'>
						<span className='text-base'>🤖</span>
						<p className='text-sm font-bold text-gray-900 dark:text-white'>AI АНАЛІЗ І МОНЕТИЗАЦІЯ</p>
					</div>
					<div className={`${verdict.bg} ${verdict.border} border rounded-lg px-2.5 py-1 text-center`}>
						<p className={`text-[11px] font-bold ${verdict.color}`}>{verdict.icon} {verdict.label}</p>
					</div>
				</div>
			</div>

			{/* 2-column grid matching screenshot */}
			<div className='p-4'>
				<div className='grid grid-cols-2 gap-4'>

					{/* ═══ LEFT COLUMN ═══ */}
					<div className='space-y-4'>
						{/* Advertising Reach */}
						<div>
							<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>
								Перегляди реклами (за 12, 24, 48 год)
							</p>
							{(reach12h || reach24h || reach48h) ? (
								<div className='space-y-2'>
									{reach12h != null && <ReachBar value={reach12h} label='за 12 годин' color='text-pink-400' maxVal={maxReach} />}
									{reach24h != null && <ReachBar value={reach24h} label='за 24 годин' color='text-emerald-400' maxVal={maxReach} />}
									{reach48h != null && <ReachBar value={reach48h} label='за 48 годин' color='text-orange-400' maxVal={maxReach} />}
								</div>
							) : (
								<p className='text-gray-500 text-xs'>Дані відсутні</p>
							)}
						</div>

						{/* Content Analysis */}
						<div>
							<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>AI КОНТЕНТ АНАЛІЗ</p>

							{/* Sentiment with bars */}
							<div className='mb-3'>
								<p className='text-[10px] text-gray-500 mb-1.5'>Сентимент-розподіл</p>
								<div className='space-y-1.5'>
									{[
										{ label: 'Позитивний', pct: data.sentiment_positive ?? 0, color: 'bg-emerald-500', dot: 'bg-emerald-500' },
										{ label: 'Нейтральний', pct: data.sentiment_neutral ?? 0, color: 'bg-gray-400', dot: 'bg-gray-400' },
										{ label: 'Негативний', pct: data.sentiment_negative ?? 0, color: 'bg-red-500', dot: 'bg-red-500' },
									].map((s) => (
										<div key={s.label} className='flex items-center gap-2'>
											<span className={`w-2 h-2 rounded-full ${s.dot} flex-shrink-0`} />
											<span className='text-[10px] text-gray-400 w-20 flex-shrink-0'>{s.label}</span>
											<div className='flex-1 h-1.5 rounded-full bg-gray-700/30'>
												<div className={`h-full rounded-full ${s.color}`} style={{ width: `${s.pct}%` }} />
											</div>
											<span className='text-[10px] text-gray-300 font-medium w-8 text-right'>{s.pct}%</span>
										</div>
									))}
								</div>
							</div>

							{/* Audience quality / Relevance */}
							{data.audience_quality && (
								<div className='mb-3'>
									<p className='text-[10px] text-gray-500 mb-1'>Релевантність ніші</p>
									<p className='text-[11px] text-gray-300 leading-relaxed'>{data.audience_quality}</p>
								</div>
							)}

							{/* Keyword topics with bars */}
							{(data.content_topics?.length > 0 || data.content_analysis) && (
								<div>
									<p className='text-[10px] text-gray-500 mb-1.5'>Ключові теми</p>
									<div className='space-y-1'>
										{(data.content_topics || data.content_analysis
											.split(/[,;.•\n]+/)
											.map(t => t.trim())
											.filter(t => t.length > 2 && t.length < 40)
											.slice(0, 5)
										).slice(0, 5).map((topic, i) => {
											const pct = Math.max(10, 60 - i * 10);
											return (
												<div key={i} className='flex items-center gap-2'>
													<span className='text-[10px] text-gray-300 w-24 truncate flex-shrink-0 uppercase font-medium'>{topic}</span>
													<div className='flex-1 h-1.5 rounded-full bg-gray-700/30'>
														<div className='h-full rounded-full bg-orange-500' style={{ width: `${pct}%` }} />
													</div>
													<span className='text-[10px] text-gray-400 w-8 text-right'>{pct}%</span>
												</div>
											);
										})}
									</div>
								</div>
							)}
						</div>
					</div>

					{/* ═══ RIGHT COLUMN ═══ */}
					<div className='space-y-4'>
						{/* Monetization Assessment */}
						<div>
							<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>МОНЕТИЗАЦІЙНА ОЦІНКА</p>
							{data.monetization?.length > 0 ? (
								<div className='space-y-1.5'>
									{data.monetization.map((item, i) => {
										if (typeof item !== 'object') return null;
										return (
											<div key={i} className='flex items-center justify-between py-1'>
												<div className='flex items-center gap-2 min-w-0'>
													<span className='text-sm flex-shrink-0'>{methodIcons[i] || '💵'}</span>
													<span className='text-[11px] text-gray-300 truncate'>{item.method}</span>
												</div>
												<div className='flex items-center gap-2 flex-shrink-0'>
													<div className='w-12 h-1.5 rounded-full bg-gray-700/30 overflow-hidden'>
														<div className='h-full rounded-full bg-accent' style={{ width: `${Math.min(100, ((item.income_max || 0) / (data.total_potential_income_max || 1)) * 100)}%` }} />
													</div>
													<span className='text-[11px] font-bold text-emerald-400 whitespace-nowrap'>
														{item.income_max?.toLocaleString('uk-UA')} USDT/міс
													</span>
												</div>
											</div>
										);
									})}
								</div>
							) : (
								<p className='text-gray-500 text-xs'>Pending Data...</p>
							)}
						</div>

						{/* Potential ROI */}
						<div>
							<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-2'>ПОТЕНЦІЙНИЙ ROI</p>
							{data.fair_price_estimate && (
								<p className='text-[11px] text-gray-300 leading-relaxed mb-1'>
									Справедлива ціна каналу: <span className='font-semibold text-white'>{data.fair_price_estimate}</span>
								</p>
							)}
							{data.roi_months && (
								<p className='text-[11px] text-gray-300'>
									Очікувана окупність: <span className='font-semibold text-emerald-400'>{data.roi_months}</span>
								</p>
							)}
							{(data.total_potential_income_min || data.total_potential_income_max) && (
								<div className='mt-2 bg-emerald-900/20 rounded-lg p-2.5 border border-emerald-800/40'>
									<div className='flex items-baseline gap-1.5'>
										<span className='text-sm font-bold text-emerald-400'>
											від ${data.total_potential_income_min || '?'} до ${data.total_potential_income_max || '?'}
										</span>
										<span className='text-[10px] text-emerald-500/70'>USDT / місяць</span>
									</div>
								</div>
							)}
						</div>

						{/* Growth trend */}
						{data.growth_trend && (
							<div>
								<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>📈 Тренд росту</p>
								<p className='text-[11px] text-gray-300 leading-relaxed'>{data.growth_trend}</p>
							</div>
						)}
					</div>
				</div>

				{/* Verdict reason - full width */}
				{data.verdict_reason && (
					<div className={`mt-3 text-[11px] ${verdict.color} ${verdict.bg} rounded-lg px-3 py-2`}>
						{data.verdict_reason}
					</div>
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
