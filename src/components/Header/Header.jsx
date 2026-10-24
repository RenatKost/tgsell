import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import Navigation from './Navigation';

const Header = () => {
	const [scrolling, setScrolling] = useState(false);

	const handleScroll = () => {
		const y = Math.max(window.scrollY || 0, document.documentElement.scrollTop || 0, document.body.scrollTop || 0);
		if (y > 50) {
			setScrolling(true);
		} else {
			setScrolling(false);
		}
	};

	useEffect(() => {
		// capture: also catches scroll of <body>/inner containers (scroll events don't bubble)
		document.addEventListener('scroll', handleScroll, { capture: true, passive: true });
		handleScroll();
		return () => {
			document.removeEventListener('scroll', handleScroll, { capture: true });
		};
	}, []);

	return (
		<header
			className={`fixed w-full top-0 left-0 z-[60] transition-all duration-500 ${
				scrolling
					? 'py-2 bg-white dark:bg-slate-900 shadow-lg shadow-black/5 dark:shadow-black/20 border-b border-gray-100 dark:border-white/5'
					: 'py-4 bg-transparent'
			} md:px-8 px-4`}
		>
			<div className='max-w-7xl mx-auto flex items-center justify-between'>
				<NavLink to='/' className='flex items-center group'>
					<img
						src='/logo.png'
						alt='TgSell'
						className='h-10 w-auto object-contain transition-transform duration-300 group-hover:scale-105'
					/>
				</NavLink>
				<Navigation />
			</div>
		</header>
	);
};

export default Header;
