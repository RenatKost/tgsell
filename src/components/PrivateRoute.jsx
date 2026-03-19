import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AppContext';

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
		return <Navigate to='/' replace />;
	}

	if (requiredRole && user?.role !== requiredRole && user?.role !== 'admin') {
		return <Navigate to='/' replace />;
	}

	return children;
};

export default PrivateRoute;
