import { faTelegram, faGoogle } from '@fortawesome/free-brands-svg-icons';
import { faSpinner, faXmark } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useEffect, useRef, useState, useCallback } from 'react';
import { authAPI } from '../../services/api';
import { useAuth } from '../../context/AppContext';
import { isInAppBrowser } from '../../utils/inAppBrowser';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';
const TOKEN_TTL_MS = 5 * 60 * 1000; // matches backend auth_tokens._TTL
const TOKEN_REFRESH_MS = 4 * 60 * 1000;
const PENDING_KEY = 'tg_bot_auth_pending';

const savePending = (token, at) => {
	try { sessionStorage.setItem(PENDING_KEY, JSON.stringify({ token, at })); } catch { /* ignore */ }
};
const clearPending = () => {
	try { sessionStorage.removeItem(PENDING_KEY); } catch { /* ignore */ }
};
const readPending = () => {
	try {
		const p = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null');
		if (p?.token && Date.now() - p.at < TOKEN_TTL_MS) return p;
		clearPending();
	} catch { /* ignore */ }
	return null;
};

const AuthModal = ({ show, setShow }) => {
	const googleBtnRef = useRef(null);
	const { login } = useAuth();
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

	// Telegram bot login. In-app WebViews (Instagram, TikTok…) block window.open after an await,
	// so the token is pre-created when the modal opens and the button is a real <a href="t.me/…">
	// that the browser follows synchronously on tap. Polling starts on that same click.
	const [botLink, setBotLink] = useState(null); // { token, bot_link, at }
	const inApp = isInAppBrowser();

	const stopPolling = useCallback(() => {
		if (pollRef.current) {
			clearInterval(pollRef.current);
			pollRef.current = null;
		}
	}, []);

	const prepareToken = useCallback(async () => {
		setBotAuth({ status: 'loading' });
		try {
			const { data } = await authAPI.createBotToken();
			setBotLink({ token: data.token, bot_link: data.bot_link, at: Date.now() });
			setBotAuth({ status: 'idle' });
		} catch {
			setBotLink(null);
			setBotAuth({ status: 'error' });
		}
	}, []);

	const startPolling = useCallback((token, startedAt = Date.now()) => {
		stopPolling();
		setBotAuth({ status: 'waiting', token });
		pollRef.current = setInterval(async () => {
			if (Date.now() - startedAt > TOKEN_TTL_MS) {
				stopPolling();
				clearPending();
				setBotLink(null);
				setBotAuth({ status: 'error' });
				return;
			}
			try {
				const { data: result } = await authAPI.checkBotAuth(token);
				if (result.status === 'ok') {
					stopPolling();
					clearPending();
					login(result.user, {
						access_token: result.access_token,
						refresh_token: result.refresh_token,
					});
					setShow(false);
					setBotAuth({ status: 'idle' });
				}
			} catch {
				stopPolling();
				clearPending();
				setBotLink(null);
				setBotAuth({ status: 'error' });
			}
		}, 2000);
	}, [login, setShow, stopPolling]);

	// Modal open: pre-create a token. Modal close: stop polling and reset.
	useEffect(() => {
		if (show) {
			if (!pollRef.current) prepareToken();
		} else {
			stopPolling();
			setBotAuth({ status: 'idle' });
			setBotLink(null);
			setAuthError('');
		}
	}, [show, prepareToken, stopPolling]);

	useEffect(() => () => stopPolling(), [stopPolling]);

	// Refresh a pre-created token before it expires (server TTL 5 min) while the user hesitates.
	useEffect(() => {
		if (!show || !botLink || botAuth.status !== 'idle') return undefined;
		const t = setTimeout(prepareToken, Math.max(0, TOKEN_REFRESH_MS - (Date.now() - botLink.at)));
		return () => clearTimeout(t);
	}, [show, botLink, botAuth.status, prepareToken]);

	// If the WebView navigated away to t.me and came back (page reloaded), resume polling.
	useEffect(() => {
		const pending = readPending();
		if (pending && !pollRef.current) startPolling(pending.token, pending.at);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);

	// Called synchronously from the <a> click — the browser itself follows href, no window.open.
	const handleBotLinkClick = () => {
		if (!botLink) return;
		setAuthError('');
		savePending(botLink.token, botLink.at);
		startPolling(botLink.token, botLink.at);
	};

	// Load Google Identity Services SDK
	useEffect(() => {
		if (!GOOGLE_CLIENT_ID || isInAppBrowser()) return;
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
		if (!show || !GOOGLE_CLIENT_ID || inApp || !googleBtnRef.current) return;

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
	}, [show, inApp, handleGoogleResponse]);

	if (!show) return null;

	const isLoading = botAuth.status === 'loading';
	const isWaiting = botAuth.status === 'waiting';
	const isError = botAuth.status === 'error';

	return (
		<div
			onClick={(e) => {
				if (e.target === e.currentTarget) setShow(false);
			}}
			className='fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm z-50 p-4'
		>
			<div className='bg-white dark:bg-slate-800 rounded-2xl shadow-2xl z-[51] mx-auto text-center max-w-[400px] w-full overflow-hidden animate-fadeIn'>
				{/* Close button */}
				<div className='flex justify-end p-3 pb-0'>
					<button
						onClick={() => setShow(false)}
						className='text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 dark:hover:bg-slate-700 duration-200'
					>
						<FontAwesomeIcon icon={faXmark} className='text-lg' />
					</button>
				</div>

				<div className='px-8 pb-8 pt-2'>
					<h2 className='text-xl font-bold text-gray-800 dark:text-white mb-2'>Авторизація в Телеграм</h2>

					{isWaiting ? (
						<p className='text-gray-500 dark:text-gray-400 text-sm mb-6'>
							Для завершення операції перейдіть в бота авторизації TgSell.
						</p>
					) : (
						<p className='text-gray-500 dark:text-gray-400 text-sm mb-6'>
							Натисніть кнопку нижче — відкриється бот в Telegram для швидкого входу.
						</p>
					)}

					{authError && (
						<div className='bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3 mb-4 text-left'>
							<p className='text-sm text-red-600 dark:text-red-400'>{authError}</p>
						</div>
					)}

					<div className='flex flex-col items-center gap-4'>
						{/* Primary: Telegram Bot Auth — real link, followed synchronously on tap */}
						<a
							href={botLink && !isWaiting ? botLink.bot_link : undefined}
							target={inApp ? undefined : '_blank'}
							rel='noopener noreferrer'
							onClick={(e) => {
								if (!botLink || isWaiting || isLoading) { e.preventDefault(); return; }
								handleBotLinkClick();
							}}
							aria-disabled={!botLink || isLoading || isWaiting}
							className={`w-full flex items-center justify-center gap-3 bg-[#2AABEE] hover:bg-[#229ED9] text-white py-4 px-6 rounded-xl font-semibold text-base shadow-md hover:shadow-lg hover:shadow-blue-200/50 duration-300 ${(!botLink || isLoading || isWaiting) ? 'opacity-70 cursor-wait' : 'cursor-pointer'}`}
						>
							{isLoading ? (
								<FontAwesomeIcon icon={faSpinner} className='animate-spin text-xl' />
							) : (
								<FontAwesomeIcon icon={faTelegram} className='text-2xl' />
							)}
							<span>{isLoading
								? 'Підключення...'
								: isWaiting
									? 'Очікуємо підтвердження...'
									: 'Авторизуватися через Телеграм'}</span>
						</a>

						{isWaiting && botLink && (
							<a href={botLink.bot_link} target={inApp ? undefined : '_blank'} rel='noopener noreferrer'
								className='text-xs text-[#229ED9] underline -mt-2'>
								Бот не відкрився? Відкрити ще раз
							</a>
						)}

						{isWaiting && (
							<div className='bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl px-4 py-3 w-full'>
								<div className='flex items-center gap-2 justify-center mb-1'>
									<FontAwesomeIcon icon={faSpinner} className='animate-spin text-blue-500 text-xs' />
									<p className='text-sm font-medium text-blue-700 dark:text-blue-400'>Очікуємо підтвердження</p>
								</div>
								<p className='text-xs text-blue-600/80 dark:text-blue-400/70'>
									Перейдіть у бот і натисніть <b>«Увійти в TgSell»</b>
								</p>
							</div>
						)}

						{isError && (
							<div className='bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3 w-full'>
								<p className='text-xs text-red-500 dark:text-red-400'>
									Час вийшов або сталась помилка.{' '}
									<button onClick={() => { clearPending(); prepareToken(); }} className='font-semibold underline hover:text-red-700 dark:hover:text-red-300'>Спробувати знову</button>
								</p>
							</div>
						)}

						{/* Divider */}
						{GOOGLE_CLIENT_ID && inApp && (
							<p className='text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-slate-700/40 rounded-xl px-4 py-3 w-full'>
								Вхід через Google недоступний у вбудованому браузері застосунку. Відкрийте сайт у Chrome або Safari, щоб увійти через Google.
							</p>
						)}
						{GOOGLE_CLIENT_ID && !inApp && (
							<>
								<div className='flex items-center gap-3 w-full'>
									<div className='flex-1 h-px bg-gray-200 dark:bg-slate-700'></div>
									<span className='text-gray-400 dark:text-gray-500 text-xs uppercase tracking-wider'>або</span>
									<div className='flex-1 h-px bg-gray-200 dark:bg-slate-700'></div>
								</div>

								{/* Google Sign-In */}
								<div ref={googleBtnRef} className='flex justify-center'></div>
							</>
						)}

						{import.meta.env.DEV && (
							<button
								className='w-full text-white flex items-center justify-center gap-2 bg-gradient-to-r from-[#3498db] to-[#2980b9] py-3 px-6 rounded-xl font-semibold shadow-md hover:shadow-lg hover:shadow-blue-200 duration-300'
								onClick={async () => {
									try {
										const { data } = await authAPI.loginTelegram({
											id: 123456789,
											first_name: 'Demo',
											username: 'demo_user',
											photo_url: '',
											auth_date: Math.floor(Date.now() / 1000),
											hash: 'demo',
										});
										login(data.user, {
											access_token: data.access_token,
											refresh_token: data.refresh_token,
										});
										setShow(false);
									} catch (e) {
										console.error('Demo auth failed:', e);
									}
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
