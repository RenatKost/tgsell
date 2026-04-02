import { createBrowserRouter } from 'react-router-dom';
import CabinetPage from './layouts/CabinetPage';
import CatalogPage from './layouts/CatalogPage';
import HomePage from './layouts/HomePage';
import Layout from './layouts/Layout';
import ModerCabinet from './layouts/ModerCabinet';
import SellPage from './layouts/SellPage';
import ErrorsPage from './layouts/ErrorsPage';
import ChannelDetailsPage from './layouts/ChannelDetailsPage';
import DealPage from './layouts/DealPage';
import ProfilePage from './layouts/ProfilePage';
import AuctionPage from './layouts/AuctionPage';
import PrivateRoute from './components/PrivateRoute';

export const router = createBrowserRouter([
	{
		path: '/',
		element: <Layout />,
		errorElement: <ErrorsPage />,
		children: [
			{
				element: <HomePage />,
				index: true,
			},
			{
				path: '/sell',
				element: (
					<PrivateRoute>
						<SellPage />
					</PrivateRoute>
				),
			},
			{
				path: '/catalog',
				element: <CatalogPage />,
			},
			{
				path: '/auction',
				element: <AuctionPage />,
			},
			{
				path: '/cabinet',
				element: (
					<PrivateRoute>
						<CabinetPage />
					</PrivateRoute>
				),
			},
			{
				path: '/admin',
				element: (
					<PrivateRoute requiredRole='moderator'>
						<ModerCabinet />
					</PrivateRoute>
				),
			},
			{
				path: '/channel/:id',
				element: <ChannelDetailsPage />,
			},
			{
				path: '/deal/:id',
				element: (
					<PrivateRoute>
						<DealPage />
					</PrivateRoute>
				),
			},
			{
				path: '/profile',
				element: (
					<PrivateRoute>
						<ProfilePage />
					</PrivateRoute>
				),
			},
		],
	},
]);

export default router;

