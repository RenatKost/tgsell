import { useEffect } from 'react';

// Поява при скролі. `is-visible` ставиться напряму в DOM, тому елемент з .esc-reveal
// не повинен мати className, що змінюється при ре-рендері (React перезапише клас і сховає його).
// Fallback: елементи, що вже у viewport або вище нього (стрибок скролом), показуються одразу,
// а через REVEAL_FALLBACK_MS показуються всі — контент ніколи не лишається невидимим.
const REVEAL_FALLBACK_MS = 1500;
const useReveal = () => {
	useEffect(() => {
		const els = [...document.querySelectorAll('.esc-reveal:not(.is-visible)')];
		const show = (el) => el.classList.add('is-visible');
		if (!els.length) return undefined;
		if (!('IntersectionObserver' in window)) { els.forEach(show); return undefined; }
		const io = new IntersectionObserver((entries) => entries.forEach((en) => {
			if (en.isIntersecting || en.boundingClientRect.top < 0) { show(en.target); io.unobserve(en.target); }
		}), { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
		els.forEach((el) => io.observe(el));
		const t = setTimeout(() => { els.forEach(show); io.disconnect(); }, REVEAL_FALLBACK_MS);
		return () => { clearTimeout(t); io.disconnect(); };
	});
};

export default useReveal;
