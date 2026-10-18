import { useEffect } from 'react';
import routeMeta from '../seo/routeMeta.json';

const SITE_URL = 'https://tgsell.me';

const upsert = (selector, create, attr, value) => {
	let el = document.head.querySelector(selector);
	if (!el) {
		el = create();
		document.head.appendChild(el);
	}
	const prev = el.getAttribute(attr);
	el.setAttribute(attr, value);
	return () => { if (prev !== null) el.setAttribute(attr, prev); };
};

const metaEl = (attr, key) => () => {
	const m = document.createElement('meta');
	m.setAttribute(attr, key);
	return m;
};

/** Keeps title/description/canonical/OG/Twitter in sync on client-side navigation.
 *  The server injects the same values into index.html for crawlers (backend/app/utils/spa_meta.py). */
const usePageMeta = (path) => {
	useEffect(() => {
		const meta = routeMeta[path];
		if (!meta) return undefined;
		const url = SITE_URL + path;
		const prevTitle = document.title;
		document.title = meta.title;
		const restores = [
			upsert('meta[name="description"]', metaEl('name', 'description'), 'content', meta.description),
			upsert('link[rel="canonical"]', () => { const l = document.createElement('link'); l.rel = 'canonical'; return l; }, 'href', url),
			upsert('meta[property="og:title"]', metaEl('property', 'og:title'), 'content', meta.title),
			upsert('meta[property="og:description"]', metaEl('property', 'og:description'), 'content', meta.description),
			upsert('meta[property="og:url"]', metaEl('property', 'og:url'), 'content', url),
			upsert('meta[name="twitter:title"]', metaEl('name', 'twitter:title'), 'content', meta.title),
			upsert('meta[name="twitter:description"]', metaEl('name', 'twitter:description'), 'content', meta.description),
		];
		return () => {
			document.title = prevTitle;
			restores.forEach((r) => r());
		};
	}, [path]);
	return routeMeta[path] || {};
};

export default usePageMeta;
