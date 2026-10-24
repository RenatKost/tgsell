import { fmtNum } from '../../utils/money';
import { faChartLine, faListAlt, faUsers, faTrash, faArrowRight } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { formatEr } from '../../utils/er';
import { Badge, LISTING_STATUS, surface, btnSecondary, btnDanger } from '../Cabinet/ui';
import SellerServices from '../Services/SellerServices';

const CabinetCard = ({ channel, onDelete }) => {
	const status = LISTING_STATUS[channel.status] || LISTING_STATUS.pending;
	const [avatarError, setAvatarError] = useState(false);

	const formatAge = (months) => {
		if (!months) return '—';
		const m = typeof months === 'string' ? parseInt(months, 10) : months;
		if (isNaN(m)) return '—';
		const y = Math.floor(m / 12);
		const rem = m % 12;
		return y > 0 ? `${y} р. ${rem} міс.` : `${rem} міс.`;
	};

	const stats = [
		['Перегляди', channel.views_hidden ? <span className='text-amber-500' title='Приховано'>🔒</span> : (fmtNum(channel.avg_views) || '—')],
		['ER', formatEr(channel.er, channel.subscribers_count)],
		['Вік', formatAge(channel.age)],
		['Дохід/міс', channel.monthly_income ? `${fmtNum(channel.monthly_income)} $` : '—'],
	];

	return (
		<article className={`${surface} overflow-hidden flex flex-col hover:border-accent/50 transition-colors`}>
			<div className='p-4 sm:p-5'>
				<div className='flex items-start gap-3 sm:gap-4'>
					{channel.avatar_url && !avatarError ? (
						<img className='w-12 h-12 sm:w-14 sm:h-14 rounded-xl object-cover flex-shrink-0' src={channel.avatar_url} alt='' onError={() => setAvatarError(true)} />
					) : (
						<div className='w-12 h-12 sm:w-14 sm:h-14 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center text-xl font-bold text-white flex-shrink-0'>
							{channel.channel_name?.[0] || '?'}
						</div>
					)}
					<div className='flex-1 min-w-0'>
						<NavLink to={`/channel/${channel.id}`} className='font-bold text-gray-900 dark:text-white hover:text-accent leading-snug line-clamp-2 break-words' title={channel.channel_name}>
							{channel.channel_name}
						</NavLink>
						<div className='flex flex-wrap items-center gap-1.5 mt-2'>
							<Badge tone={status.tone}>{status.text}</Badge>
							{(channel.listing_type === 'auction' || channel.listing_type === 'both') && <Badge tone='orange' dot={false}>🔥 Аукціон</Badge>}
							{channel.is_closed && <Badge tone='gray' dot={false}>🔒 Закритий</Badge>}
							{channel.is_top && <Badge tone='orange' dot={false}>🚀 Топ</Badge>}
							{channel.tgsell_verified && <Badge tone='green' dot={false}>✅ Перевірено TgSell</Badge>}
						</div>
						<div className='flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-sm text-gray-500 dark:text-gray-400'>
							<span className='flex items-center gap-1'>
								<FontAwesomeIcon icon={faUsers} className='text-xs' />
								{fmtNum(channel.subscribers_count) || '0'}
							</span>
							{channel.daily_growth != null && (
								<span className={`flex items-center gap-1 ${channel.daily_growth >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500'}`}>
									<FontAwesomeIcon icon={faChartLine} className='text-xs' />
									{channel.daily_growth >= 0 ? '+' : ''}{channel.daily_growth}/день
								</span>
							)}
							{channel.category && (
								<span className='flex items-center gap-1 min-w-0'>
									<FontAwesomeIcon icon={faListAlt} className='text-xs' />
									<span className='truncate'>{channel.category}</span>
								</span>
							)}
						</div>
					</div>
				</div>
			</div>

			<dl className='grid grid-cols-2 sm:grid-cols-4 gap-px bg-gray-100 dark:bg-card-border border-y border-gray-100 dark:border-card-border'>
				{stats.map(([k, v]) => (
					<div key={k} className='bg-white dark:bg-card px-3 py-2.5 text-center'>
						<dt className='text-xs text-gray-500 dark:text-gray-400'>{k}</dt>
						<dd className='font-semibold text-gray-900 dark:text-gray-100 text-sm mt-0.5 tabular-nums'>{v}</dd>
					</div>
				))}
			</dl>

			<div className='p-4 sm:p-5 mt-auto'>
				{channel.rejection_reason && (
					<p className='mb-3 px-3 py-2 text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20 rounded-xl border border-red-100 dark:border-red-900/40'>
						<span className='font-semibold'>Причина відхилення:</span> {channel.rejection_reason}
					</p>
				)}
				<div className='flex items-center justify-between gap-3'>
					<div className='min-w-0'>
						<p className='text-xs text-gray-500 dark:text-gray-400'>Ціна</p>
						<p className='text-lg font-bold text-gray-900 dark:text-white tabular-nums'>
							{fmtNum(channel.price)} <span className='text-sm text-gray-500 dark:text-accent'>USDT</span>
						</p>
					</div>
					<div className='flex items-center gap-2'>
						{onDelete && channel.status !== 'sold' && (
							<button type='button' onClick={() => onDelete(channel.id)} className={btnDanger} title='Видалити оголошення' aria-label='Видалити оголошення'>
								<FontAwesomeIcon icon={faTrash} size='sm' />
							</button>
						)}
						<NavLink to={`/channel/${channel.id}`} className={btnSecondary}>
							Деталі
							<FontAwesomeIcon icon={faArrowRight} size='xs' />
						</NavLink>
					</div>
				</div>
			</div>
			{onDelete && <SellerServices channel={channel} />}
		</article>
	);
};

export default CabinetCard;
