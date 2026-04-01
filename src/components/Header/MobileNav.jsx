import { NavLink } from 'react-router-dom';

const MobileNav = ({ scroll, showMenu, setShowMenu }) => {
	return (
		<>
			<div
				onClick={() => setShowMenu(!showMenu)}
				className='grid relative z-50 cursor-pointer space-y-1.5'
			>
				<span
					className={`w-6 h-0.5 block rounded-full relative duration-300 ${
						showMenu
							? 'rotate-45 translate-y-2 bg-blue-500'
							: 'rotate-0 bg-gray-500 dark:bg-gray-400'
					}`}
				/>
				<span
					className={`w-6 h-0.5 block rounded-full relative duration-300 ${
						showMenu ? 'opacity-0 scale-0' : 'opacity-100 bg-gray-500 dark:bg-gray-400'
					}`}
				/>
				<span
					className={`w-6 h-0.5 block rounded-full relative duration-300 ${
						showMenu
							? '-rotate-45 -translate-y-2 bg-blue-500'
							: 'rotate-0 bg-gray-500 dark:bg-gray-400'
					}`}
				/>
			</div>
			<nav
				className={`duration-500 ease-out px-8 flex flex-col justify-center items-start absolute w-screen h-screen bg-white dark:bg-slate-900 top-0 right-0 left-0 bottom-0 ${
					showMenu ? 'translate-x-0 opacity-100' : 'translate-x-[-100%] opacity-0'
				}`}
			>
				<ul className='grid space-y-3'>
					<li>
						<NavLink
							to='/catalog'
							className='text-gray-800 dark:text-gray-200 font-bold text-lg hover:text-blue-500 transition-colors duration-200 block py-2'
							onClick={() => setShowMenu(false)}
						>
							Каталог каналів
						</NavLink>
					</li>
					<li>
						<a
							className='text-gray-800 dark:text-gray-200 font-bold text-lg hover:text-blue-500 transition-colors duration-200 block py-2 cursor-pointer'
							href='#footer'
							onClick={e => {
								e.preventDefault();
								scroll(true);
								setShowMenu(false);
							}}
						>
							Контакти
						</a>
					</li>
				</ul>
				<div className='grid mt-8 space-y-3 w-full max-w-xs'>
					<NavLink
						className='text-center font-semibold text-blue-500 border border-blue-500/30 py-3 px-6 rounded-xl hover:bg-blue-500 hover:text-white transition-all duration-200'
						to='/catalog'
						onClick={() => setShowMenu(false)}
					>
						Купити канал
					</NavLink>
					<NavLink
						className='text-center font-semibold bg-gradient-to-r from-emerald-500 to-green-500 text-white py-3 px-6 rounded-xl hover:shadow-lg hover:shadow-green-500/25 transition-all duration-200'
						to='/sell'
						onClick={() => setShowMenu(false)}
					>
						Продати канал
					</NavLink>
				</div>
			</nav>
		</>
	);
};

export default MobileNav;
