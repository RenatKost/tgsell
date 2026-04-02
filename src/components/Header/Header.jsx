import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import Navigation from './Navigation';

const Header = () => {
	const [scrolling, setScrolling] = useState(false);

	const handleScroll = () => {
		if (window.scrollY > 50) {
			setScrolling(true);
		} else {
			setScrolling(false);
		}
	};

	useEffect(() => {
		window.addEventListener('scroll', handleScroll);
		return () => {
			window.removeEventListener('scroll', handleScroll);
		};
	}, []);

	return (
		<header
			className={`fixed w-full top-0 left-0 z-50 transition-all duration-500 ${
				scrolling
					? 'py-2 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20'
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
