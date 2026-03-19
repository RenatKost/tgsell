import { faUser, faSignOutAlt } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AppContext';
import AuthModal from './AuthModal';
import MobileNav from './MobileNav';

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
			<nav className='xl:ml-24 ml-10 lg:flex items-center w-full hidden'>
				<ul className='flex items-center space-x-4'>
					<li>
						<NavLink
							to='/catalog'
							className='hover:text-[#3498db] font-bold duration-300 hover:translate-y-1 block'
						>
							Каталог каналів
						</NavLink>
					</li>
					<li>
						<a
							className='hover:text-[#3498db] font-bold duration-300 hover:translate-y-1 block'
							href='#footer'
							onClick={e => {
								e.preventDefault();
								setScrollToBottom(true);
							}}
						>
							Контакти
						</a>
					</li>
				</ul>

				{isAuthenticated && user ? (
					<div className='flex items-center gap-3 ml-auto'>
						{(user.role === 'admin' || user.role === 'moderator') && (
							<NavLink
								to='/admin'
								className='hover:text-[#e74c3c] font-bold duration-500 text-sm'
							>
								Адмін
							</NavLink>
						)}
						<NavLink
							to='/cabinet'
							className='flex items-center gap-2 hover:text-[#27ae60] cursor-pointer duration-500'
						>
							{user.avatar_url ? (
								<img src={user.avatar_url} alt='' className='w-7 h-7 rounded-full' />
							) : (
								<FontAwesomeIcon icon={faUser} />
							)}
							<p className='font-bold'>{user.first_name}</p>
						</NavLink>
						<button
							onClick={logout}
							className='hover:text-red-500 duration-500'
							title='Вийти'
						>
							<FontAwesomeIcon icon={faSignOutAlt} />
						</button>
					</div>
				) : (
					<div
						className='flex items-center gap-2 ml-auto hover:text-[#27ae60] cursor-pointer duration-500'
						onClick={() => setShowModal(true)}
					>
						<FontAwesomeIcon icon={faUser} />
						<p className='font-bold'>Увійти</p>
					</div>
				)}

				<div className='flex space-x-6 ml-auto'>
					<NavLink
						className='font-bold text-[#27ae60] shadow-md shadow-green-400 py-2 px-6 rounded-md duration-500 bg-white hover:text-white hover:bg-[#27ae60]'
						to='/catalog'
					>
						КУПИТИ КАНАЛ
					</NavLink>
					<NavLink
						className='font-bold bg-[#27ae60] text-white py-2 px-6 rounded-md shadow-md shadow-green-400 hover:bg-white hover:text-[#27ae60] duration-500'
						to='/sell'
					>
						ПРОДАТИ КАНАЛ
					</NavLink>
				</div>
			</nav>

			{/* Mobile auth */}
			{isAuthenticated && user ? (
				<div className='lg:hidden flex items-center gap-3'>
					<NavLink
						to='/cabinet'
						className='flex items-center gap-2 hover:text-[#27ae60] cursor-pointer duration-500'
					>
						{user.avatar_url ? (
							<img src={user.avatar_url} alt='' className='w-6 h-6 rounded-full' />
						) : (
							<FontAwesomeIcon icon={faUser} />
						)}
						<p className='font-bold text-sm'>{user.first_name}</p>
					</NavLink>
					<button onClick={logout} className='hover:text-red-500 duration-500'>
						<FontAwesomeIcon icon={faSignOutAlt} size='sm' />
					</button>
				</div>
			) : (
				<div
					className='lg:hidden flex items-center gap-2 hover:text-[#27ae60] cursor-pointer duration-500'
					onClick={() => setShowModal(true)}
				>
					<FontAwesomeIcon icon={faUser} />
					<p className='font-bold'>Увійти</p>
				</div>
			)}

			<nav className='lg:hidden flex items-center'>
				<MobileNav
					scroll={setScrollToBottom}
					showMenu={showMenu}
					setShowMenu={setShowMenu}
				/>
			</nav>
			<AuthModal show={showModal} setShow={setShowModal} />
		</>
	);
};

export default Navigation;
