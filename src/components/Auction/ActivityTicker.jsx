import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { activityAPI } from '../../services/api';

const EVENT_CONFIG = {
	deal_completed: {
		borderClass: 'border-l-accent',
		glowStyle: '0 0 12px rgba(0,255,136,0.35)',
		badgeClass: 'bg-accent/10 text-accent',
		dotClass: 'bg-accent',
		icon: '💰',
		label: 'Угода',
	},
	auction_bid: {
		borderClass: 'border-l-orange-400',
		glowStyle: '0 0 12px rgba(251,146,60,0.4)',
		badgeClass: 'bg-orange-500/10 text-orange-400',
		dotClass: 'bg-orange-400',
		icon: '🔥',
		label: 'Ставка',
	},
	new_channel: {
		borderClass: 'border-l-cyan-400',
		glowStyle: '0 0 12px rgba(34,211,238,0.3)',
		badgeClass: 'bg-cyan-400/10 text-cyan-400',
		dotClass: 'bg-cyan-400',
		icon: '📊',
		label: 'Канал',
	},
	new_user: {
		borderClass: 'border-l-violet-400',
		glowStyle: '0 0 12px rgba(167,139,250,0.3)',
		badgeClass: 'bg-violet-400/10 text-violet-400',
		dotClass: 'bg-violet-400',
		icon: '👤',
		label: 'Юзер',
	},
};

const timeAgo = (isoStr) => {
	const diff = Date.now() - new Date(isoStr).getTime();
	const mins = Math.floor(diff / 60000);
	if (mins < 1) return 'щойно';
	if (mins < 60) return `${mins} хв`;
	const h = Math.floor(mins / 60);
	if (h < 24) return `${h} год`;
	return `${Math.floor(h / 24)} д`;
};

const cleanText = (text) => text.replace(/^.\s/, '');

const ActivityTicker = () => {
	const [events, setEvents] = useState([]);
	const [newIds, setNewIds] = useState(new Set());
	const [flashPulse, setFlashPulse] = useState(false);
	const prevKeys = useRef(new Set());

	const load = async () => {
		try {
			const { data } = await activityAPI.getFeed();
			const keys = new Set(data.map((e, i) => `${e.created_at}${i}`));
			const isFirstLoad = prevKeys.current.size === 0;

			if (!isFirstLoad) {
				const added = new Set();
				data.forEach((e, i) => {
					const k = `${e.created_at}${i}`;
					if (!prevKeys.current.has(k)) added.add(i);
				});
				if (added.size > 0) {
					setNewIds(added);
					setFlashPulse(true);
					setTimeout(() => { setNewIds(new Set()); setFlashPulse(false); }, 3000);
				}
			}
			prevKeys.current = keys;
			setEvents(data);
		} catch {
			// silent
		}
	};

	useEffect(() => {
		load();
		const iv = setInterval(load, 30000);
		return () => clearInterval(iv);
	}, []);

	if (events.length === 0) return null;

	const counts = events.reduce((acc, e) => {
		acc[e.type] = (acc[e.type] || 0) + 1;
		return acc;
	}, {});

	const visible = events.slice(0, 7);

	return (
		<div className='mb-8 relative'>
			{/* Top neon scan-line */}
			<motion.div
				className='absolute inset-x-0 top-0 h-px z-10 pointer-events-none'
				style={{ background: 'linear-gradient(90deg, transparent 0%, #00FF88 50%, transparent 100%)' }}
				animate={{ opacity: [0.15, 0.55, 0.15] }}
				transition={{ repeat: Infinity, duration: 3.5, ease: 'easeInOut' }}
			/>

			<div
				className='bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border shadow-sm overflow-hidden transition-shadow duration-700'
				style={flashPulse ? { boxShadow: '0 0 40px rgba(0,255,136,0.12), 0 0 15px rgba(0,255,136,0.08)' } : {}}
			>
				{/* Header */}
				<div className='flex items-center justify-between px-5 py-3 border-b border-gray-100 dark:border-card-border'>
					<div className='flex items-center gap-3'>
						{/* Live badge */}
						<div className='flex items-center gap-1.5 bg-accent/10 px-2.5 py-1 rounded-full'>
							<motion.span
								className='block w-1.5 h-1.5 rounded-full bg-accent'
								animate={{ opacity: [1, 0.2, 1], scale: [1, 0.7, 1] }}
								transition={{ repeat: Infinity, duration: 1.4 }}
							/>
							<span className='text-[10px] font-black text-accent tracking-widest uppercase'>Live</span>
						</div>
						<span className='text-sm font-semibold text-gray-800 dark:text-white'>Активність платформи</span>
					</div>
					<div className='flex items-center gap-2'>
						<span className='text-xs text-gray-400'>{events.length} подій</span>
						<motion.div
							className='w-1.5 h-1.5 rounded-full bg-gray-300 dark:bg-gray-600'
							animate={{ opacity: [0.3, 1, 0.3] }}
							transition={{ repeat: Infinity, duration: 2.2 }}
						/>
					</div>
				</div>

				{/* Body */}
				<div className='flex divide-x divide-gray-100 dark:divide-card-border'>

					{/* Feed column */}
					<div className='flex-1 min-w-0 p-3 space-y-1.5'>
						<AnimatePresence initial={false} mode='popLayout'>
							{visible.map((event, i) => {
								const cfg = EVENT_CONFIG[event.type] ?? EVENT_CONFIG.new_user;
								const isNew = newIds.has(i);
								return (
									<motion.div
										key={`${event.created_at}-${i}`}
										layout
										initial={{ opacity: 0, x: -24 }}
										animate={{
											opacity: 1,
											x: 0,
											boxShadow: isNew ? cfg.glowStyle : 'none',
										}}
										exit={{ opacity: 0, x: -16, height: 0 }}
										transition={{ duration: 0.3, delay: i * 0.04 }}
										className={`flex items-center gap-3 pl-3 pr-2.5 py-2 rounded-r-lg border-l-2 ${cfg.borderClass} bg-gray-50 dark:bg-card-inner transition-shadow duration-700`}
									>
										<span className='text-base flex-shrink-0 leading-none'>{cfg.icon}</span>
										<span className='flex-1 text-xs text-gray-700 dark:text-gray-300 truncate'>
											{cleanText(event.text)}
										</span>
										<div className='flex items-center gap-1.5 flex-shrink-0'>
											{isNew && (
												<motion.span
													initial={{ scale: 0 }}
													animate={{ scale: 1 }}
													className='text-[9px] font-black text-accent bg-accent/10 px-1.5 py-0.5 rounded-full uppercase tracking-wider'
												>
													New
												</motion.span>
											)}
											<span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${cfg.badgeClass}`}>
												{timeAgo(event.created_at)}
											</span>
										</div>
									</motion.div>
								);
							})}
						</AnimatePresence>
					</div>

					{/* Stats column */}
					<div className='w-36 flex-shrink-0 p-3 flex flex-col gap-2'>
						<p className='text-[10px] font-bold uppercase tracking-wider text-gray-400'>За сьогодні</p>
						{[
							{ key: 'deal_completed', label: 'Угоди' },
							{ key: 'auction_bid',   label: 'Ставки' },
							{ key: 'new_channel',   label: 'Канали' },
							{ key: 'new_user',      label: 'Юзери' },
						].map(({ key, label }) => {
							const cfg = EVENT_CONFIG[key];
							const count = counts[key] || 0;
							const maxCount = Math.max(...Object.values(counts), 1);
							const pct = Math.round((count / maxCount) * 100);
							return (
								<div key={key} className={`px-2.5 py-2 rounded-lg bg-gray-50 dark:bg-card-inner border-l-2 ${cfg.borderClass}`}>
									<div className='flex items-center justify-between mb-1'>
										<p className='text-[10px] text-gray-400'>{label}</p>
										<motion.span
											key={count}
											initial={{ scale: 1.5, opacity: 0 }}
											animate={{ scale: 1, opacity: 1 }}
											className={`font-black text-sm ${cfg.badgeClass.split(' ')[1]}`}
										>
											{count}
										</motion.span>
									</div>
									<div className='h-1 rounded-full bg-gray-200 dark:bg-card overflow-hidden'>
										<motion.div
											className={`h-full rounded-full ${cfg.dotClass}`}
											initial={{ width: 0 }}
											animate={{ width: `${pct}%` }}
											transition={{ duration: 0.8, ease: 'easeOut' }}
										/>
									</div>
								</div>
							);
						})}
					</div>
				</div>

				{/* Bottom ticker — scrolling latest events */}
				<BottomTicker events={events} />
			</div>
		</div>
	);
};

/* Thin auto-scrolling ticker at the bottom */
const BottomTicker = ({ events }) => {
	const ref = useRef(null);
	const posRef = useRef(0);
	const rafRef = useRef(null);

	useEffect(() => {
		const el = ref.current;
		if (!el || events.length === 0) return;
		const speed = 0.4;
		const step = () => {
			posRef.current += speed;
			if (posRef.current >= el.scrollWidth / 2) posRef.current = 0;
			el.scrollLeft = posRef.current;
			rafRef.current = requestAnimationFrame(step);
		};
		rafRef.current = requestAnimationFrame(step);
		return () => cancelAnimationFrame(rafRef.current);
	}, [events]);

	const doubled = [...events, ...events];

	return (
		<div className='border-t border-gray-100 dark:border-card-border relative overflow-hidden'>
			{/* Edge fades */}
			<div className='absolute left-0 top-0 bottom-0 w-8 bg-gradient-to-r from-white dark:from-card to-transparent z-10 pointer-events-none' />
			<div className='absolute right-0 top-0 bottom-0 w-8 bg-gradient-to-l from-white dark:from-card to-transparent z-10 pointer-events-none' />
			<div
				ref={ref}
				className='flex gap-2 overflow-hidden whitespace-nowrap px-3 py-2'
				style={{ scrollBehavior: 'auto' }}
			>
				{doubled.map((e, i) => {
					const cfg = EVENT_CONFIG[e.type] ?? EVENT_CONFIG.new_user;
					return (
						<span
							key={i}
							className={`inline-flex items-center gap-1.5 text-[10px] font-medium px-2.5 py-1 rounded-full bg-gray-50 dark:bg-card-inner border border-gray-100 dark:border-card-border flex-shrink-0 text-gray-600 dark:text-gray-400`}
						>
							<span className={`w-1 h-1 rounded-full flex-shrink-0 ${cfg.dotClass}`} />
							{cleanText(e.text)}
						</span>
					);
				})}
			</div>
		</div>
	);
};

export default ActivityTicker;

