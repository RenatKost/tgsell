// «Приведи продавця»: remember ?ref=<code> (localStorage + cookie, 30 days) until the first lot submission.
const KEY = 'tgsell_ref';
const TTL_MS = 30 * 24 * 3600 * 1000;
const VALID = /^[a-z0-9]{4,16}$/;

export function captureRef(search = window.location.search) {
	try {
		const code = (new URLSearchParams(search).get('ref') || '').trim().toLowerCase();
		if (!VALID.test(code)) return;
		if (getRef()) return; // first referrer wins
		localStorage.setItem(KEY, JSON.stringify({ code, at: Date.now() }));
		document.cookie = `${KEY}=${code}; max-age=${TTL_MS / 1000}; path=/; samesite=lax`;
	} catch { /* storage unavailable */ }
}

export function getRef() {
	try {
		const raw = localStorage.getItem(KEY);
		if (raw) {
			const { code, at } = JSON.parse(raw);
			if (VALID.test(code) && Date.now() - at < TTL_MS) return code;
			localStorage.removeItem(KEY);
		}
		const m = document.cookie.match(/(?:^|; )tgsell_ref=([a-z0-9]{4,16})/);
		return m ? m[1] : null;
	} catch { return null; }
}

export function clearRef() {
	try { localStorage.removeItem(KEY); document.cookie = `${KEY}=; max-age=0; path=/`; } catch { /* noop */ }
}
