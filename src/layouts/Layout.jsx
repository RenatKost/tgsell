import { Outlet } from 'react-router-dom';
import Footer from '../components/Footer';
import Header from '../components/Header/Header';
import { ScrollRestoration } from '../components/ScrollRestoration';

const Layout = () => {
	return (
		<ScrollRestoration>
			<div className='wrapper bg-gray-50 dark:bg-slate-950 transition-colors duration-300'>
				<Header />
				<div className='max-w-7xl mx-auto px-4 md:px-8 content'>
					<Outlet></Outlet>
				</div>
				<Footer />
			</div>
		</ScrollRestoration>
	);
};

export default Layout;
