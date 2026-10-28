import { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AppContext';
import AuthModal from './Header/AuthModal';

// Unauthenticated visitors stay on the same URL (e.g. /sell from an ad, UTM kept) and see a login gate;
// after Telegram login the page renders in place — no redirect to the home page, no dead end.
const LoginGate = () => {
	const [show, setShow] = useState(true);
	return (
		<div className='flex flex-col items-center justify-center text-center min-h-[60vh] px-4 pt-28 pb-12' data-login-gate>
			<h1 className='text-2xl font-black text-gray-900 dark:text-white mb-2'>Увійдіть, щоб продовжити</h1>
			<p className='text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-sm'>
				Вхід через Telegram займає кілька секунд. Після входу ви одразу повернетеся на цю сторінку.
			</p>
			<button type='button' onClick={() => setShow(true)}
				className='rounded-xl px-6 py-3 font-semibold bg-[#2AABEE] hover:bg-[#229ED9] text-white'>
				Увійти через Telegram
			</button>
			<AuthModal show={show} setShow={setShow} />
		</div>
	);
};

const PrivateRoute = ({ children, requiredRole }) => {
	const { isAuthenticated, user, loading } = useAuth();

	if (loading) {
		return (
			<div className='flex items-center justify-center min-h-[50vh]'>
				<div className='animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[#3498db]'></div>
			</div>
		);
	}

	if (!isAuthenticated) {
		if (requiredRole) return <Navigate to='/' replace />;
		return <LoginGate />;
	}

	if (requiredRole && user?.role !== requiredRole && user?.role !== 'admin') {
		return <Navigate to='/' replace />;
	}

	return children;
};

export default PrivateRoute;
