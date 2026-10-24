import { useAuth } from '../../context/AppContext';

export const ALERT_BOT_URL = 'https://t.me/tgsell_alert_bot?start=subscribe';

/** «Натисніть Start в @tgsell_alert_bot» — shown only to users the backend doesn't know as subscribed. */
const AlertBotHint = ({ className = '', text }) => {
	const { user } = useAuth();
	if (user?.alert_bot_started) return null;
	return (
		<div className={`flex flex-col sm:flex-row sm:items-center gap-3 p-4 rounded-2xl border border-accent/30 bg-accent/5 text-left ${className}`}>
			<div className='flex items-start gap-3 flex-1 min-w-0'>
				<span className='w-10 h-10 shrink-0 rounded-xl bg-accent/15 border border-accent/30 flex items-center justify-center text-lg'>🔔</span>
				<div className='min-w-0'>
					<p className='font-semibold text-sm text-gray-900 dark:text-white'>Увімкніть сповіщення</p>
					<p className='text-sm text-gray-600 dark:text-gray-400 mt-0.5'>
						{text || <>Натисніть <b className='text-gray-900 dark:text-white'>Start</b> в <b className='text-accent'>@tgsell_alert_bot</b>, щоб дізнаватися про модерацію лота, нові заявки й угоди.</>}
					</p>
				</div>
			</div>
			<a href={ALERT_BOT_URL} target='_blank' rel='noopener noreferrer'
				className='inline-flex items-center justify-center gap-2 min-h-[44px] px-5 rounded-xl bg-accent text-black font-semibold text-sm hover:brightness-110 transition-all whitespace-nowrap'>
				Відкрити бота
			</a>
		</div>
	);
};

export default AlertBotHint;
