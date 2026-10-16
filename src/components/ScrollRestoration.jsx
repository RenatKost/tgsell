import { useLocation } from 'react-router-dom';
import { useEffect } from 'react';

// Scroll to top on navigation; if the URL has a #hash (footer anchors like /#how),
// scroll to that section instead, retrying briefly while the page renders.
export const ScrollRestoration = (props) => {
	const { pathname, search, hash } = useLocation();
	useEffect(() => {
		if (!hash) { window.scrollTo(0, 0); return undefined; }
		const id = decodeURIComponent(hash.slice(1));
		let tries = 0;
		let timer;
		const go = () => {
			const el = document.getElementById(id);
			if (el) { el.scrollIntoView({ behavior: 'smooth', block: 'start' }); return; }
			if (++tries < 20) timer = setTimeout(go, 100);
		};
		go();
		return () => clearTimeout(timer);
	}, [pathname, search, hash]);

	return <>{props.children}</>;
};
