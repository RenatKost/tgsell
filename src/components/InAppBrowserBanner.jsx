import { useState } from 'react';
import { chromeIntentUrl, isAndroid, isInAppBrowser, isIOS } from '../utils/inAppBrowser';

const DISMISS_KEY = 'tg_inapp_banner_dismissed';

const copyText = async (text) => {
	try {
		await navigator.clipboard.writeText(text);
		return true;
	} catch {
		try {
			const ta = document.createElement('textarea');
			ta.value = text;
			ta.style.position = 'fixed';
			ta.style.opacity = '0';
			document.body.appendChild(ta);
			ta.select();
			const ok = document.execCommand('copy');
			document.body.removeChild(ta);
			return ok;
		} catch { return false; }
	}
};

// Shown only inside in-app browsers (Instagram, Facebook, TikTok…): login works reliably only in a real browser.
const InAppBrowserBanner = () => {
	const [hidden, setHidden] = useState(() => {
		try { return sessionStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
	});
	const [copied, setCopied] = useState(false);
	if (hidden || !isInAppBrowser()) return null;

	const href = window.location.href;
	const android = isAndroid();
	const ios = isIOS();

	const onCopy = async () => {
		const ok = await copyText(href);
		setCopied(ok ? 'ok' : 'fail');
		setTimeout(() => setCopied(false), 2500);
	};
	const onClose = () => {
		try { sessionStorage.setItem(DISMISS_KEY, '1'); } catch { /* ignore */ }
		setHidden(true);
	};

	return (
		<div data-inapp-banner className='fixed bottom-0 inset-x-0 z-[60] p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]'>
			<div className='max-w-md mx-auto rounded-2xl border border-accent/30 bg-white dark:bg-slate-900 shadow-2xl p-4 text-sm'>
				<div className='flex items-start justify-between gap-3 mb-2'>
					<p className='font-bold text-gray-900 dark:text-white'>Відкрити в браузері</p>
					<button onClick={onClose} aria-label='Закрити' className='text-gray-400 hover:text-gray-600 -mt-1 text-lg leading-none'>×</button>
				</div>
				<p className='text-gray-500 dark:text-gray-400 mb-3'>
					Вбудований браузер застосунку блокує вхід через Telegram і Google. Відкрийте сайт у звичайному браузері.
				</p>
				{ios && (
					<p className='text-gray-600 dark:text-gray-300 mb-3'>
						Натисніть <b>…</b> (або <b>⋯</b>) у правому верхньому куті → <b>«Відкрити в Safari»</b> / <b>«Відкрити в браузері»</b>.
					</p>
				)}
				{!ios && !android && (
					<p className='text-gray-600 dark:text-gray-300 mb-3'>
						Натисніть <b>⋮</b> у куті екрана → <b>«Відкрити в браузері»</b>, або скопіюйте посилання.
					</p>
				)}
				<div className='flex gap-2'>
					{android && (
						<a href={chromeIntentUrl(href)} className='flex-1 text-center bg-accent text-black font-bold py-2.5 rounded-xl'>
							Відкрити в Chrome
						</a>
					)}
					<button onClick={onCopy} className='flex-1 border border-gray-200 dark:border-slate-700 text-gray-800 dark:text-white font-semibold py-2.5 rounded-xl'>
						{copied === 'ok' ? 'Скопійовано ✓' : copied === 'fail' ? 'Не вдалося скопіювати' : 'Копіювати посилання'}
					</button>
				</div>
			</div>
		</div>
	);
};

export default InAppBrowserBanner;
