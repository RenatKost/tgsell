// Task 22: channel quality index badge + breakdown block.
const COMPONENT_LABELS = {
	er: 'ER (свіжі перегляди / підписники, 30 днів)',
	regularity: 'Регулярність публікацій',
	growth: 'Приріст підписників',
	integrity: 'Ознаки накрутки',
};

const REASONS = {
	few_posts_30d: 'менше 3 постів за 30 днів',
	no_subscribers: 'немає даних про підписників',
	views_hidden: 'перегляди приховані',
};

const tone = (s) => {
	if (s == null) return 'bg-gray-50 dark:bg-card-inner text-gray-500 dark:text-gray-400 border-gray-200 dark:border-card-border';
	if (s >= 70) return 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/40';
	if (s >= 40) return 'bg-sky-50 dark:bg-sky-900/20 text-sky-600 dark:text-sky-400 border-sky-200 dark:border-sky-800/40';
	return 'bg-rose-50 dark:bg-rose-900/20 text-rose-600 dark:text-rose-400 border-rose-200 dark:border-rose-800/40';
};

const detail = (key, c) => {
	if (key === 'er') return `${c.value}% · ${c.posts} постів`;
	if (key === 'regularity') return `${c.active_days} активних днів · ${c.posts} постів`;
	if (key === 'growth') return `${c.value > 0 ? '+' : ''}${c.value}% / міс.`;
	if (key === 'integrity') {
		const parts = [];
		if (c.inflated) parts.push('нетипові перегляди');
		if (c.jumps) parts.push(`різкі стрибки: ${c.jumps}`);
		return parts.length ? parts.join(' · ') : 'не виявлено';
	}
	return '';
};

const tooltip = (channel) => {
	const comps = channel?.quality_breakdown?.components || {};
	return Object.entries(comps).map(([k, c]) => `${COMPONENT_LABELS[k] || k}: ${c.points}/${c.max}`).join('\n') || undefined;
};

export const QualityBadge = ({ channel, className = '' }) => {
	if (!channel || channel.bundle_id || channel.quality_health == null) return null;
	const s = channel.quality_score;
	const sus = channel.quality_health === 'suspicious';
	return (
		<span title={tooltip(channel)} className={`inline-flex items-center gap-1 max-w-full truncate text-[11px] font-semibold px-2.5 py-1 rounded-lg border ${tone(s)} ${className}`}>
			{s == null ? 'Якість: мало даних' : `Якість ${s}/100`}
			{sus && s != null && <span aria-label='можлива накрутка'>⚠</span>}
		</span>
	);
};

export const QualityBlock = ({ channel }) => {
	if (!channel || channel.bundle_id || channel.quality_health == null) return null;
	const b = channel.quality_breakdown || {};
	const comps = b.components || {};
	return (
		<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon p-4 min-w-0'>
			<div className='flex flex-wrap items-center gap-2 mb-3'>
				<h4 className='font-semibold text-gray-900 dark:text-white text-xs uppercase tracking-wider'>Індекс якості</h4>
				<QualityBadge channel={channel} className='ml-auto' />
			</div>
			{Object.keys(comps).length > 0 && (
				<div className='flex flex-col gap-2'>
					{Object.entries(comps).map(([k, c]) => (
						<div key={k} className='min-w-0'>
							<div className='flex justify-between gap-2 text-[11px]'>
								<span className='text-gray-500 dark:text-gray-400 truncate'>{COMPONENT_LABELS[k] || k}</span>
								<span className='font-semibold text-gray-800 dark:text-gray-100 whitespace-nowrap'>{c.points}/{c.max}</span>
							</div>
							<div className='h-1.5 rounded-full bg-gray-100 dark:bg-card-inner overflow-hidden mt-1'>
								<div className='h-full bg-accent' style={{ width: `${Math.round((100 * c.points) / (c.max || 1))}%` }} />
							</div>
							<p className='text-[10px] text-gray-400 mt-0.5'>{detail(k, c)}</p>
						</div>
					))}
				</div>
			)}
			{channel.quality_score == null ? (
				<p className='text-[11px] text-gray-400 mt-3'>
					Мало даних для оцінки{(b.reasons || []).length ? `: ${b.reasons.map(r => REASONS[r] || r).join(', ')}` : ''}. Ми не вигадуємо значення.
				</p>
			) : (b.missing || []).length > 0 ? (
				<p className='text-[10px] text-gray-400 mt-3 leading-snug'>
					Без даних: {b.missing.map(m => (COMPONENT_LABELS[m] || m).toLowerCase()).join(', ')} — бал перераховано за наявними складовими.
				</p>
			) : null}
			<p className='text-[10px] text-gray-400 mt-2 leading-snug'>
				Рахуємо лише за зібраною статистикою, оновлюємо не частіше ніж раз на 6 годин.
			</p>
		</div>
	);
};
