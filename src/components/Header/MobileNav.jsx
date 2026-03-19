import { NavLink } from 'react-router-dom';

const MobileNav = ({ scroll, showMenu, setShowMenu }) => {
	return (
		<>
			<div
				onClick={() => setShowMenu(!showMenu)}
				className='grid relative z-50 cursor-pointer space-y-1'
			>
				<span
					className={`w-6 h-1 block rounded-md relative  duration-300 ${
						showMenu
							? 'rotate-[145deg] w-8 bg-[#27ae60]'
							: 'rotate-0 bg-[#3498db]'
					}`}
				/>
				<span
					className={`w-6 h-1 block rounded-md relative  duration-300 ${
						showMenu ? 'ml-[0.4rem] w-10 bg-[#27ae60]' : 'ml-0 bg-[#3498db]'
					}`}
				/>
				<span
					className={`w-6 h-1 block rounded-md relative  duration-300 ${
						showMenu
							? 'rotate-[-148deg] w-8 bg-[#27ae60]'
							: 'rotate-0 bg-[#3498db]'
					}`}
				/>
			</div>
			<nav
				className={`duration-700 px-10 flex flex-col justify-center items-start absolute w-screen h-screen bg-gradient-to-tl from-blue-200 to-white top-0 right-0 left-0 bottom-0 
${showMenu ? 'translate-x-0' : 'translate-x-[-100%]'}`}
			>
				<ul className='grid space-y-4'>
					<li>
						<NavLink
							to='/catalog'
							className='hover:text-[#3498db] font-bold text-lg duration-300 hover:translate-y-1 block'
							onClick={() => setShowMenu(false)}
						>
							Каталог каналів
						</NavLink>
					</li>
					<li>
						<a
							className='hover:text-[#3498db] font-bold text-lg duration-300 hover:translate-y-1 block'
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
				<div className='grid mt-6 space-y-5'>
					<NavLink
						className='font-bold text-[#27ae60] shadow-md shadow-green-400 py-2 px-6 rounded-md duration-500 bg-white hover:text-white hover:bg-[#27ae60]'
						to='/catalog'
						onClick={() => setShowMenu(false)}
					>
						КУПИТИ КАНАЛ
					</NavLink>
					<NavLink
						className='font-bold bg-[#27ae60] text-white py-2 px-6 rounded-md shadow-md shadow-green-400 hover:bg-white hover:text-[#27ae60] duration-500'
						to='/sell'
						onClick={() => setShowMenu(false)}
					>
						ПРОДАТИ КАНАЛ
					</NavLink>
				</div>
			</nav>
		</>
	);
};

export default MobileNav;
