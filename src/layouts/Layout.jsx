import { Outlet } from 'react-router-dom';
import Footer from '../components/Footer';
import Header from '../components/Header/Header';
import { ScrollRestoration } from '../components/ScrollRestoration';

const Layout = () => {
	return (
		<ScrollRestoration>
			<div className='wrapper bg-gradient-to-tl from-blue-200  to-white '>
				<Header />
				<div className='content-container mx-auto content'>
					<Outlet></Outlet>
				</div>
				<Footer />
			</div>
		</ScrollRestoration>
	);
};

export default Layout;
