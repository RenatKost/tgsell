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

// Compact note shown ONLY inside AuthModal for in-app browsers (Instagram, Facebook, TikTok…).
// Never rendered on page load. Telegram link login still works in-app; this just offers a real browser.
const InAppBrowserBanner = () => {
	const [hidden, setHidden] = useState(() => {
		try { return sessionStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
	});
	const [copied, setCopied] = useState(false);
	const [showHint, setShowHint] = useState(false);
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
		<div data-inapp-banner className='w-full text-left text-xs rounded-xl bg-gray-50 dark:bg-slate-700/40 border border-gray-200 dark:border-slate-700 px-3 py-2'>
			<div className='flex items-start justify-between gap-2'>
				<p className='text-gray-500 dark:text-gray-400'>
					Якщо вхід не спрацює — відкрийте сайт у звичайному браузері.
				</p>
				<button type='button' onClick={onClose} aria-label='Закрити' className='text-gray-400 hover:text-gray-600 text-base leading-none -mt-0.5'>×</button>
			</div>
			<div className='flex flex-wrap gap-x-3 gap-y-1 mt-1.5'>
				{android && (
					<a href={chromeIntentUrl(href)} className='font-semibold text-accent underline'>Відкрити в Chrome</a>
				)}
				<button type='button' onClick={onCopy} className='font-semibold text-gray-700 dark:text-gray-200 underline'>
					{copied === 'ok' ? 'Скопійовано ✓' : copied === 'fail' ? 'Не вдалося скопіювати' : 'Копіювати посилання'}
				</button>
				{!android && (
					<button type='button' onClick={() => setShowHint((v) => !v)} className='font-semibold text-gray-700 dark:text-gray-200 underline'>Як відкрити?</button>
				)}
			</div>
			{showHint && (
				<p className='text-gray-600 dark:text-gray-300 mt-1.5'>
					{ios
						? <>Натисніть <b>…</b> угорі праворуч → <b>«Відкрити в Safari»</b> / <b>«Відкрити в браузері»</b>.</>
						: <>Натисніть <b>⋮</b> у куті екрана → <b>«Відкрити в браузері»</b>.</>}
				</p>
			)}
		</div>
	);
};

export default InAppBrowserBanner;
