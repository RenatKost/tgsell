import { faTelegram, faGoogle } from '@fortawesome/free-brands-svg-icons';
import { faRightLeft, faSpinner } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useEffect, useRef, useState, useCallback } from 'react';
import { authAPI } from '../../services/api';
import { useAuth } from '../../context/AppContext';

const TELEGRAM_BOT_NAME = import.meta.env.VITE_TELEGRAM_BOT_NAME || 'TgSellBot';
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

const AuthModal = ({ show, setShow }) => {
	const telegramRef = useRef(null);
	const googleBtnRef = useRef(null);
	const { login } = useAuth();
	const [widgetKey, setWidgetKey] = useState(0);
	const [botAuth, setBotAuth] = useState({ status: 'idle' }); // idle | loading | waiting | error
	const pollRef = useRef(null);

	// Google Sign-In callback
	const handleGoogleResponse = useCallback(async (response) => {
		try {
			const { data } = await authAPI.loginGoogle(response.credential);
			login(data.user, {
				access_token: data.access_token,
				refresh_token: data.refresh_token,
			});
			setShow(false);
		} catch (error) {
			console.error('Google auth failed:', error);
			const msg = error.response?.data?.detail || 'Помилка авторизації Google';
			alert(`Помилка входу: ${msg}`);
		}
	}, [login, setShow]);

	// Cleanup polling on unmount or modal close
	useEffect(() => {
		if (!show) {
			stopPolling();
			setBotAuth({ status: 'idle' });
		}
		return () => stopPolling();
	}, [show]);

	const stopPolling = () => {
		if (pollRef.current) {
			clearInterval(pollRef.current);
			pollRef.current = null;
		}
	};

	const handleBotLogin = async () => {
		setBotAuth({ status: 'loading' });
		try {
			const { data } = await authAPI.createBotToken();
			const { token, bot_link } = data;
			window.open(bot_link, '_blank');
			setBotAuth({ status: 'waiting', token });

			pollRef.current = setInterval(async () => {
				try {
					const { data: result } = await authAPI.checkBotAuth(token);
					if (result.status === 'ok') {
						stopPolling();
						login(result.user, {
							access_token: result.access_token,
							refresh_token: result.refresh_token,
						});
						setShow(false);
						setBotAuth({ status: 'idle' });
					}
				} catch {
					// token expired or error — stop polling
					stopPolling();
					setBotAuth({ status: 'error' });
				}
			}, 2000);
		} catch {
			setBotAuth({ status: 'error' });
		}
	};

	// Load Google Identity Services SDK
	useEffect(() => {
		if (!GOOGLE_CLIENT_ID) return;
		if (document.getElementById('google-gsi-script')) return;

		const script = document.createElement('script');
		script.id = 'google-gsi-script';
		script.src = 'https://accounts.google.com/gsi/client';
		script.async = true;
		script.defer = true;
		document.head.appendChild(script);
	}, []);

	// Initialize Google button when modal opens
	useEffect(() => {
		if (!show || !GOOGLE_CLIENT_ID || !googleBtnRef.current) return;

		const initGoogle = () => {
			if (!window.google?.accounts?.id) return;
			window.google.accounts.id.initialize({
				client_id: GOOGLE_CLIENT_ID,
				callback: handleGoogleResponse,
			});
			googleBtnRef.current.innerHTML = '';
			window.google.accounts.id.renderButton(googleBtnRef.current, {
				theme: 'outline',
				size: 'large',
				text: 'signin_with',
				locale: 'uk',
				width: 280,
			});
		};

		// SDK may not be loaded yet
		if (window.google?.accounts?.id) {
			initGoogle();
		} else {
			const timer = setInterval(() => {
				if (window.google?.accounts?.id) {
					clearInterval(timer);
					initGoogle();
				}
			}, 200);
			return () => clearInterval(timer);
		}
	}, [show, handleGoogleResponse]);

	const loadWidget = useCallback(() => {
		if (!telegramRef.current) return;

		// Telegram Login Widget callback
		window.onTelegramAuth = async (telegramUser) => {
			try {
				console.log('Telegram auth data:', telegramUser);
				const { data } = await authAPI.loginTelegram(telegramUser);
				login(data.user, {
					access_token: data.access_token,
					refresh_token: data.refresh_token,
				});
				setShow(false);
			} catch (error) {
				console.error('Telegram auth failed:', error);
				const msg = error.response?.data?.detail || 'Помилка авторизації';
				alert(`Помилка входу: ${msg}`);
			}
		};

		// Load Telegram Login Widget script
		telegramRef.current.innerHTML = '';
		const script = document.createElement('script');
		script.src = 'https://telegram.org/js/telegram-widget.js?22';
		script.setAttribute('data-telegram-login', TELEGRAM_BOT_NAME);
		script.setAttribute('data-size', 'large');
		script.setAttribute('data-onauth', 'onTelegramAuth(user)');
		script.setAttribute('data-request-access', 'write');
		script.async = true;
		telegramRef.current.appendChild(script);
	}, [login, setShow]);

	useEffect(() => {
		if (!show) return;
		loadWidget();
		return () => {
			delete window.onTelegramAuth;
		};
	}, [show, widgetKey, loadWidget]);

	if (!show) return null;

	return (
		<div
			onClick={(e) => {
				if (e.target === e.currentTarget) setShow(false);
			}}
			className='fixed top-0 left-0 h-screen w-screen flex items-center justify-center bg-black bg-opacity-50 z-50'
		>
			<div className='bg-white sm:p-10 p-6 rounded-xl shadow-lg z-[51] mx-auto text-center max-w-sm w-full'>
				<h2 className='text-2xl uppercase font-bold'>Вітаю 🙋‍♂️</h2>
				<p className='text-gray-500 mt-2 mb-6'>Увійдіть для продовження</p>
				<div className='flex flex-col items-center gap-4'>
					{/* Telegram Login */}
					<div ref={telegramRef} key={widgetKey} className='flex justify-center'>
						{/* Telegram Widget renders here */}
					</div>
					<button
						onClick={handleBotLogin}
						disabled={botAuth.status === 'loading' || botAuth.status === 'waiting'}
						className='text-gray-500 hover:text-[#3498db] text-xs flex items-center gap-1.5 duration-300 disabled:opacity-50'
					>
						{botAuth.status === 'loading' || botAuth.status === 'waiting' ? (
							<FontAwesomeIcon icon={faSpinner} className='text-[10px] animate-spin' />
						) : (
							<FontAwesomeIcon icon={faRightLeft} className='text-[10px]' />
						)}
						{botAuth.status === 'waiting' ? 'Очікуємо підтвердження...' : 'Інший Telegram аккаунт'}
					</button>
					{botAuth.status === 'waiting' && (
						<p className='text-xs text-gray-400'>
							Натисніть <b>Start</b> у боті, що відкрився в Telegram
						</p>
					)}
					{botAuth.status === 'error' && (
						<p className='text-xs text-red-400'>
							Час вийшов або сталась помилка.{' '}
							<button onClick={handleBotLogin} className='underline hover:text-red-600'>Спробувати знову</button>
						</p>
					)}

					<div className='flex items-center gap-3 w-full'>
						<div className='flex-1 h-px bg-gray-200'></div>
						<span className='text-gray-400 text-sm'>або</span>
						<div className='flex-1 h-px bg-gray-200'></div>
					</div>

					{/* Google Sign-In */}
					{GOOGLE_CLIENT_ID ? (
						<div ref={googleBtnRef} className='flex justify-center'></div>
					) : (
						<p className='text-gray-300 text-xs'>Google вхід не налаштовано</p>
					)}

					{import.meta.env.DEV && (
						<button
							className='text-white flex items-center gap-2 bg-[#3498db] py-3 px-8 rounded-md shadow-md duration-500 hover:shadow-[#3498db]'
							onClick={() => {
								window.onTelegramAuth?.({
									id: 123456789,
									first_name: 'Demo',
									username: 'demo_user',
									photo_url: '',
									auth_date: Math.floor(Date.now() / 1000),
									hash: 'demo',
								});
							}}
						>
							<FontAwesomeIcon icon={faTelegram} />
							Demo вхід (для розробки)
						</button>
					)}
				</div>
			</div>
		</div>
	);
};

export default AuthModal;
