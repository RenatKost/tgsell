import { faUser, faSignOutAlt } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AppContext';

const AuthContainer = ({ onLoginClick }) => {
	const { user, isAuthenticated, logout } = useAuth();

	if (isAuthenticated && user) {
		return (
			<div className='lg:hidden flex items-center gap-3 ml-auto'>
				<NavLink
					to='/cabinet'
					className='flex items-center gap-2 hover:text-[#27ae60] cursor-pointer duration-500'
				>
					{user.avatar_url ? (
						<img src={user.avatar_url} alt='' className='w-7 h-7 rounded-full' />
					) : (
						<FontAwesomeIcon icon={faUser} />
					)}
					<p className='font-bold text-sm'>{user.first_name}</p>
				</NavLink>
				<button
					onClick={logout}
					className='hover:text-red-500 duration-500'
					title='Вийти'
				>
					<FontAwesomeIcon icon={faSignOutAlt} />
				</button>
			</div>
		);
	}

	return (
		<div
			className='lg:hidden flex items-center gap-2 ml-auto hover:text-[#27ae60] cursor-pointer duration-500'
			onClick={onLoginClick}
		>
			<FontAwesomeIcon icon={faUser} />
			<p>Увійти</p>
		</div>
	);
};

export default AuthContainer;