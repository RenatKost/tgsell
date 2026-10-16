import { Outlet } from 'react-router-dom';
import Footer from '../components/Footer';
import ActivityTracker from '../components/ActivityTracker';
import InAppBrowserBanner from '../components/InAppBrowserBanner';
import Header from '../components/Header/Header';
import { ScrollRestoration } from '../components/ScrollRestoration';
import { useAuth } from '../context/AppContext';

const Layout = () => {
	const { user } = useAuth();
	return (
		<ScrollRestoration>
			<div className='wrapper bg-gray-50 dark:bg-transparent transition-colors duration-300'>
				<Header />
				<ActivityTracker />
				<InAppBrowserBanner />
				{user?.is_blocked && (
					<div className='w-full max-w-7xl mx-auto px-4 md:px-8 mt-4'>
						<div className='rounded-xl border border-red-300 bg-red-50 dark:bg-red-900/20 dark:border-red-800 text-red-700 dark:text-red-300 px-4 py-3 text-sm'>
							<b>Акаунт заблоковано.</b> {user.blocked_reason ? `Причина: ${user.blocked_reason}. ` : ''}
							Нові угоди, оголошення та ставки недоступні. Перегляд ваших угод залишається; кошти в ескроу під контролем адміністратора.
						</div>
					</div>
				)}
				<div className='w-full max-w-7xl mx-auto px-4 md:px-8 content'>
					<Outlet></Outlet>
				</div>
				<Footer />
			</div>
		</ScrollRestoration>
	);
};

export default Layout;
