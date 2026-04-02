import { useFormik } from 'formik';
import { useState, useEffect } from 'react';
import * as Yup from 'yup';
import { channelsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import { options } from './Main/Calculator';
import { useNavigate } from 'react-router-dom';

const SuccessModal = ({ onClose, onCabinet }) => {
	const [visible, setVisible] = useState(false);
	useEffect(() => {
		requestAnimationFrame(() => setVisible(true));
	}, []);

	const handleClose = (cb) => {
		setVisible(false);
		setTimeout(() => cb?.(), 250);
	};

	return (
		<div
			className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-300 ${visible ? 'bg-black/50 backdrop-blur-sm' : 'bg-black/0'}`}
			onClick={() => handleClose(onClose)}
		>
			<div
				className={`bg-white dark:bg-slate-800 rounded-2xl shadow-2xl max-w-md w-full p-8 text-center transition-all duration-300 ${visible ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-4'}`}
				onClick={e => e.stopPropagation()}
			>
				<div className='w-20 h-20 bg-gradient-to-br from-green-400 to-emerald-500 rounded-full flex items-center justify-center mx-auto mb-6 shadow-lg shadow-green-200 dark:shadow-green-900/30'>
					<svg className='w-10 h-10 text-white' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2.5}>
						<path strokeLinecap='round' strokeLinejoin='round' d='M5 13l4 4L19 7' />
					</svg>
				</div>

				<h3 className='text-2xl font-bold text-gray-900 dark:text-white mb-3'>
					Канал додано!
				</h3>
				<p className='text-gray-500 dark:text-gray-400 mb-6 leading-relaxed'>
					Ваш канал з'явиться в каталозі після перевірки адміністратором.
				</p>

				<div className='bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-100 dark:border-blue-800 rounded-xl p-5 mb-6 text-left'>
					<div className='flex items-start gap-3'>
						<div className='w-10 h-10 bg-blue-500 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5'>
							<svg className='w-5 h-5 text-white' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
								<path strokeLinecap='round' strokeLinejoin='round' d='M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9' />
							</svg>
						</div>
						<div>
							<p className='font-semibold text-gray-800 dark:text-gray-200 text-sm'>Підключіть бота сповіщень</p>
							<p className='text-gray-500 dark:text-gray-400 text-sm mt-1'>
								Він повідомить, коли канал підтвердять і коли його захочуть купити
							</p>
						</div>
					</div>
				</div>

				<div className='flex flex-col gap-3'>
					<a
						href='https://t.me/tgsell_alert_bot?start=subscribe'
						target='_blank'
						rel='noopener noreferrer'
						className='flex items-center justify-center gap-2 bg-[#0088cc] hover:bg-[#0077b5] text-white font-semibold py-3.5 px-6 rounded-xl transition-all duration-200 hover:shadow-lg hover:shadow-blue-200'
					>
						<svg className='w-5 h-5' viewBox='0 0 24 24' fill='currentColor'>
							<path d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z' />
						</svg>
						Підключити бота
					</a>
					<button
						type='button'
						onClick={() => handleClose(onCabinet)}
						className='text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 font-medium py-2.5 px-6 rounded-xl transition-colors duration-200 hover:bg-gray-100 dark:hover:bg-slate-700'
					>
						Перейти до кабінету →
					</button>
				</div>
			</div>
		</div>
	);
};

const InputField = ({ label, error, touched, icon, children }) => (
	<div className='space-y-1.5'>
		<label className='text-sm font-medium text-gray-600 dark:text-gray-400 flex items-center gap-1.5'>
			{icon && <span className='text-gray-400'>{icon}</span>}
			{label}
		</label>
		{children}
		{touched && error && (
			<p className='text-xs text-red-500 flex items-center gap-1'>
				<svg className='w-3.5 h-3.5' fill='currentColor' viewBox='0 0 20 20'>
					<path fillRule='evenodd' d='M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z' clipRule='evenodd' />
				</svg>
				{error}
			</p>
		)}
	</div>
);

const inputClass = 'w-full border border-gray-200 dark:border-slate-600 rounded-xl px-4 py-3.5 text-sm bg-gray-50/50 dark:bg-slate-700/50 dark:text-white placeholder-gray-400 transition-all duration-200 focus:border-blue-400 focus:bg-white dark:focus:bg-slate-700 focus:ring-4 focus:ring-blue-50 dark:focus:ring-blue-900/30';

const SellForm = () => {
	const { isAuthenticated } = useAuth();
	const navigate = useNavigate();
	const [submitError, setSubmitError] = useState('');
	const [showModal, setShowModal] = useState(false);

	const {
		handleSubmit,
		handleChange,
		handleBlur,
		values,
		errors,
		touched,
		isSubmitting,
		setFieldValue,
	} = useFormik({
		initialValues: {
			telegram_link: '',
			seller_telegram: '',
			category: '',
			price: '',
			monthly_income: '',
			description: '',
			resource1: '',
			resource2: '',
			listing_type: 'sale',
			auction_start_price: '',
			auction_bid_step: '',
			auction_duration_hours: '48',
		},
		validationSchema: Yup.object({
			telegram_link: Yup.string()
				.matches(/^\S*$/, 'Не повинен містити пробілів')
				.required('Поле обов\'язкове для заповнення'),
			seller_telegram: Yup.string()
				.required('Поле обов\'язкове для заповнення'),
			category: Yup.string()
				.required('Оберіть тематику'),
			price: Yup.number()
				.typeError('Введіть число')
				.positive('Ціна повинна бути більше 0')
				.required('Поле обов\'язкове для заповнення'),
			auction_start_price: Yup.number()
				.typeError('Введіть число')
				.positive('Ціна повинна бути більше 0')
				.when('listing_type', {
					is: 'auction',
					then: (schema) => schema.required('Вкажіть стартову ціну'),
				}),
			auction_bid_step: Yup.number()
				.typeError('Введіть число')
				.positive('Крок повинен бути більше 0')
				.when('listing_type', {
					is: 'auction',
					then: (schema) => schema.required('Вкажіть крок ставки'),
				}),
		}),
		onSubmit: async (vals, { resetForm }) => {
			if (!isAuthenticated) {
				setSubmitError('Увійдіть для подання заявки');
				return;
			}
			setSubmitError('');
			try {
				const resources = [vals.resource1, vals.resource2].filter(Boolean).join('\n');
				const payload = {
					telegram_link: vals.telegram_link,
					seller_telegram: vals.seller_telegram,
					category: vals.category,
					price: parseFloat(vals.price),
					monthly_income: vals.monthly_income ? parseFloat(vals.monthly_income) : null,
					description: vals.description || null,
					resources: resources || null,
					listing_type: vals.listing_type,
				};
				if (vals.listing_type === 'auction') {
					payload.auction_start_price = parseFloat(vals.auction_start_price);
					payload.auction_bid_step = parseFloat(vals.auction_bid_step);
					payload.auction_duration_hours = parseInt(vals.auction_duration_hours);
				}
				await channelsAPI.create(payload);
				resetForm();
				setShowModal(true);
			} catch (err) {
				setSubmitError(err.response?.data?.detail || 'Помилка створення заявки');
			}
		},
	});

	return (
		<>
			<section className='min-h-screen py-20 px-4'>
				<div className='max-w-3xl mx-auto'>
					{/* Header */}
					<div className='text-center mb-10'>
						<div className='inline-flex items-center gap-2 bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 text-sm font-medium px-4 py-2 rounded-full mb-5'>
							<svg className='w-4 h-4' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
								<path strokeLinecap='round' strokeLinejoin='round' d='M12 19l9 2-9-18-9 18 9-2zm0 0v-8' />
							</svg>
							Продаж каналу
						</div>
						<h1 className='text-3xl md:text-4xl font-bold text-gray-900 dark:text-white mb-3'>
							Подати канал на продаж
						</h1>
						<p className='text-gray-500 dark:text-gray-400 max-w-lg mx-auto'>
							Заповніть форму і ваш канал з'явиться в каталозі після перевірки
						</p>
					</div>

					{/* Form Card */}
					<form
						className='bg-white dark:bg-slate-800 rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 overflow-hidden'
						onSubmit={handleSubmit}
					>
						{/* Required Fields Section */}
						<div className='p-8 pb-0'>
							<div className='flex items-center gap-2 mb-6'>
								<div className='w-8 h-8 bg-blue-500 rounded-lg flex items-center justify-center'>
									<span className='text-white font-bold text-sm'>1</span>
								</div>
								<h3 className='font-semibold text-gray-900 dark:text-white'>{"Обов'язкові поля"}</h3>
							</div>

							<div className='grid md:grid-cols-2 gap-5'>
								<InputField label='Посилання на канал' error={errors.telegram_link} touched={touched.telegram_link}>
									<input
										className={inputClass}
										name='telegram_link'
										value={values.telegram_link}
										onChange={handleChange}
										onBlur={handleBlur}
										type='text'
										placeholder='@username або https://t.me/...'
									/>
								</InputField>

								<InputField label='Ваш телеграм' error={errors.seller_telegram} touched={touched.seller_telegram}>
									<input
										className={inputClass}
										name='seller_telegram'
										value={values.seller_telegram}
										onChange={handleChange}
										onBlur={handleBlur}
										type='text'
										placeholder='@username'
									/>
								</InputField>

								<InputField label='Тематика' error={errors.category} touched={touched.category}>
									<select
										className={`${inputClass} ${!values.category ? 'text-gray-400' : 'text-gray-900 dark:text-white'}`}
										name='category'
										value={values.category}
										onChange={handleChange}
										onBlur={handleBlur}
									>
										<option value='' disabled hidden>
											Виберіть тематику
										</option>
										{options.map(option => (
											<option key={option.label} value={option.label}>
												{option.label}
											</option>
										))}
									</select>
								</InputField>

								<InputField label='Вартість (USDT)' error={errors.price} touched={touched.price}>
									<input
										className={inputClass}
										name='price'
										value={values.price}
										onChange={handleChange}
										onBlur={handleBlur}
										type='text'
										placeholder='0.00'
									/>
								</InputField>
							</div>

							{/* Listing Type */}
							<div className='mt-6'>
								<label className='text-sm font-medium text-gray-600 dark:text-gray-400 mb-3 block'>
									Тип розміщення
								</label>
								<div className='grid grid-cols-2 gap-3'>
									<button
										type='button'
										onClick={() => setFieldValue('listing_type', 'sale')}
										className={`p-4 rounded-xl border-2 transition-all duration-200 text-left ${
											values.listing_type === 'sale'
												? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
												: 'border-gray-200 dark:border-slate-600 hover:border-gray-300 dark:hover:border-slate-500'
										}`}
									>
										<div className='text-lg mb-1'>🏷️</div>
										<div className='font-semibold text-sm text-gray-900 dark:text-white'>Продаж</div>
										<div className='text-xs text-gray-500 dark:text-gray-400'>Фіксована ціна</div>
									</button>
									<button
										type='button'
										onClick={() => setFieldValue('listing_type', 'auction')}
										className={`p-4 rounded-xl border-2 transition-all duration-200 text-left ${
											values.listing_type === 'auction'
												? 'border-orange-500 bg-orange-50 dark:bg-orange-900/20'
												: 'border-gray-200 dark:border-slate-600 hover:border-gray-300 dark:hover:border-slate-500'
										}`}
									>
										<div className='text-lg mb-1'>🔥</div>
										<div className='font-semibold text-sm text-gray-900 dark:text-white'>Аукціон</div>
										<div className='text-xs text-gray-500 dark:text-gray-400'>Ставки покупців</div>
									</button>
								</div>
							</div>

							{/* Auction fields */}
							{values.listing_type === 'auction' && (
								<div className='mt-5 p-5 bg-orange-50/50 dark:bg-orange-900/10 border border-orange-200 dark:border-orange-800/30 rounded-xl space-y-4'>
									<div className='flex items-center gap-2 mb-2'>
										<span className='text-orange-500 text-lg'>🔥</span>
										<span className='font-semibold text-sm text-gray-900 dark:text-white'>Параметри аукціону</span>
									</div>
									<div className='grid md:grid-cols-3 gap-4'>
										<InputField label='Стартова ціна (USDT)' error={errors.auction_start_price} touched={touched.auction_start_price}>
											<input
												className={inputClass}
												name='auction_start_price'
												value={values.auction_start_price}
												onChange={handleChange}
												onBlur={handleBlur}
												type='text'
												placeholder='100'
											/>
										</InputField>
										<InputField label='Крок ставки (USDT)' error={errors.auction_bid_step} touched={touched.auction_bid_step}>
											<input
												className={inputClass}
												name='auction_bid_step'
												value={values.auction_bid_step}
												onChange={handleChange}
												onBlur={handleBlur}
												type='text'
												placeholder='10'
											/>
										</InputField>
										<InputField label='Тривалість'>
											<select
												className={`${inputClass} text-gray-900 dark:text-white`}
												name='auction_duration_hours'
												value={values.auction_duration_hours}
												onChange={handleChange}
											>
												<option value='24'>24 години</option>
												<option value='48'>48 годин</option>
												<option value='72'>72 години</option>
												<option value='168'>7 днів</option>
											</select>
										</InputField>
									</div>
									<p className='text-xs text-gray-500 dark:text-gray-400'>
										💡 Ціна вище (USDT) буде використана як ціна миттєвого викупу
									</p>
								</div>
							)}
						</div>

						{/* Divider */}
						<div className='px-8 py-6'>
								<div className='border-t border-gray-100 dark:border-slate-700'></div>
						</div>

						{/* Details Section */}
						<div className='px-8 pb-0'>
							<div className='flex items-center gap-2 mb-6'>
								<div className='w-8 h-8 bg-gray-200 rounded-lg flex items-center justify-center'>
									<span className='text-gray-600 font-bold text-sm'>2</span>
								</div>
								<h3 className='font-semibold text-gray-900 dark:text-white'>Додаткові деталі</h3>
								<span className='text-xs text-gray-400 ml-1'>(необов'язково)</span>
							</div>

							<div className='grid md:grid-cols-2 gap-5'>
								<InputField label='Дохід в місяць (USDT)'>
									<input
										className={inputClass}
										name='monthly_income'
										value={values.monthly_income}
										onChange={handleChange}
										onBlur={handleBlur}
										type='text'
										placeholder='Місячний дохід'
									/>
								</InputField>

								<div></div>

								<div className='md:col-span-2'>
									<InputField label='Опис каналу'>
										<textarea
											className={`${inputClass} h-28 resize-none`}
											name='description'
											value={values.description}
											onChange={handleChange}
											onBlur={handleBlur}
											placeholder='Розкажіть про ваш канал, щоб зацікавити покупця'
										/>
									</InputField>
								</div>

								<InputField label='Додатковий ресурс'>
									<input
										className={inputClass}
										name='resource1'
										value={values.resource1}
										onChange={handleChange}
										onBlur={handleBlur}
										type='url'
										placeholder='https://...'
									/>
								</InputField>

								<InputField label='Додатковий ресурс'>
									<input
										className={inputClass}
										name='resource2'
										value={values.resource2}
										onChange={handleChange}
										onBlur={handleBlur}
										type='url'
										placeholder='https://...'
									/>
								</InputField>
							</div>
						</div>

						{/* Submit Section */}
						<div className='p-8 mt-4'>
							{submitError && (
								<div className='flex items-center gap-2 bg-red-50 border border-red-100 text-red-600 text-sm px-4 py-3 rounded-xl mb-5'>
									<svg className='w-4 h-4 flex-shrink-0' fill='currentColor' viewBox='0 0 20 20'>
										<path fillRule='evenodd' d='M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z' clipRule='evenodd' />
									</svg>
									{submitError}
								</div>
							)}
							<button
								type='submit'
								disabled={isSubmitting}
								className='w-full md:w-auto bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-semibold py-3.5 px-10 rounded-xl shadow-md shadow-blue-200 hover:shadow-lg hover:shadow-blue-300 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2'
							>
								{isSubmitting ? (
									<>
										<svg className='animate-spin w-5 h-5' fill='none' viewBox='0 0 24 24'>
											<circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4' />
											<path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z' />
										</svg>
										Відправка...
									</>
								) : (
									<>
										Надіслати заявку
										<svg className='w-4 h-4' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
											<path strokeLinecap='round' strokeLinejoin='round' d='M14 5l7 7m0 0l-7 7m7-7H3' />
										</svg>
									</>
								)}
							</button>
						</div>
					</form>
				</div>
			</section>

			{showModal && (
				<SuccessModal
					onClose={() => setShowModal(false)}
					onCabinet={() => navigate('/cabinet')}
				/>
			)}
		</>
	);
};

export default SellForm;
