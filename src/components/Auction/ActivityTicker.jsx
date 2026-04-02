import { useState, useEffect, useRef } from 'react';
import { activityAPI } from '../../services/api';

const ActivityTicker = () => {
	const [events, setEvents] = useState([]);
	const scrollRef = useRef(null);

	useEffect(() => {
		const load = async () => {
			try {
				const { data } = await activityAPI.getFeed();
				setEvents(data);
			} catch (err) {
				console.error('Failed to load activity feed:', err);
			}
		};
		load();
		const interval = setInterval(load, 30000);
		return () => clearInterval(interval);
	}, []);

	// Auto-scroll animation
	useEffect(() => {
		const el = scrollRef.current;
		if (!el || events.length === 0) return;

		let animFrame;
		let pos = 0;
		const speed = 0.5;

		const animate = () => {
			pos += speed;
			if (pos >= el.scrollWidth / 2) pos = 0;
			el.scrollLeft = pos;
			animFrame = requestAnimationFrame(animate);
		};

		animFrame = requestAnimationFrame(animate);
		return () => cancelAnimationFrame(animFrame);
	}, [events]);

	if (events.length === 0) return null;

	// Duplicate for seamless loop
	const displayEvents = [...events, ...events];

	const timeAgo = (isoStr) => {
		const diff = Date.now() - new Date(isoStr).getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 1) return 'щойно';
		if (mins < 60) return `${mins} хв тому`;
		const hours = Math.floor(mins / 60);
		if (hours < 24) return `${hours} год тому`;
		return `${Math.floor(hours / 24)} д тому`;
	};

	return (
		<div className='mb-8 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-2xl shadow-sm overflow-hidden'>
			<div className='flex items-center gap-3 px-5 py-3 border-b border-gray-100 dark:border-slate-700'>
				<span className='flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200 whitespace-nowrap'>
					<span className='w-2 h-2 rounded-full bg-green-500 animate-pulse' />
					Активність
				</span>
				<span className='text-xs text-gray-400 dark:text-gray-500'>в реальному часі</span>
			</div>
			<div className='relative overflow-hidden'>
				<div className='absolute left-0 top-0 bottom-0 w-10 bg-gradient-to-r from-white dark:from-slate-800 to-transparent z-10 pointer-events-none' />
				<div className='absolute right-0 top-0 bottom-0 w-10 bg-gradient-to-l from-white dark:from-slate-800 to-transparent z-10 pointer-events-none' />
				<div
					ref={scrollRef}
					className='flex gap-3 overflow-hidden whitespace-nowrap px-4 py-3'
					style={{ scrollBehavior: 'auto' }}
				>
					{displayEvents.map((event, i) => (
						<div
							key={i}
							className='inline-flex items-center gap-2 bg-gray-50 dark:bg-slate-700/60 border border-gray-100 dark:border-slate-600 rounded-full px-4 py-2 text-sm flex-shrink-0'
						>
							<span className='text-gray-800 dark:text-gray-200'>{event.text}</span>
							<span className='text-xs text-gray-400 dark:text-gray-500'>
								{timeAgo(event.created_at)}
							</span>
						</div>
					))}
				</div>
			</div>
		</div>
	);
};

export default ActivityTicker;
