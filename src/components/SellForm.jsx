import { useFormik } from 'formik';
import { useState, useEffect } from 'react';
import * as Yup from 'yup';
import { channelsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import { options } from './Main/Calculator';
import { useNavigate } from 'react-router-dom';

const SuccessModal = ({ onClose, onCabinet, listingType }) => {
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
			className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-all duration-300 ${visible ? 'bg-black/60 backdrop-blur-sm' : 'bg-black/0'}`}
			onClick={() => handleClose(onClose)}
		>
			<div
				className={`bg-card border border-card-border rounded-2xl shadow-2xl shadow-black/50 max-w-md w-full p-8 text-center transition-all duration-300 ${visible ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-4'}`}
				onClick={e => e.stopPropagation()}
			>
				<div className='w-20 h-20 bg-accent/10 border-2 border-accent/30 rounded-full flex items-center justify-center mx-auto mb-6'>
					<svg className='w-10 h-10 text-accent' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2.5}>
						<path strokeLinecap='round' strokeLinejoin='round' d='M5 13l4 4L19 7' />
					</svg>
				</div>

				<h3 className='text-2xl font-bold text-white mb-3'>Канал додано!</h3>
				<p className='text-gray-400 mb-6 leading-relaxed'>
					Ваш канал з'явиться в каталозі після перевірки адміністратором.
				</p>

				<div className='bg-card-inner border border-card-border rounded-xl p-5 mb-6 text-left'>
					<div className='flex items-start gap-3'>
						<div className='w-10 h-10 bg-[#0088cc]/20 border border-[#0088cc]/30 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5'>
							<svg className='w-5 h-5 text-[#0088cc]' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2}>
								<path strokeLinecap='round' strokeLinejoin='round' d='M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9' />
							</svg>
						</div>
						<div>
							<p className='font-semibold text-white text-sm'>Підключіть бота сповіщень</p>
							<p className='text-gray-400 text-sm mt-1'>
								Натисніть <b className='text-white'>/start</b> у боті, щоб активувати сповіщення. Бот повідомить, коли канал підтвердять і коли його захочуть купити.
								{(listingType === 'auction' || listingType === 'both') && (
									<> Також бот надсилатиме повідомлення про кожну нову ставку на ваш аукціон.</>
								)}
							</p>
						</div>
					</div>
				</div>

				<div className='flex flex-col gap-3'>
					<a
						href='https://t.me/tgsell_alert_bot?start=subscribe'
						target='_blank'
						rel='noopener noreferrer'
						className='flex items-center justify-center gap-2 bg-[#0088cc] hover:bg-[#0077b5] text-white font-semibold py-3.5 px-6 rounded-xl transition-all duration-200'
					>
						<svg className='w-5 h-5' viewBox='0 0 24 24' fill='currentColor'>
							<path d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z' />
						</svg>
						Підключити бота
					</a>
					<button
						type='button'
						onClick={() => handleClose(onCabinet)}
						className='text-gray-400 hover:text-white font-medium py-2.5 px-6 rounded-xl transition-colors duration-200 hover:bg-card-inner'
					>
						Перейти до кабінету →
					</button>
				</div>
			</div>
		</div>
	);
};

const InputField = ({ label, error, touched, children }) => (
	<div className='space-y-1.5'>
		<label className='block text-sm text-gray-400 mb-1'>{label}</label>
		{children}
		{touched && error && (
			<p className='text-xs text-red-400 flex items-center gap-1 mt-1'>
				<svg className='w-3.5 h-3.5' fill='currentColor' viewBox='0 0 20 20'>
					<path fillRule='evenodd' d='M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z' clipRule='evenodd' />
				</svg>
				{error}
			</p>
		)}
	</div>
);

const inputClass = 'w-full bg-card-inner border border-card-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 text-sm transition-colors';

const SellForm = ({ onBack }) => {
	const { isAuthenticated } = useAuth();
	const navigate = useNavigate();
	const [submitError, setSubmitError] = useState('');
	const [showModal, setShowModal] = useState(false);
	const [submittedListingType, setSubmittedListingType] = useState('sale');

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
					is: (val) => val === 'auction' || val === 'both',
					then: (schema) => schema.required('Вкажіть стартову ціну'),
				}),
			auction_bid_step: Yup.number()
				.typeError('Введіть число')
				.positive('Крок повинен бути більше 0')
				.when('listing_type', {
					is: (val) => val === 'auction' || val === 'both',
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
				if (vals.listing_type === 'auction' || vals.listing_type === 'both') {
					payload.auction_start_price = parseFloat(vals.auction_start_price);
					payload.auction_bid_step = parseFloat(vals.auction_bid_step);
					payload.auction_duration_hours = parseInt(vals.auction_duration_hours);
				}
				await channelsAPI.create(payload);
				setSubmittedListingType(vals.listing_type);
				resetForm();
				setShowModal(true);
			} catch (err) {
				setSubmitError(err.response?.data?.detail || 'Помилка створення заявки');
			}
		},
	});

	return (
		<>
			<section className='min-h-screen pt-8 pb-10 text-white'>
				<div className='max-w-3xl mx-auto px-4'>
					{/* Back button */}
					{onBack && (
						<button
							type='button'
							onClick={onBack}
							className='flex items-center gap-2 text-gray-400 hover:text-white text-sm mb-6 transition-colors group'
						>
							<svg className='w-4 h-4 group-hover:-translate-x-0.5 transition-transform' fill='none' stroke='currentColor' viewBox='0 0 24 24'>
								<path strokeLinecap='round' strokeLinejoin='round' strokeWidth={2} d='M15 19l-7-7 7-7' />
							</svg>
							Назад до вибору
						</button>
					)}

					{/* Header */}
					<div className='mb-8'>
						<h1 className='text-2xl font-black text-white mb-1'>
							Продати <span className='text-accent'>канал</span>
						</h1>
						<p className='text-gray-400 text-sm'>
							Заповніть форму — канал з'явиться в каталозі після перевірки
						</p>
					</div>

					{/* Form Card */}
					<form
						className='bg-card border border-card-border rounded-xl shadow-neon overflow-hidden'
						onSubmit={handleSubmit}
					>
						{/* Required Fields Section */}
						<div className='p-6 pb-0'>
							<div className='flex items-center gap-2 mb-5'>
								<div className='w-7 h-7 bg-accent rounded-md flex items-center justify-center'>
									<span className='text-black font-bold text-xs'>1</span>
								</div>
								<h3 className='font-semibold text-white text-sm'>{"Обов'язкові поля"}</h3>
							</div>

							<div className='grid md:grid-cols-2 gap-4'>
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
										className={`${inputClass} ${!values.category ? 'text-gray-600' : 'text-white'}`}
										name='category'
										value={values.category}
										onChange={handleChange}
										onBlur={handleBlur}
									>
										<option value='' disabled hidden>Виберіть тематику</option>
										{options.map(option => (
											<option key={option.label} value={option.label} className='bg-card text-white'>
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
							<div className='mt-5'>
								<label className='block text-sm text-gray-400 mb-3'>Тип розміщення</label>
								<div className='grid grid-cols-2 gap-3'>
									<button
										type='button'
										onClick={() => {
											const cur = values.listing_type;
											if (cur === 'both') setFieldValue('listing_type', 'auction');
											else if (cur === 'auction') setFieldValue('listing_type', 'both');
											else setFieldValue('listing_type', 'sale');
										}}
										className={`p-4 rounded-xl border-2 transition-all text-left ${
											values.listing_type === 'sale' || values.listing_type === 'both'
												? 'border-accent bg-accent/10'
												: 'border-card-border bg-card-inner hover:border-accent/30'
										}`}
									>
										<div className='text-lg mb-1'>🏷️</div>
										<div className='font-semibold text-sm text-white'>Каталог</div>
										<div className='text-xs text-gray-500'>Фіксована ціна</div>
									</button>
									<button
										type='button'
										onClick={() => {
											const cur = values.listing_type;
											if (cur === 'both') setFieldValue('listing_type', 'sale');
											else if (cur === 'sale') setFieldValue('listing_type', 'both');
											else setFieldValue('listing_type', 'auction');
										}}
										className={`p-4 rounded-xl border-2 transition-all text-left ${
											values.listing_type === 'auction' || values.listing_type === 'both'
												? 'border-orange-500 bg-orange-500/10'
												: 'border-card-border bg-card-inner hover:border-orange-500/30'
										}`}
									>
										<div className='text-lg mb-1'>🔥</div>
										<div className='font-semibold text-sm text-white'>Аукціон</div>
										<div className='text-xs text-gray-500'>Ставки покупців</div>
									</button>
								</div>
								<p className='text-xs text-gray-500 mt-2'>
									💡 Можна обрати обидва варіанти — канал буде і в каталозі, і на аукціоні
								</p>
							</div>

							{(values.listing_type === 'auction' || values.listing_type === 'both') && (
								<div className='mt-4 p-4 bg-orange-500/5 border border-orange-500/20 rounded-xl space-y-4'>
									<div className='flex items-center gap-2'>
										<span className='text-orange-400 text-sm'>🔥</span>
										<span className='font-semibold text-sm text-white'>Параметри аукціону</span>
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
												className={`${inputClass} text-white`}
												name='auction_duration_hours'
												value={values.auction_duration_hours}
												onChange={handleChange}
											>
												<option value='24' className='bg-card'>24 години</option>
												<option value='48' className='bg-card'>48 годин</option>
												<option value='72' className='bg-card'>72 години</option>
												<option value='168' className='bg-card'>7 днів</option>
											</select>
										</InputField>
									</div>
									<p className='text-xs text-gray-500'>
										💡 Аукціон триватиме до завершення часу або поки ви не закриєте лот за останньою ціною
									</p>
								</div>
							)}
						</div>

						{/* Divider */}
						<div className='px-6 py-5'>
							<div className='border-t border-card-border'></div>
						</div>

						{/* Details Section */}
						<div className='px-6 pb-0'>
							<div className='flex items-center gap-2 mb-5'>
								<div className='w-7 h-7 bg-card-inner border border-card-border rounded-md flex items-center justify-center'>
									<span className='text-gray-400 font-bold text-xs'>2</span>
								</div>
								<h3 className='font-semibold text-white text-sm'>Додаткові деталі</h3>
								<span className='text-xs text-gray-500 ml-1'>(необов'язково)</span>
							</div>

							<div className='grid md:grid-cols-2 gap-4'>
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
						<div className='p-6 mt-2'>
							{submitError && (
								<div className='flex items-center gap-2 bg-red-500/10 border border-red-500/30 text-red-400 text-sm px-4 py-3 rounded-xl mb-5'>
									<svg className='w-4 h-4 flex-shrink-0' fill='currentColor' viewBox='0 0 20 20'>
										<path fillRule='evenodd' d='M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z' clipRule='evenodd' />
									</svg>
									{submitError}
								</div>
							)}
							<div className='flex items-center gap-3'>
								{onBack && (
									<button
										type='button'
										onClick={onBack}
										className='border border-card-border text-gray-300 hover:border-accent/40 hover:text-white py-3 px-6 rounded-lg font-medium transition-all text-sm'
									>
										← Назад
									</button>
								)}
								<button
									type='submit'
									disabled={isSubmitting}
									className='flex-1 md:flex-none bg-accent text-black font-bold py-3 px-10 rounded-lg shadow-lg shadow-accent/30 hover:brightness-110 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 text-sm'
								>
									{isSubmitting ? (
										<>
											<svg className='animate-spin w-4 h-4' fill='none' viewBox='0 0 24 24'>
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
						</div>
					</form>
				</div>
			</section>

			{showModal && (
				<SuccessModal
					onClose={() => setShowModal(false)}
					onCabinet={() => navigate('/cabinet')}
					listingType={submittedListingType}
				/>
			)}
		</>
	);
};

export default SellForm;
