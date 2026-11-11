import { useEffect, useState } from 'react';
import { blogAPI } from '../services/api';

const SITE_URL = 'https://tgsell.me';
const BOOTSTRAP_ID = 'tgsell-blog-data';
const SCHEMA_ID = 'blog-article-schema';

/** Server bootstrap (same DTO as /api/blog*) for the first render after a direct load. */
const readBootstrap = () => {
	const el = document.getElementById(BOOTSTRAP_ID);
	if (!el) return null;
	try {
		return JSON.parse(el.textContent || 'null');
	} catch {
		return null;
	}
};

const takeBootstrap = (page, slug) => {
	const data = readBootstrap();
	if (!data || data.page !== page) return null;
	if (page === 'article' && data.article?.slug !== slug) return null;
	return data;
};

export const useBlogIndex = () => {
	const boot = takeBootstrap('index');
	const [state, setState] = useState(() => (boot ? { status: 'ok', articles: boot.articles } : { status: 'loading', articles: [] }));
	useEffect(() => {
		if (boot) return undefined;
		let alive = true;
		blogAPI.list()
			.then((r) => alive && setState({ status: 'ok', articles: r.data.articles || [] }))
			.catch(() => alive && setState({ status: 'error', articles: [] }));
		return () => { alive = false; };
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);
	return boot ? { status: 'ok', articles: boot.articles || [] } : state;
};

export const useBlogArticle = (slug) => {
	const boot = takeBootstrap('article', slug);
	const [state, setState] = useState(() => (boot ? { status: 'ok', article: boot.article, slug } : { status: 'loading', article: null, slug }));
	useEffect(() => {
		if (boot) return undefined;
		let alive = true;
		setState({ status: 'loading', article: null, slug });
		blogAPI.get(slug)
			.then((r) => alive && setState({ status: 'ok', article: r.data, slug }))
			.catch((e) => alive && setState({ status: e?.response?.status === 404 ? 'not_found' : 'error', article: null, slug }));
		return () => { alive = false; };
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [slug]);
	if (boot) return { status: 'ok', article: boot.article, slug };
	return state.slug === slug ? state : { status: 'loading', article: null, slug };
};

const setAttr = (selector, create, attr, value) => {
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

/** Head for client-side navigation (server already renders the same tags on direct load). */
export const useBlogHead = ({ path, title, description, type = 'website', schema = null }) => {
	useEffect(() => {
		if (!title) return undefined;
		const url = SITE_URL + path;
		const prevTitle = document.title;
		document.title = title;
		const restores = [
			setAttr('meta[name="description"]', metaEl('name', 'description'), 'content', description),
			setAttr('link[rel="canonical"]', () => { const l = document.createElement('link'); l.rel = 'canonical'; return l; }, 'href', url),
			setAttr('meta[property="og:title"]', metaEl('property', 'og:title'), 'content', title),
			setAttr('meta[property="og:description"]', metaEl('property', 'og:description'), 'content', description),
			setAttr('meta[property="og:url"]', metaEl('property', 'og:url'), 'content', url),
			setAttr('meta[property="og:type"]', metaEl('property', 'og:type'), 'content', type),
			setAttr('meta[name="twitter:title"]', metaEl('name', 'twitter:title'), 'content', title),
			setAttr('meta[name="twitter:description"]', metaEl('name', 'twitter:description'), 'content', description),
		];
		let schemaEl = document.getElementById(SCHEMA_ID);
		if (schema) {
			if (!schemaEl) {
				schemaEl = document.createElement('script');
				schemaEl.type = 'application/ld+json';
				schemaEl.id = SCHEMA_ID;
				document.head.appendChild(schemaEl);
			}
			schemaEl.textContent = JSON.stringify(schema).replace(/</g, '\\u003c');
		} else if (schemaEl) {
			schemaEl.remove();
		}
		return () => {
			document.title = prevTitle;
			restores.forEach((r) => r());
			const s = document.getElementById(SCHEMA_ID);
			if (s) s.remove();
		};
	}, [path, title, description, type, schema ? JSON.stringify(schema) : '']);
};

export const articleSchema = (a) => (a ? {
	'@context': 'https://schema.org',
	'@type': 'Article',
	headline: a.title,
	description: a.description,
	inLanguage: 'uk',
	url: a.url,
	mainEntityOfPage: { '@type': 'WebPage', '@id': a.url },
	datePublished: a.date,
	publisher: { '@type': 'Organization', name: 'TgSell', url: SITE_URL },
} : null);

const MONTHS = ['січня', 'лютого', 'березня', 'квітня', 'травня', 'червня', 'липня', 'серпня', 'вересня', 'жовтня', 'листопада', 'грудня'];

/** 'YYYY-MM-DD' → '8 листопада 2026' (editorial calendar date, no timezone shift). */
export const formatBlogDate = (iso) => {
	const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
	if (!m) return '';
	return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
};
