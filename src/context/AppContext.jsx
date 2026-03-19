import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authAPI } from '../services/api';

const AppContext = createContext();

const AppContextProvider = ({ children }) => {
	const [cards, setCards] = useState([]);
	const [user, setUser] = useState(null);
	const [isAuthenticated, setIsAuthenticated] = useState(false);
	const [loading, setLoading] = useState(true);

	// Check auth on mount
	useEffect(() => {
		const token = localStorage.getItem('access_token');
		if (token) {
			authAPI.getMe()
				.then(({ data }) => {
					setUser(data);
					setIsAuthenticated(true);
				})
				.catch(() => {
					localStorage.removeItem('access_token');
					localStorage.removeItem('refresh_token');
				})
				.finally(() => setLoading(false));
		} else {
			setLoading(false);
		}
	}, []);

	const login = useCallback((userData, tokens) => {
		localStorage.setItem('access_token', tokens.access_token);
		localStorage.setItem('refresh_token', tokens.refresh_token);
		setUser(userData);
		setIsAuthenticated(true);
	}, []);

	const logout = useCallback(() => {
		localStorage.removeItem('access_token');
		localStorage.removeItem('refresh_token');
		setUser(null);
		setIsAuthenticated(false);
	}, []);

	return (
		<AppContext.Provider value={{
			cards, setCards,
			user, setUser,
			isAuthenticated,
			loading,
			login, logout,
		}}>
			{children}
		</AppContext.Provider>
	);
};

const useAuth = () => {
	const { user, isAuthenticated, loading, login, logout } = useContext(AppContext);
	return { user, isAuthenticated, loading, login, logout };
};

const useAppContext = () => useContext(AppContext);

export { AppContext, AppContextProvider, useAuth, useAppContext };
