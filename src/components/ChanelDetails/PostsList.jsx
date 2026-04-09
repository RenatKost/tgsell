import { useEffect, useState } from 'react';
import { channelsAPI } from '../../services/api';

const mediaIcons = {
	photo: '🖼',
	video: '🎥',
	document: '📄',
	audio: '🎵',
	voice: '🎤',
};

const accentColors = [
	'border-l-cyan-400',
	'border-l-pink-400',
	'border-l-emerald-400',
	'border-l-orange-400',
	'border-l-violet-400',
	'border-l-amber-400',
];

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

const PostCard = ({ post, index }) => {
	const accent = accentColors[index % accentColors.length];

	return (
		<div className={`bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 border-l-[3px] ${accent} p-3.5 hover:shadow-md transition-all duration-200`}>
			{/* Header */}
			<div className='flex items-center justify-between mb-2'>
				<span className='text-[10px] text-gray-400 font-medium'>{formatDate(post.date)}</span>
				<div className='flex items-center gap-1.5'>
					{post.media_type && (
						<span className='text-[10px] font-medium px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-500 dark:text-blue-400'>
							{mediaIcons[post.media_type] || '📎'} {post.media_type}
						</span>
					)}
					{post.link && (
						<a href={`https://${post.link}`} target='_blank' rel='noopener noreferrer'
							className='text-[10px] text-[#3498db] hover:underline font-medium'>↗</a>
					)}
				</div>
			</div>

			{/* Text */}
			{post.text && (
				<p className='text-xs text-gray-600 dark:text-gray-300 line-clamp-4 mb-2.5 leading-relaxed'>{post.text}</p>
			)}

			{/* Stats */}
			<div className='flex items-center gap-3 pt-2 border-t border-gray-50 dark:border-slate-700/50'>
				<span className='flex items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400'>
					<svg className='w-3 h-3' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='2'>
						<path strokeLinecap='round' strokeLinejoin='round' d='M15 12a3 3 0 11-6 0 3 3 0 016 0z' />
						<path strokeLinecap='round' strokeLinejoin='round' d='M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z' />
					</svg>
					<span className='font-semibold'>{formatNum(post.views)}</span>
				</span>
				{post.reactions > 0 && (
					<span className='text-[11px] text-gray-500 dark:text-gray-400'>❤️ <span className='font-semibold'>{formatNum(post.reactions)}</span></span>
				)}
				{post.forwards > 0 && (
					<span className='text-[11px] text-gray-500 dark:text-gray-400'>↗ <span className='font-semibold'>{formatNum(post.forwards)}</span></span>
				)}
				{post.comments > 0 && (
					<span className='text-[11px] text-gray-500 dark:text-gray-400'>💬 <span className='font-semibold'>{formatNum(post.comments)}</span></span>
				)}
			</div>

			{/* View dynamics */}
			{(post.views_1h != null || post.views_12h != null || post.views_24h != null || post.views_48h != null) && (
				<div className='flex flex-wrap gap-1 mt-2'>
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
	);
};

const PostsList = ({ channelId }) => {
	const [posts, setPosts] = useState([]);
	const [total, setTotal] = useState(0);
	const [loading, setLoading] = useState(true);
	const [page, setPage] = useState(0);
	const limit = 20;

	useEffect(() => {
		const fetch = async () => {
			setLoading(true);
			try {
				const { data } = await channelsAPI.getPosts(channelId, { limit, offset: page * limit });
				setPosts(data.items || []);
				setTotal(data.total || 0);
			} catch {
				setPosts([]);
			} finally {
				setLoading(false);
			}
		};
		fetch();
	}, [channelId, page]);

	if (loading && posts.length === 0) {
		return (
			<div className='bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm p-4'>
				<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-3'>Публікації каналу</p>
				<div className='flex justify-center py-6'>
					<div className='animate-spin rounded-full h-5 w-5 border-2 border-gray-200 border-t-[#3498db]' />
				</div>
			</div>
		);
	}

	if (!posts.length) {
		return (
			<div className='bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm p-4'>
				<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>Публікації каналу</p>
				<p className='text-gray-300 dark:text-gray-600 text-center py-6 text-xs'>Дані поки відсутні</p>
			</div>
		);
	}

	const totalPages = Math.ceil(total / limit);

	return (
		<div>
			<div className='flex items-center justify-between mb-3'>
				<div>
					<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider'>Публікації каналу</p>
					<p className='font-bold text-sm text-gray-900 dark:text-white'>{total} публікацій</p>
				</div>
			</div>

			<div className='grid md:grid-cols-2 gap-3'>
				{posts.map((post, idx) => (
					<PostCard key={post.id} post={post} index={idx} />
				))}
			</div>

			{totalPages > 1 && (
				<div className='flex items-center justify-center gap-2 mt-4'>
					<button
						onClick={() => setPage(p => Math.max(0, p - 1))}
						disabled={page === 0}
						className='px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-white dark:bg-slate-800 border border-gray-100 dark:border-slate-700 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all'
					>
						← Назад
					</button>
					<span className='text-[11px] text-gray-400 font-medium'>
						{page + 1} / {totalPages}
					</span>
					<button
						onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
						disabled={page >= totalPages - 1}
						className='px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-white dark:bg-slate-800 border border-gray-100 dark:border-slate-700 text-gray-500 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-all'
					>
						Далі →
					</button>
				</div>
			)}
		</div>
	);
};

export default PostsList;
