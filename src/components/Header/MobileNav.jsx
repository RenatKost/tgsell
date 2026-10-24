import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AppContext';

const ITEMS = [
	{ to: '/catalog', label: 'Каталог каналів', active: 'bg-blue-500/10 text-blue-500 dark:bg-blue-500/20 dark:text-blue-400' },
	{ to: '/auction', label: '🔥 Аукціон', active: 'bg-orange-500/10 text-orange-500 dark:bg-orange-500/20 dark:text-orange-400' },
	{ to: '/wanted', label: 'Шукаю канал', active: 'bg-emerald-500/10 text-emerald-500 dark:bg-emerald-500/20 dark:text-emerald-400' },
	{ to: '/escrow', label: 'Гарант', active: 'bg-violet-500/10 text-violet-500 dark:bg-violet-500/20 dark:text-violet-400' },
	{ to: '/contacts', label: 'Контакти', active: 'bg-cyan-500/10 text-cyan-500 dark:bg-cyan-500/20 dark:text-cyan-400' },
];
const itemCls = (active) => ({ isActive }) =>
	`block w-full px-4 py-3 rounded-xl font-bold text-lg transition-colors duration-200 ${
		isActive ? active : 'text-gray-800 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-white/5'
	}`;


const MobileNav = ({ showMenu, setShowMenu }) => {
	const { user, isAuthenticated, logout } = useAuth();
	const close = () => setShowMenu(false);
	const isStaff = isAuthenticated && user && (user.role === 'admin' || user.role === 'moderator');
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
				aria-hidden={!showMenu}
				className={`duration-500 ease-out px-5 pt-20 pb-8 flex flex-col justify-start items-stretch fixed inset-0 w-screen h-[100dvh] overflow-y-auto bg-white dark:bg-slate-900 z-40 ${
					showMenu ? 'translate-x-0 opacity-100' : 'translate-x-[-100%] opacity-0 pointer-events-none'
				}`}
			>
				<ul className='grid gap-1 w-full'>
					{ITEMS.map((it) => (
						<li key={it.to}>
							<NavLink to={it.to} className={itemCls(it.active)} onClick={close}>{it.label}</NavLink>
						</li>
					))}
					{isStaff && (
						<li>
							<NavLink to='/admin' className={itemCls('bg-red-500/10 text-red-500')} onClick={close}>Адмін</NavLink>
						</li>
					)}
					{isAuthenticated && user && (
						<li>
							<NavLink to='/cabinet' className={itemCls('bg-blue-500/10 text-blue-500 dark:bg-blue-500/20 dark:text-blue-400')} onClick={close}>Кабінет</NavLink>
						</li>
					)}
				</ul>
				<div className='grid mt-6 gap-3 w-full'>
					<NavLink
						className='w-full text-center font-semibold text-blue-500 border border-blue-500/30 py-3 px-6 rounded-xl hover:bg-blue-500 hover:text-white transition-all duration-200'
						to='/catalog'
						onClick={close}
					>
						Купити канал
					</NavLink>
					<NavLink
						className='w-full text-center font-semibold bg-gradient-to-r from-emerald-500 to-green-500 text-white py-3 px-6 rounded-xl hover:shadow-lg hover:shadow-green-500/25 transition-all duration-200'
						to='/sell'
						onClick={close}
					>
						Продати канал
					</NavLink>
					{isAuthenticated && user && (
						<button
							type='button'
							onClick={() => { close(); logout(); }}
							className='w-full text-center font-semibold text-gray-500 hover:text-red-500 border border-gray-200 dark:border-slate-700 py-3 px-6 rounded-xl transition-colors duration-200'
						>
							Вийти
						</button>
					)}
				</div>
			</nav>
		</>
	);
};

export default MobileNav;
