import { dealBotBannerCopy, dealBotBannerHint, alertBotUsername } from '../../utils/dealBotBanner';

/** Premium, mobile-friendly prompt to start @tgsell_alert_bot for deal notifications. */
const DealBotNotifyBanner = ({ tgNotify }) => {
	const bot = alertBotUsername(tgNotify);
	const hint = dealBotBannerHint(tgNotify);
	const urgent = Boolean(tgNotify?.bot_unreachable);
	return (
		<div
			role='status'
			className={`rounded-2xl p-4 mb-4 flex flex-col sm:flex-row sm:items-center gap-3 border ${
				urgent
					? 'bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-100'
					: 'bg-accent/5 border-accent/30 text-gray-900 dark:text-white'
			}`}
		>
			<div className='flex items-start gap-3 flex-1 min-w-0'>
				<span
					className={`w-10 h-10 shrink-0 rounded-xl flex items-center justify-center text-lg border ${
						urgent
							? 'bg-amber-100 dark:bg-amber-900/50 border-amber-200 dark:border-amber-800'
							: 'bg-accent/15 border-accent/30'
					}`}
					aria-hidden='true'
				>
					🔔
				</span>
				<div className='min-w-0'>
					<p className='font-semibold text-sm'>{dealBotBannerCopy(tgNotify)}</p>
					{hint && (
						<p className='text-sm mt-0.5 text-gray-600 dark:text-gray-400'>{hint}</p>
					)}
				</div>
			</div>
			<a
				href={tgNotify.deep_link}
				target='_blank'
				rel='noopener noreferrer'
				className='inline-flex items-center justify-center gap-2 shrink-0 min-h-[44px] px-5 rounded-xl bg-accent text-black font-semibold text-sm hover:brightness-110 transition-all whitespace-nowrap text-center'
			>
				Запустити @{bot}
			</a>
		</div>
	);
};

export default DealBotNotifyBanner;
