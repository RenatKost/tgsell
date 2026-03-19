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
			className={`${
				scrolling ? 'blur-bg shadow-md ' : ''
			} flex items-center justify-between fixed w-full py-5 md:px-12 px-5 left-0 z-10`}
		>
			<div className='text-2xl font-bold text-[#3498db]'>
				<NavLink to='/'>TgSell</NavLink>
			</div>
			<Navigation />
		</header>
	);
};

export default Header;
