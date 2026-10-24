import { fmtNum } from '../../utils/money';
// Task 24: «Схожі канали» block on the channel page.
import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { similarAPI } from '../../services/api';

const fmt = (n) => (n == null ? '—' : fmtNum(Number(n)));

const SimilarChannels = ({ channelId }) => {
	const [items, setItems] = useState([]);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		let alive = true;
		setLoading(true);
		similarAPI.get(channelId)
			.then(({ data }) => { if (alive) setItems(data.items || []); })
			.catch(() => { if (alive) setItems([]); })
			.finally(() => { if (alive) setLoading(false); });
		return () => { alive = false; };
	}, [channelId]);

	if (loading || items.length === 0) return null;

	return (
		<div className='mt-4 bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon p-4'>
			<h4 className='font-semibold text-gray-900 dark:text-white text-xs uppercase tracking-wider mb-3'>Схожі канали</h4>
			<div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3'>
				{items.map(c => (
					<NavLink key={c.id} to={`/channel/${c.id}`}
						className='flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-card-inner border border-gray-100 dark:border-card-border hover:border-accent transition-colors'>
						{c.avatar_url ? (
							<img src={c.avatar_url} alt='' className='w-10 h-10 rounded-lg object-cover flex-shrink-0' />
						) : (
							<div className='w-10 h-10 rounded-lg bg-accent/20 flex items-center justify-center font-bold text-accent flex-shrink-0'>
								{c.channel_name?.[0] || 'T'}
							</div>
						)}
						<div className='min-w-0 flex-1'>
							<div className='text-sm font-semibold text-gray-900 dark:text-white truncate'>{c.channel_name || 'Без назви'}</div>
							<div className='text-[11px] text-gray-500 dark:text-gray-400'>
								{fmt(c.subscribers_count)} підп. · {fmt(c.price)} USDT
								{c.price_per_view != null && <> · ${c.price_per_view.toFixed(3)}/перегл.</>}
							</div>
						</div>
						{c.quality_score != null && (
							<span className='text-[11px] font-bold px-2 py-0.5 rounded-full bg-accent/15 text-accent' title='Індекс якості'>
								{c.quality_score}
							</span>
						)}
					</NavLink>
				))}
			</div>
		</div>
	);
};

export default SimilarChannels;
