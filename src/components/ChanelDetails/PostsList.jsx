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
		<div className='bg-white dark:bg-card-inner rounded-xl border border-gray-100 dark:border-card-border overflow-hidden hover:border-accent/30 transition-all'>
			{/* Header: date + media + link */}
			<div className='flex items-center justify-between px-3.5 py-2 border-b border-gray-50 dark:border-card-border/50'>
				<span className='text-[10px] text-gray-400 font-medium'>{formatDate(post.date)}</span>
				<div className='flex items-center gap-2'>
					{post.media_type && (
						<span className='text-[9px] font-medium px-1.5 py-0.5 rounded bg-gray-50 dark:bg-card-hover text-gray-400'>
							{mediaIcons[post.media_type] || '📎'} {post.media_type}
						</span>
					)}
					{post.link && (
						<a href={`https://${post.link}`} target='_blank' rel='noopener noreferrer'
							className='text-[10px] text-accent hover:underline font-medium'>↗ цього</a>
					)}
				</div>
			</div>

			{/* Text body */}
			<div className='px-3.5 py-2.5'>
				{post.text ? (
					<>
						<p className={`text-[12px] text-gray-700 dark:text-gray-200 leading-relaxed whitespace-pre-wrap ${!expanded && longText ? 'line-clamp-4' : ''}`}>
							{post.text}
						</p>
						{longText && (
							<button
								onClick={() => setExpanded(!expanded)}
								className='text-accent text-[11px] font-medium mt-1 hover:underline'
							>
								{expanded ? 'Згорнути' : 'Читати далі...'}
							</button>
						)}
					</>
				) : (
					<p className='text-[12px] text-gray-400 dark:text-gray-500 italic'>Медіа-контент</p>
				)}
			</div>

			{/* Stats footer */}
			<div className='flex items-center justify-between px-3.5 py-2 border-t border-gray-50 dark:border-card-border/50'>
				<div className='flex items-center gap-3'>
					<span className='flex items-center gap-1 text-[11px] text-gray-400'>
						<svg className='w-3.5 h-3.5' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth='1.5'>
							<path strokeLinecap='round' strokeLinejoin='round' d='M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z' />
							<path strokeLinecap='round' strokeLinejoin='round' d='M15 12a3 3 0 11-6 0 3 3 0 016 0z' />
						</svg>
						<span className='font-medium'>{formatNum(post.views)}</span>
					</span>
					{post.reactions > 0 && (
						<span className='flex items-center gap-0.5 text-[11px] text-gray-400'>
							❤️ <span className='font-medium'>{formatNum(post.reactions)}</span>
						</span>
					)}
					{post.forwards > 0 && (
						<span className='flex items-center gap-0.5 text-[11px] text-gray-400'>
							↗ <span className='font-medium'>{formatNum(post.forwards)}</span>
						</span>
					)}
					{post.comments > 0 && (
						<span className='flex items-center gap-0.5 text-[11px] text-gray-400'>
							💬 <span className='font-medium'>{formatNum(post.comments)}</span>
						</span>
					)}
				</div>
				<span className='text-[10px] text-gray-500 italic'>Pending analysis...</span>
			</div>
		</div>
	);
};

const POSTS_PER_PAGE = 10;

const PostsList = ({ channelId }) => {
	const [posts, setPosts] = useState([]);
	const [total, setTotal] = useState(0);
	const [loading, setLoading] = useState(true);
	const [page, setPage] = useState(1);
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
			<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm p-4'>
				<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-3'>Публікації каналу</p>
				<div className='flex justify-center py-6'>
					<div className='animate-spin rounded-full h-5 w-5 border-2 border-gray-200 dark:border-card-border border-t-accent' />
				</div>
			</div>
		);
	}

	if (!posts.length) {
		return (
			<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm p-4'>
				<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider mb-1'>Публікації каналу</p>
				<p className='text-gray-300 dark:text-gray-600 text-center py-6 text-xs'>Дані поки відсутні</p>
			</div>
		);
	}

	const totalPages = Math.ceil(posts.length / POSTS_PER_PAGE);
	const startIdx = (page - 1) * POSTS_PER_PAGE;
	const visible = posts.slice(startIdx, startIdx + POSTS_PER_PAGE);

	// Build page numbers array: 1 ... 3 4 5 ... 10
	const getPages = () => {
		const pages = [];
		for (let i = 1; i <= totalPages; i++) {
			if (i === 1 || i === totalPages || (i >= page - 1 && i <= page + 1)) {
				pages.push(i);
			} else if (pages[pages.length - 1] !== '...') {
				pages.push('...');
			}
		}
		return pages;
	};

	return (
		<div className='bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm p-4'>
			<div className='flex items-center justify-between mb-4'>
				<div>
					<p className='text-[10px] text-gray-400 font-semibold uppercase tracking-wider'>Публікації каналу</p>
					<p className='font-bold text-sm text-gray-900 dark:text-white'>
						{total} публікацій
					</p>
				</div>

				{/* Pagination */}
				{totalPages > 1 && (
					<div className='flex items-center gap-1'>
						{getPages().map((p, idx) =>
							p === '...' ? (
								<span key={`ellipsis-${idx}`} className='px-1.5 text-gray-500 text-xs'>…</span>
							) : (
								<button
									key={p}
									onClick={() => setPage(p)}
									className={`w-7 h-7 rounded-lg text-xs font-medium transition-all ${
										page === p
											? 'bg-accent text-white'
											: 'bg-gray-50 dark:bg-card-inner text-gray-400 hover:bg-gray-100 dark:hover:bg-card-hover'
									}`}
								>
									{p}
								</button>
							)
						)}
					</div>
				)}
			</div>

			{/* 2-column grid of post cards */}
			<div className='grid md:grid-cols-2 gap-3'>
				{visible.map((post) => (
					<TelegramPost key={post.id} post={post} />
				))}
			</div>

			{/* Bottom pagination */}
			{totalPages > 1 && (
				<div className='flex items-center justify-center gap-1 mt-4 pt-3 border-t border-gray-100 dark:border-card-border'>
					<button
						onClick={() => setPage(p => Math.max(1, p - 1))}
						disabled={page === 1}
						className='w-7 h-7 rounded-lg text-xs text-gray-400 hover:bg-gray-100 dark:hover:bg-card-hover disabled:opacity-30 transition-all'
					>
						‹
					</button>
					{getPages().map((p, idx) =>
						p === '...' ? (
							<span key={`ellipsis-b-${idx}`} className='px-1.5 text-gray-500 text-xs'>…</span>
						) : (
							<button
								key={p}
								onClick={() => setPage(p)}
								className={`w-7 h-7 rounded-lg text-xs font-medium transition-all ${
									page === p
										? 'bg-accent text-white'
										: 'bg-gray-50 dark:bg-card-inner text-gray-400 hover:bg-gray-100 dark:hover:bg-card-hover'
								}`}
							>
								{p}
							</button>
						)
					)}
					<button
						onClick={() => setPage(p => Math.min(totalPages, p + 1))}
						disabled={page === totalPages}
						className='w-7 h-7 rounded-lg text-xs text-gray-400 hover:bg-gray-100 dark:hover:bg-card-hover disabled:opacity-30 transition-all'
					>
						›
					</button>
				</div>
			)}
		</div>
	);
};

export default PostsList;
