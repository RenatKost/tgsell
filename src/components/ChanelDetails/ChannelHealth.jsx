import { useEffect, useState } from 'react';
import { channelsAPI } from '../../services/api';

const SCORE_CONFIG = {
	healthy: { bg: 'bg-emerald-500', ring: 'ring-emerald-200 dark:ring-emerald-900', text: 'text-emerald-600 dark:text-emerald-400', bgLight: 'bg-emerald-50 dark:bg-emerald-900/20' },
	suspicious: { bg: 'bg-amber-500', ring: 'ring-amber-200 dark:ring-amber-900', text: 'text-amber-600 dark:text-amber-400', bgLight: 'bg-amber-50 dark:bg-amber-900/20' },
	dead: { bg: 'bg-red-500', ring: 'ring-red-200 dark:ring-red-900', text: 'text-red-600 dark:text-red-400', bgLight: 'bg-red-50 dark:bg-red-900/20' },
};

const getScoreStyle = (score) => {
	if (score >= 70) return SCORE_CONFIG.healthy;
	if (score >= 40) return SCORE_CONFIG.suspicious;
	return SCORE_CONFIG.dead;
};

const ChannelHealth = ({ channelId }) => {
	const [health, setHealth] = useState(null);
	const [loading, setLoading] = useState(true);

	useEffect(() => {
		const fetch = async () => {
			try {
				const { data } = await channelsAPI.getHealth(channelId);
				setHealth(data);
			} catch {
				setHealth(null);
			} finally {
				setLoading(false);
			}
		};
		fetch();
	}, [channelId]);

	if (loading) {
		return (
			<div className='bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm p-4'>
				<div className='flex items-center gap-3'>
					<div className='w-14 h-14 rounded-full bg-gray-100 dark:bg-slate-700 animate-pulse' />
					<div className='space-y-2 flex-1'>
						<div className='h-4 bg-gray-100 dark:bg-slate-700 rounded animate-pulse w-32' />
						<div className='h-3 bg-gray-100 dark:bg-slate-700 rounded animate-pulse w-48' />
					</div>
				</div>
			</div>
		);
	}

	if (!health) return null;

	const style = getScoreStyle(health.health_score);
	const circumference = 2 * Math.PI * 28;
	const strokeDashoffset = circumference - (health.health_score / 100) * circumference;

	return (
		<div className='bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 shadow-sm p-4'>
			<h4 className='font-semibold text-sm text-gray-900 dark:text-white mb-3 flex items-center gap-2'>
				<span>🔍</span> Аналіз живучості каналу
			</h4>

			{/* Score circle + label */}
			<div className='flex items-center gap-4 mb-4'>
				<div className='relative w-16 h-16 flex-shrink-0'>
					<svg className='w-16 h-16 -rotate-90' viewBox='0 0 64 64'>
						<circle cx='32' cy='32' r='28' stroke='currentColor' strokeWidth='4' fill='none'
							className='text-gray-100 dark:text-slate-700' />
						<circle cx='32' cy='32' r='28' strokeWidth='4' fill='none'
							className={style.text}
							stroke='currentColor'
							strokeLinecap='round'
							strokeDasharray={circumference}
							strokeDashoffset={strokeDashoffset}
							style={{ transition: 'stroke-dashoffset 1s ease-out' }}
						/>
					</svg>
					<div className='absolute inset-0 flex items-center justify-center'>
						<span className={`text-sm font-bold ${style.text}`}>{health.health_score}</span>
					</div>
				</div>
				<div>
					<p className={`text-sm font-bold ${style.text}`}>{health.health_label}</p>
					<p className='text-gray-400 dark:text-gray-500 text-xs'>
						Проаналізовано {health.posts_analyzed} постів
					</p>
				</div>
			</div>

			{/* Metrics grid */}
			<div className='grid grid-cols-2 gap-2 mb-3'>
				{/* View velocity */}
				<div className='bg-gray-50 dark:bg-slate-700/60 rounded-xl p-3'>
					<p className='text-gray-400 dark:text-gray-500 text-xs mb-1'>Швидкість переглядів</p>
					<p className={`font-bold text-sm ${
						health.view_velocity_label === 'Накрутка' ? 'text-red-500' :
						health.view_velocity_label === 'Підозріло' ? 'text-amber-500' :
						health.view_velocity_label === 'Нормально' ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-500'
					}`}>
						{health.view_velocity_label}
					</p>
					{health.views_1h_ratio != null && (
						<p className='text-gray-400 text-xs mt-0.5'>{health.views_1h_ratio}% за 1 год</p>
					)}
				</div>

				{/* Activity */}
				<div className='bg-gray-50 dark:bg-slate-700/60 rounded-xl p-3'>
					<p className='text-gray-400 dark:text-gray-500 text-xs mb-1'>Активність</p>
					<p className={`font-bold text-sm ${
						health.activity_label === 'Мертвий канал' ? 'text-red-500' :
						health.activity_label === 'Низька активність' ? 'text-amber-500' :
						health.activity_label === 'Високий охват' ? 'text-emerald-600 dark:text-emerald-400' :
						health.activity_label === 'Нормальна активність' ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-500'
					}`}>
						{health.activity_label}
					</p>
					{health.views_to_subs_ratio != null && (
						<p className='text-gray-400 text-xs mt-0.5'>{health.views_to_subs_ratio}% охват</p>
					)}
				</div>

				{/* ER */}
				<div className='bg-gray-50 dark:bg-slate-700/60 rounded-xl p-3'>
					<p className='text-gray-400 dark:text-gray-500 text-xs mb-1'>ER</p>
					<p className={`font-bold text-sm ${
						health.er_label === 'Дуже низький' ? 'text-red-500' :
						health.er_label === 'Підозріло високий' ? 'text-amber-500' :
						health.er_label === 'Нормальний' || health.er_label === 'Високий' ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-500'
					}`}>
						{health.er_label}
					</p>
					{health.er != null && (
						<p className='text-gray-400 text-xs mt-0.5'>{health.er}%</p>
					)}
				</div>

				{/* Suspicious posts */}
				<div className='bg-gray-50 dark:bg-slate-700/60 rounded-xl p-3'>
					<p className='text-gray-400 dark:text-gray-500 text-xs mb-1'>Підозрілі пости</p>
					<p className={`font-bold text-sm ${
						health.suspicious_posts > 0 ? 'text-red-500' : 'text-emerald-600 dark:text-emerald-400'
					}`}>
						{health.suspicious_posts} / {health.posts_analyzed}
					</p>
				</div>
			</div>

			{/* Flags */}
			{health.flags && health.flags.length > 0 && (
				<div className='space-y-2'>
					{health.flags.map((flag, i) => (
						<div key={i} className={`px-3 py-2 rounded-xl text-sm ${
							flag.startsWith('✅') ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400' :
							flag.startsWith('💀') || flag.startsWith('⚠️') ? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400' :
							'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400'
						}`}>
							{flag}
						</div>
					))}
				</div>
			)}
		</div>
	);
};

export default ChannelHealth;
