import { faTelegram, faGoogle } from '@fortawesome/free-brands-svg-icons';
import { faRightLeft, faSpinner, faXmark } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useEffect, useRef, useState, useCallback } from 'react';
import { authAPI } from '../../services/api';
import { useAuth } from '../../context/AppContext';

const TELEGRAM_BOT_NAME = import.meta.env.VITE_TELEGRAM_BOT_NAME || 'tgsell_auth_bot';
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

const AuthModal = ({ show, setShow }) => {
	const telegramRef = useRef(null);
	const googleBtnRef = useRef(null);
	const { login } = useAuth();
	const [widgetKey, setWidgetKey] = useState(0);
	const [botAuth, setBotAuth] = useState({ status: 'idle' }); // idle | loading | waiting | error
	const [authError, setAuthError] = useState('');
	const pollRef = useRef(null);

	// Google Sign-In callback
	const handleGoogleResponse = useCallback(async (response) => {
		setAuthError('');
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
			setAuthError(msg);
		}
	}, [login, setShow]);

	// Cleanup polling on unmount or modal close
	useEffect(() => {
		if (!show) {
			stopPolling();
			setBotAuth({ status: 'idle' });
			setAuthError('');
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
			setAuthError('');
			try {
				console.log('Telegram auth data:', telegramUser);
				const { data } = await authAPI.loginTelegram(telegramUser);
				console.log('Telegram auth response:', data);
				login(data.user, {
					access_token: data.access_token,
					refresh_token: data.refresh_token,
				});
				setShow(false);
			} catch (error) {
				console.error('Telegram auth failed:', error);
				console.error('Response data:', error.response?.data);
				console.error('Response status:', error.response?.status);
				const msg = error.response?.data?.detail || 'Помилка авторизації. Перевірте консоль браузера.';
				setAuthError(msg);
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
			className='fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm z-50 p-4'
		>
			<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-2xl z-[51] mx-auto text-center max-w-[400px] w-full overflow-hidden animate-fadeIn'>
				{/* Top gradient bar */}
				<div className='h-24 bg-gradient-to-r from-[#3498db] to-[#27ae60] flex items-center justify-center relative'>
					<button
						onClick={() => setShow(false)}
						className='absolute top-3 right-3 text-white/70 hover:text-white w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/20 duration-200'
					>
						<FontAwesomeIcon icon={faXmark} className='text-lg' />
					</button>
					<div className='w-16 h-16 bg-white rounded-2xl shadow-lg flex items-center justify-center'>
						<span className='text-3xl'>🔐</span>
					</div>
				</div>

				<div className='px-8 py-6'>
					<h2 className='text-xl font-bold text-gray-800 dark:text-white mb-1'>Вхід в TgSell</h2>
					<p className='text-gray-400 dark:text-gray-500 text-sm mb-6'>Оберіть спосіб авторизації</p>

					{authError && (
						<div className='bg-red-50 border border-red-200 rounded-xl px-4 py-3 mb-4 text-left'>
							<p className='text-sm text-red-600'>{authError}</p>
						</div>
					)}

					<div className='flex flex-col items-center gap-4'>
						{/* Telegram Login Widget */}
						<div ref={telegramRef} key={widgetKey} className='flex justify-center'>
							{/* Telegram Widget renders here */}
						</div>

						{/* Switch account via bot */}
						<button
							onClick={handleBotLogin}
							disabled={botAuth.status === 'loading' || botAuth.status === 'waiting'}
							className='text-gray-400 hover:text-[#3498db] text-xs flex items-center gap-1.5 duration-300 disabled:opacity-50'
						>
							{botAuth.status === 'loading' || botAuth.status === 'waiting' ? (
								<FontAwesomeIcon icon={faSpinner} className='text-[10px] animate-spin' />
							) : (
								<FontAwesomeIcon icon={faRightLeft} className='text-[10px]' />
							)}
							{botAuth.status === 'waiting' ? 'Очікуємо підтвердження...' : 'Інший Telegram аккаунт'}
						</button>
						{botAuth.status === 'waiting' && (
							<div className='bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 w-full'>
								<p className='text-xs text-blue-600'>
									Натисніть <b>Start</b> у боті, що відкрився в Telegram
								</p>
							</div>
						)}
						{botAuth.status === 'error' && (
							<div className='bg-red-50 border border-red-100 rounded-xl px-4 py-3 w-full'>
								<p className='text-xs text-red-500'>
									Час вийшов або сталась помилка.{' '}
									<button onClick={handleBotLogin} className='font-semibold underline hover:text-red-700'>Спробувати знову</button>
								</p>
							</div>
						)}

						{/* Divider */}
						<div className='flex items-center gap-3 w-full'>
								<div className='flex-1 h-px bg-gray-100 dark:bg-slate-700'></div>
								<span className='text-gray-300 dark:text-gray-500 text-xs uppercase tracking-wider'>або</span>
								<div className='flex-1 h-px bg-gray-100 dark:bg-slate-700'></div>
						</div>

						{/* Google Sign-In */}
						{GOOGLE_CLIENT_ID ? (
							<div ref={googleBtnRef} className='flex justify-center'></div>
						) : (
							<p className='text-gray-300 text-xs'>Google вхід не налаштовано</p>
						)}

						{import.meta.env.DEV && (
							<button
								className='w-full text-white flex items-center justify-center gap-2 bg-gradient-to-r from-[#3498db] to-[#2980b9] py-3 px-6 rounded-xl font-semibold shadow-md hover:shadow-lg hover:shadow-blue-200 duration-300'
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
		</div>
	);
};

export default AuthModal;
