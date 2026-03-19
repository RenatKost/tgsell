import { faTelegram } from '@fortawesome/free-brands-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useEffect, useRef } from 'react';
import { authAPI } from '../../services/api';
import { useAuth } from '../../context/AppContext';

const TELEGRAM_BOT_NAME = import.meta.env.VITE_TELEGRAM_BOT_NAME || 'TgSellBot';

const AuthModal = ({ show, setShow }) => {
	const telegramRef = useRef(null);
	const { login } = useAuth();

	useEffect(() => {
		if (!show || !telegramRef.current) return;

		// Telegram Login Widget callback
		window.onTelegramAuth = async (telegramUser) => {
			try {
				const { data } = await authAPI.loginTelegram(telegramUser);
				login(data.user, {
					access_token: data.access_token,
					refresh_token: data.refresh_token,
				});
				setShow(false);
			} catch (error) {
				console.error('Telegram auth failed:', error);
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

		return () => {
			delete window.onTelegramAuth;
		};
	}, [show, login, setShow]);

	if (!show) return null;

	return (
		<div
			onClick={(e) => {
				if (e.target === e.currentTarget) setShow(false);
			}}
			className='fixed top-0 left-0 h-screen w-screen flex items-center justify-center bg-black bg-opacity-50 z-50'
		>
			<div className='bg-white sm:p-10 p-6 rounded shadow-lg z-[51] mx-auto text-center'>
				<h2 className='text-2xl uppercase font-bold'>Вітаю 🙋‍♂️</h2>
				<p className='text-gray-500 mt-2 mb-6'>Увійдіть через Telegram для продовження</p>
				<div className='flex flex-col items-center gap-6'>
					<div ref={telegramRef} className='flex justify-center'>
						{/* Telegram Widget renders here */}
					</div>
					<div className='text-gray-400 text-sm'>— або —</div>
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
