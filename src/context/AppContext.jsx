import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { authAPI, favoritesAPI } from '../services/api';

const AppContext = createContext();

const AppContextProvider = ({ children }) => {
	const [cards, setCards] = useState([]);
	const [user, setUser] = useState(null);
	const [isAuthenticated, setIsAuthenticated] = useState(false);
	const [loading, setLoading] = useState(true);
	const [favoriteIds, setFavoriteIds] = useState(new Set());
	const [theme, setThemeState] = useState(() => {
		const saved = localStorage.getItem('theme');
		return saved || 'dark';
	});

	// Apply theme class to <html>
	useEffect(() => {
		const root = document.documentElement;
		if (theme === 'dark') {
			root.classList.add('dark');
		} else {
			root.classList.remove('dark');
		}
		localStorage.setItem('theme', theme);
	}, [theme]);

	const toggleTheme = useCallback(() => {
		setThemeState(prev => prev === 'dark' ? 'light' : 'dark');
	}, []);

	// Check auth on mount
	useEffect(() => {
		const token = localStorage.getItem('access_token');
		if (token) {
			authAPI.getMe()
				.then(({ data }) => {
					setUser(data);
					setIsAuthenticated(true);
					return favoritesAPI.getIds();
				})
				.then(({ data }) => setFavoriteIds(new Set(data)))
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
		favoritesAPI.getIds().then(({ data }) => setFavoriteIds(new Set(data))).catch(() => {});
	}, []);

	const logout = useCallback(() => {
		localStorage.removeItem('access_token');
		localStorage.removeItem('refresh_token');
		setUser(null);
		setIsAuthenticated(false);
		setFavoriteIds(new Set());
	}, []);

	const toggleFavorite = useCallback(async (channelId) => {
		if (!isAuthenticated) return;
		const isFav = favoriteIds.has(channelId);
		try {
			if (isFav) {
				await favoritesAPI.remove(channelId);
				setFavoriteIds(prev => { const s = new Set(prev); s.delete(channelId); return s; });
			} else {
				await favoritesAPI.add(channelId);
				setFavoriteIds(prev => new Set(prev).add(channelId));
			}
		} catch (err) {
			console.error('Favorite toggle error:', err);
		}
	}, [isAuthenticated, favoriteIds]);

	return (
		<AppContext.Provider value={{
			cards, setCards,
			user, setUser,
			isAuthenticated,
			loading,
			login, logout,
			favoriteIds, toggleFavorite,
			theme, toggleTheme,
		}}>
			{children}
		</AppContext.Provider>
	);
};

const useAuth = () => {
	const { user, isAuthenticated, loading, login, logout, favoriteIds, toggleFavorite, theme, toggleTheme } = useContext(AppContext);
	return { user, isAuthenticated, loading, login, logout, favoriteIds, toggleFavorite, theme, toggleTheme };
};

const useAppContext = () => useContext(AppContext);

export { AppContext, AppContextProvider, useAuth, useAppContext };
