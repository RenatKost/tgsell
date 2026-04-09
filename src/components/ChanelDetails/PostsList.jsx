import { useEffect, useState } from 'react';
import { channelsAPI } from '../../services/api';

const mediaIcons = {
	photo: '🖼',
	video: '🎥',
	document: '📄',
	audio: '🎵',
	voice: '🎤',
};

const formatNum = (n) => {
	if (n == null) return '—';
	if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
	if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
	return n.toLocaleString('uk-UA');
};

const formatDate = (iso) => {
	const d = new Date(iso);
	const day = d.getDate();
	const months = ['січ', 'лют', 'бер', 'кві', 'тра', 'чер', 'лип', 'сер', 'вер', 'жов', 'лис', 'гру'];
	const h = String(d.getHours()).padStart(2, '0');
	const m = String(d.getMinutes()).padStart(2, '0');
	return `${day} ${months[d.getMonth()]} ${h}:${m}`;
};

const TelegramPost = ({ post }) => {
	const [expanded, setExpanded] = useState(false);
	const longText = post.text && post.text.length > 200;

	return (
		<div className='relative pl-10 pb-6 group'>
			{/* Timeline connector */}
			<div className='absolute left-[15px] top-0 bottom-0 w-px bg-gray-200 dark:bg-slate-700 group-last:bg-gradient-to-b group-last:from-gray-200 group-last:to-transparent dark:group-last:from-slate-700 dark:group-last:to-transparent' />

			{/* Timeline dot */}
			<div className='absolute left-[10px] top-1.5 w-[11px] h-[11px] rounded-full border-2 border-[#3498db] bg-white dark:bg-slate-800 z-10' />

			{/* Message bubble */}
			<div className='bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm overflow-hidden hover:shadow-md transition-shadow duration-200'>
				{/* Text body */}
				<div className='px-3.5 pt-3 pb-2'>
					{post.text ? (
						<>
							<p className={`text-[13px] text-gray-700 dark:text-gray-200 leading-relaxed whitespace-pre-wrap ${!expanded && longText ? 'line-clamp-4' : ''}`}>
								{post.text}
							</p>
							{longText && (
								<button
									onClick={() => setExpanded(!expanded)}
									className='text-[#3498db] text-[11px] font-medium mt-1 hover:underline'
								>
									{expanded ? 'Згорнути' : 'Читати далі...'}
								</button>
							)}
						</>
					) : (
						<p className='text-[13px] text-gray-400 dark:text-gray-500 italic'>Медіа-контент</p>
					)}
				</div>

				{/* Footer: date + stats + media badge */}
				<div className='flex items-center justify-between px-3.5 pb-2.5 pt-1'>
					<div className='flex items-center gap-3'>
						{/* Views */}
						<span className='flex items-center gap-1 text-[11px] text-gray-400'>
							<svg className='w-3.5 h-3.5' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='1.5'>
								<path strokeLinecap='round' strokeLinejoin='round' d='M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z' />
								<path strokeLinecap='round' strokeLinejoin='round' d='M15 12a3 3 0 11-6 0 3 3 0 016 0z' />
							</svg>
							<span className='font-medium'>{formatNum(post.views)}</span>
						</span>

						{/* Reactions */}
						{post.reactions > 0 && (
							<span className='flex items-center gap-0.5 text-[11px] text-gray-400'>
								<span className='text-[10px]'>❤️</span>
								<span className='font-medium'>{formatNum(post.reactions)}</span>
							</span>
						)}

						{/* Forwards */}
						{post.forwards > 0 && (
							<span className='flex items-center gap-0.5 text-[11px] text-gray-400'>
								<svg className='w-3 h-3' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='2'>
									<path strokeLinecap='round' strokeLinejoin='round' d='M13 7l5 5m0 0l-5 5m5-5H6' />
								</svg>
								<span className='font-medium'>{formatNum(post.forwards)}</span>
							</span>
						)}

						{/* Comments */}
						{post.comments > 0 && (
							<span className='flex items-center gap-0.5 text-[11px] text-gray-400'>
								<span className='text-[10px]'>💬</span>
								<span className='font-medium'>{formatNum(post.comments)}</span>
							</span>
						)}
					</div>

					<div className='flex items-center gap-2'>
						{post.media_type && (
							<span className='text-[9px] font-medium px-1.5 py-0.5 rounded bg-gray-50 dark:bg-slate-700 text-gray-400'>
								{mediaIcons[post.media_type] || '📎'} {post.media_type}
							</span>
						)}
						<span className='text-[10px] text-gray-400 font-medium'>{formatDate(post.date)}</span>
						{post.link && (
							<a href={`https://${post.link}`} target='_blank' rel='noopener noreferrer'
								className='text-[10px] text-[#3498db] hover:underline font-medium'>↗</a>
						)}
					</div>
				</div>

				{/* View dynamics bar */}
				{(post.views_1h != null || post.views_12h != null || post.views_24h != null || post.views_48h != null) && (
					<div className='flex items-center gap-1.5 px-3.5 pb-2.5'>
						{post.views_1h != null && (
							<span className='bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 px-1.5 py-0.5 rounded text-[9px] font-medium'>
								1h: {formatNum(post.views_1h)}
							</span>
						)}
						{post.views_12h != null && (
							<span className='bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-1.5 py-0.5 rounded text-[9px] font-medium'>
								12h: {formatNum(post.views_12h)}
							</span>
						)}
						{post.views_24h != null && (
							<span className='bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 px-1.5 py-0.5 rounded text-[9px] font-medium'>
								24h: {formatNum(post.views_24h)}
							</span>
						)}
						{post.views_48h != null && (
							<span className='bg-orange-50 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 px-1.5 py-0.5 rounded text-[9px] font-medium'>
								48h: {formatNum(post.views_48h)}
							</span>
						)}
					</div>
				)}
			</div>
		</div>
	);
};

const PostsList = ({ channelId }) => {
	const [posts, setPosts] = useState([]);
	const [total, setTotal] = useState(0);
	const [loading, setLoading] = useState(true);
	const [visibleCount, setVisibleCount] = useState(3);
	const limit = 50;

	useEffect(() => {
		const fetchPosts = async () => {
			setLoading(true);
			try {
				const { data } = await channelsAPI.getPosts(channelId, { limit, offset: 0 });
				setPosts(data.items || []);
				setTotal(data.total || 0);
			} catch {
				setPosts([]);
			} finally {
				setLoading(false);
			}
		};
		fetchPosts();
	}, [channelId]);

	if (loading) {
		return (
			<div className='mt-2'>
				<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-3'>Публікації каналу</p>
				<div className='flex justify-center py-6'>
					<div className='animate-spin rounded-full h-5 w-5 border-2 border-gray-200 border-t-[#3498db]' />
				</div>
			</div>
		);
	}

	if (!posts.length) {
		return (
			<div className='mt-2'>
				<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>Публікації каналу</p>
				<p className='text-gray-300 dark:text-gray-600 text-center py-6 text-xs'>Дані поки відсутні</p>
			</div>
		);
	}

	const visible = posts.slice(0, visibleCount);
	const hasMore = visibleCount < posts.length;

	return (
		<div>
			<div className='flex items-center justify-between mb-4'>
				<div>
					<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider'>Публікації каналу</p>
					<p className='font-bold text-sm text-gray-900 dark:text-white'>
						{total > 50 ? `50 з ${total}` : total} останніх публікацій
					</p>
				</div>
			</div>

			{/* Timeline posts */}
			<div className='ml-1'>
				{visible.map((post) => (
					<TelegramPost key={post.id} post={post} />
				))}
			</div>

			{/* Show more / collapse */}
			{hasMore && (
				<div className='flex justify-center mt-2'>
					<button
						onClick={() => setVisibleCount(prev => Math.min(prev + 5, posts.length))}
						className='inline-flex items-center gap-1.5 px-5 py-2 rounded-lg text-[12px] font-semibold text-[#3498db] bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-all'
					>
						<svg className='w-3.5 h-3.5' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='2'>
							<path strokeLinecap='round' strokeLinejoin='round' d='M19 9l-7 7-7-7' />
						</svg>
						Показати ще ({posts.length - visibleCount})
					</button>
				</div>
			)}

			{visibleCount > 3 && (
				<div className='flex justify-center mt-2'>
					<button
						onClick={() => setVisibleCount(3)}
						className='text-[11px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors'
					>
						Згорнути
					</button>
				</div>
			)}
		</div>
	);
};

export default PostsList;
