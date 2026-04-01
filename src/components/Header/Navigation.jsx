import { faUser, faSignOutAlt } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AppContext';
import AuthModal from './AuthModal';
import MobileNav from './MobileNav';

const ThemeToggle = () => {
	const { theme, toggleTheme } = useAuth();
	return (
		<button
			onClick={toggleTheme}
			className='relative w-14 h-7 rounded-full bg-gray-200 dark:bg-slate-700 transition-colors duration-300 flex items-center p-1'
			title={theme === 'dark' ? 'Світла тема' : 'Темна тема'}
		>
			<div
				className={`w-5 h-5 rounded-full transition-all duration-300 flex items-center justify-center shadow-sm ${
					theme === 'dark'
						? 'translate-x-7 bg-indigo-500'
						: 'translate-x-0 bg-amber-400'
				}`}
			>
				{theme === 'dark' ? (
					<svg className='w-3 h-3 text-white' fill='currentColor' viewBox='0 0 20 20'>
						<path d='M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z' />
					</svg>
				) : (
					<svg className='w-3 h-3 text-white' fill='currentColor' viewBox='0 0 20 20'>
						<path fillRule='evenodd' d='M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z' clipRule='evenodd' />
					</svg>
				)}
			</div>
		</button>
	);
};

const Navigation = () => {
	const [showModal, setShowModal] = useState(false);
	const [scrollToBottom, setScrollToBottom] = useState(false);
	const [showMenu, setShowMenu] = useState(false);
	const { user, isAuthenticated, logout } = useAuth();

	useEffect(() => {
		if (scrollToBottom) {
			window.scrollTo({
				top: document.documentElement.scrollHeight,
				behavior: 'smooth',
			});
			setScrollToBottom(false);
		}
	}, [scrollToBottom]);

	return (
		<>
			{/* Desktop nav */}
			<nav className='lg:flex items-center gap-8 hidden'>
				<ul className='flex items-center gap-1'>
					<li>
						<NavLink
							to='/catalog'
							className={({ isActive }) =>
								`px-4 py-2 rounded-xl text-sm font-semibold transition-all duration-200 ${
									isActive
										? 'bg-blue-500/10 text-blue-500 dark:bg-blue-500/20 dark:text-blue-400'
										: 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5'
								}`
							}
						>
							Каталог
						</NavLink>
					</li>
					<li>
						<a
							className='px-4 py-2 rounded-xl text-sm font-semibold text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5 transition-all duration-200 block cursor-pointer'
							href='#footer'
							onClick={e => {
								e.preventDefault();
								setScrollToBottom(true);
							}}
						>
							Контакти
						</a>
					</li>
					{isAuthenticated && user && (user.role === 'admin' || user.role === 'moderator') && (
						<li>
							<NavLink
								to='/admin'
								className={({ isActive }) =>
									`px-4 py-2 rounded-xl text-sm font-semibold transition-all duration-200 ${
										isActive
											? 'bg-red-500/10 text-red-500'
											: 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-white/5'
									}`
								}
							>
								Адмін
							</NavLink>
						</li>
					)}
				</ul>

				<ThemeToggle />

				{isAuthenticated && user ? (
					<div className='flex items-center gap-3'>
						<NavLink
							to='/cabinet'
							className='flex items-center gap-2 text-gray-700 dark:text-gray-300 hover:text-blue-500 dark:hover:text-blue-400 transition-colors duration-200'
						>
							{user.avatar_url ? (
								<img src={user.avatar_url} alt='' className='w-7 h-7 rounded-full ring-2 ring-gray-200 dark:ring-slate-600' />
							) : (
								<div className='w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center'>
									<span className='text-white text-xs font-bold'>{(user.first_name || 'U')[0]}</span>
								</div>
							)}
							<p className='font-semibold text-sm'>{user.first_name}</p>
						</NavLink>
						<button
							onClick={logout}
							className='text-gray-400 hover:text-red-500 transition-colors duration-200 p-1'
							title='Вийти'
						>
							<FontAwesomeIcon icon={faSignOutAlt} size='sm' />
						</button>
					</div>
				) : (
					<button
						className='flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 transition-colors duration-200 font-semibold text-sm'
						onClick={() => setShowModal(true)}
					>
						<FontAwesomeIcon icon={faUser} />
						Увійти
					</button>
				)}

				<div className='flex items-center gap-2'>
					<NavLink
						className='text-sm font-semibold text-blue-500 border border-blue-500/30 hover:bg-blue-500 hover:text-white px-5 py-2 rounded-xl transition-all duration-200'
						to='/catalog'
					>
						Купити
					</NavLink>
					<NavLink
						className='text-sm font-semibold bg-gradient-to-r from-emerald-500 to-green-500 text-white px-5 py-2 rounded-xl hover:shadow-lg hover:shadow-green-500/25 transition-all duration-200'
						to='/sell'
					>
						Продати
					</NavLink>
				</div>
			</nav>

			{/* Mobile auth + theme + burger */}
			<div className='lg:hidden flex items-center gap-3'>
				<ThemeToggle />

				{isAuthenticated && user ? (
					<div className='flex items-center gap-2'>
						<NavLink
							to='/cabinet'
							className='flex items-center gap-2 text-gray-700 dark:text-gray-300'
						>
							{user.avatar_url ? (
								<img src={user.avatar_url} alt='' className='w-6 h-6 rounded-full' />
							) : (
								<div className='w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center'>
									<span className='text-white text-[10px] font-bold'>{(user.first_name || 'U')[0]}</span>
								</div>
							)}
							<p className='font-semibold text-sm'>{user.first_name}</p>
						</NavLink>
						<button
							onClick={logout}
							className='text-gray-400 hover:text-red-500 transition-colors duration-200'
						>
							<FontAwesomeIcon icon={faSignOutAlt} size='sm' />
						</button>
					</div>
				) : (
					<button
						className='flex items-center gap-2 text-gray-600 dark:text-gray-400 font-semibold text-sm'
						onClick={() => setShowModal(true)}
					>
						<FontAwesomeIcon icon={faUser} />
					</button>
				)}

				<MobileNav
					scroll={setScrollToBottom}
					showMenu={showMenu}
					setShowMenu={setShowMenu}
				/>
			</div>

			<AuthModal show={showModal} setShow={setShowModal} />
		</>
	);
};

export default Navigation;
