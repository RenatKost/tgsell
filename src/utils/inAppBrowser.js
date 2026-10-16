// Detect in-app browsers (Instagram, Facebook, TikTok, …) where window.open / Google OAuth break.
const INAPP_RE = /(Instagram|FBAN|FBAV|FB_IAB|FBIOS|FB4A|MessengerForiOS|Messenger|TikTok|musical_ly|BytedanceWebview|Bytedance|trill|Snapchat|Pinterest|LinkedInApp|Twitter|Line\/|KAKAOTALK|MicroMessenger|WhatsApp|Threads|Barcelona)/i;

export const getUA = () => (typeof navigator !== 'undefined' ? navigator.userAgent || '' : '');

export const isInAppBrowser = (ua = getUA()) => {
	if (INAPP_RE.test(ua)) return true;
	// Generic Android WebView marker ("; wv)") — excludes regular Chrome.
	return /Android/i.test(ua) && /\bwv\b/.test(ua);
};

export const isAndroid = (ua = getUA()) => /Android/i.test(ua);
export const isIOS = (ua = getUA()) => /iPhone|iPad|iPod/i.test(ua);

// intent:// URL that opens the current page in Chrome on Android (falls back to the page itself).
export const chromeIntentUrl = (href = window.location.href) => {
	const u = new URL(href);
	const fallback = encodeURIComponent(href);
	return `intent://${u.host}${u.pathname}${u.search}${u.hash}#Intent;scheme=${u.protocol.replace(':', '')};package=com.android.chrome;S.browser_fallback_url=${fallback};end`;
};
