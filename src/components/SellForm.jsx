import { useFormik } from 'formik';
import { useState, useEffect } from 'react';
import * as Yup from 'yup';
import { channelsAPI, wantedAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import { options } from './Main/Calculator';
import { useNavigate } from 'react-router-dom';
import PromoteDialog, { useServicesCatalog, availableServices, SERVICE_ICON } from './Services/PromoteDialog';
import AlertBotHint from './Services/AlertBotHint';

const SuccessModal = ({ onClose, onCabinet, listingType, channel }) => {
	const [visible, setVisible] = useState(false);
	const [promoKind, setPromoKind] = useState(null);
	const { user } = useAuth();
	const cat = useServicesCatalog();
	const services = availableServices(cat, channel);
	useEffect(() => {
		requestAnimationFrame(() => setVisible(true));
	}, []);

	const handleClose = (cb) => {
		setVisible(false);
		setTimeout(() => cb?.(), 250);
	};

	const auctionNote = (listingType === 'auction' || listingType === 'both') ? ' Також бот надсилатиме кожну нову ставку на ваш аукціон.' : '';

	return (
		<div
			className={`fixed inset-0 z-50 flex items-end sm:items-center justify-center sm:p-4 transition-all duration-300 ${visible ? 'bg-black/60 backdrop-blur-sm' : 'bg-black/0'}`}
			onClick={() => handleClose(onClose)}
		>
			<div
				className={`bg-card border border-card-border rounded-t-2xl sm:rounded-2xl shadow-2xl shadow-black/50 w-full sm:max-w-lg max-h-[94vh] overflow-y-auto p-5 sm:p-8 text-center transition-all duration-300 ${visible ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-4'}`}
				onClick={e => e.stopPropagation()}
			>
				<div className='w-16 h-16 sm:w-20 sm:h-20 bg-accent/10 border-2 border-accent/30 rounded-full flex items-center justify-center mx-auto mb-4 sm:mb-6'>
					<svg className='w-8 h-8 sm:w-10 sm:h-10 text-accent' fill='none' viewBox='0 0 24 24' stroke='currentColor' strokeWidth={2.5}>
						<path strokeLinecap='round' strokeLinejoin='round' d='M5 13l4 4L19 7' />
					</svg>
				</div>

				<h3 className='text-2xl font-bold text-white mb-2'>Канал додано!</h3>
				<p className='text-gray-400 mb-5 leading-relaxed text-sm sm:text-base'>
					Ваш канал з'явиться в каталозі після перевірки адміністратором.
				</p>

				{channel && services.length > 0 && (
					<div className='bg-card-inner border border-accent/30 rounded-xl p-4 sm:p-5 mb-4 text-left'>
						<p className='font-semibold text-white'>🚀 Просунути лот</p>
						<p className='text-gray-400 text-sm mt-1 mb-3'>Більше переглядів — швидший продаж. Оплата в USDT (TRC-20).</p>
						<div className='grid grid-cols-1 sm:grid-cols-3 gap-2'>
							{services.map((i) => (
								<button key={i.kind} type='button' onClick={() => setPromoKind(i.kind)}
									className='min-w-0 flex sm:flex-col items-center sm:items-stretch gap-3 sm:gap-1 p-3 rounded-xl border border-card-border bg-card hover:border-accent transition-colors text-left min-h-[44px]'>
									<span className='text-xl'>{SERVICE_ICON[i.kind]}</span>
									<span className='flex-1 min-w-0 text-sm font-semibold text-white leading-snug break-words [overflow-wrap:anywhere]'>{i.title}</span>
									<span className='text-sm font-bold text-accent tabular-nums whitespace-nowrap'>{i.price_usdt} USDT</span>
								</button>
							))}
						</div>
					</div>
				)}

				{!user?.alert_bot_started && (
					<AlertBotHint className='mb-5'
						text={<>Натисніть <b className='text-white'>Start</b> в <b className='text-accent'>@tgsell_alert_bot</b>, щоб отримувати сповіщення: коли канал підтвердять і коли його захочуть купити.{auctionNote}</>} />
				)}

				<button
					type='button'
					onClick={() => handleClose(onCabinet)}
					className='w-full text-gray-400 hover:text-white font-medium py-2.5 px-6 rounded-xl transition-colors duration-200 hover:bg-card-inner'
				>
					Перейти до кабінету →
				</button>
			</div>
			{promoKind && channel && (
				<div onClick={e => e.stopPropagation()}>
					<PromoteDialog channel={channel} initialKind={promoKind} onClose={() => setPromoKind(null)} onCabinet={() => handleClose(onCabinet)} />
				</div>
			)}
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

const SellForm = ({ onBack, wantedId = null }) => {
	const [wanted, setWanted] = useState(null);
	const { isAuthenticated } = useAuth();
	const navigate = useNavigate();
	const [submitError, setSubmitError] = useState('');
	const [showModal, setShowModal] = useState(false);
	const [submittedListingType, setSubmittedListingType] = useState('sale');
	const [createdChannel, setCreatedChannel] = useState(null);

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
			is_closed: false,
			subscribers_count: '',
			avg_views: '',
			er: '',
			stars_balance: '',
			ton_balance: '',
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
			subscribers_count: Yup.number()
				.typeError('Введіть число')
				.positive('Має бути більше 0')
				.when('is_closed', {
					is: true,
					then: (schema) => schema.required('Вкажіть кількість підписників'),
				}),
			stars_balance: Yup.number()
				.typeError('Введіть ціле число')
				.integer('Введіть ціле число')
				.min(0, 'Не може бути відʼємним'),
			ton_balance: Yup.number()
				.typeError('Введіть число')
				.min(0, 'Не може бути відʼємним'),
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
					stars_balance: vals.stars_balance !== '' ? parseInt(vals.stars_balance, 10) : null,
					ton_balance: vals.ton_balance !== '' ? parseFloat(String(vals.ton_balance).replace(',', '.')) : null,
				};
				if (vals.listing_type === 'auction' || vals.listing_type === 'both') {
					payload.auction_start_price = parseFloat(vals.auction_start_price);
					payload.auction_bid_step = parseFloat(vals.auction_bid_step);
					payload.auction_duration_hours = parseInt(vals.auction_duration_hours);
				}
				payload.is_closed = vals.is_closed;
				if (vals.is_closed) {
					if (vals.subscribers_count) payload.subscribers_count = parseInt(vals.subscribers_count, 10);
					if (vals.avg_views) payload.avg_views = parseInt(vals.avg_views, 10);
					if (vals.er) payload.er = parseFloat(vals.er);
				}
				if (wanted?.id) payload.wanted_request_id = wanted.id;
				const created = await channelsAPI.create(payload);
				setCreatedChannel(created?.data || null);
				setSubmittedListingType(vals.listing_type);
				resetForm();
				setShowModal(true);
			} catch (err) {
				setSubmitError(err.response?.data?.detail || 'Помилка створення заявки');
			}
		},
	});

	// «Шукаю канал»: prefill category from the buyer request (?wanted=<id>)
	useEffect(() => {
		const id = parseInt(wantedId, 10);
		if (!id) return;
		wantedAPI.get(id).then(({ data }) => {
			setWanted(data);
			if (data?.category) setFieldValue('category', data.category);
		}).catch(() => setWanted(null));
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [wantedId]);

	return (
		<>
			<section className='min-h-screen pt-24 md:pt-28 pb-10 text-white'>
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
					{wanted && (
						<div className='mb-6 rounded-xl border border-accent/40 bg-accent/5 px-4 py-3 text-sm text-gray-300'>
							Запит покупця: <b className='text-white'>{wanted.category}</b>
							{wanted.budget_max ? <> · бюджет до {wanted.budget_max} USDT</> : null}. Після схвалення лоту покупець отримає сповіщення.
						</div>
					)}

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
										onBlur={(e) => {
											handleBlur(e);
											if (/^(https?:\/\/)?t\.me\/(\+|joinchat\/)/i.test(e.target.value) && !values.is_closed) {
												setFieldValue('is_closed', true);
											}
										}}
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

							{/* Closed (join-request) channel toggle */}
							<div className='mt-5'>
								<label className='flex items-center gap-3 cursor-pointer'>
									<input
										type='checkbox'
										name='is_closed'
										checked={values.is_closed}
										onChange={handleChange}
										className='w-4 h-4 rounded accent-accent'
									/>
									<span className='text-sm text-white font-medium'>🔒 Закритий канал (вступ за заявкою)</span>
								</label>
								<p className='text-xs text-gray-500 mt-1 ml-7'>
									Бот не може автоматично зчитати статистику закритих каналів — вкажіть дані вручну
								</p>
								{values.is_closed && (
									<div className='mt-3 ml-7 grid md:grid-cols-3 gap-4 p-4 bg-card-inner border border-card-border rounded-xl'>
										<InputField label='Підписників' error={errors.subscribers_count} touched={touched.subscribers_count}>
											<input
												className={inputClass}
												name='subscribers_count'
												value={values.subscribers_count}
												onChange={handleChange}
												onBlur={handleBlur}
												type='text'
												placeholder='10000'
											/>
										</InputField>
										<InputField label='Середні перегляди'>
											<input
												className={inputClass}
												name='avg_views'
												value={values.avg_views}
												onChange={handleChange}
												onBlur={handleBlur}
												type='text'
												placeholder='2000'
											/>
										</InputField>
										<InputField label='ER %'>
											<input
												className={inputClass}
												name='er'
												value={values.er}
												onChange={handleChange}
												onBlur={handleBlur}
												type='text'
												placeholder='5.5'
											/>
										</InputField>
									</div>
								)}
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

								<InputField label='Баланс каналу в Telegram Stars'>
									<input
										className={inputClass}
										name='stars_balance'
										value={values.stars_balance}
										onChange={handleChange}
										onBlur={handleBlur}
										type='text'
										inputMode='numeric'
										placeholder='Напр. 1500'
									/>
									{touched.stars_balance && errors.stars_balance && (
										<p className='text-red-400 text-xs mt-1'>{errors.stars_balance}</p>
									)}
								</InputField>

								<InputField label='Баланс каналу в TON'>
									<input
										className={inputClass}
										name='ton_balance'
										value={values.ton_balance}
										onChange={handleChange}
										onBlur={handleBlur}
										type='text'
										inputMode='decimal'
										placeholder='Напр. 12.5'
									/>
									{touched.ton_balance && errors.ton_balance && (
										<p className='text-red-400 text-xs mt-1'>{errors.ton_balance}</p>
									)}
								</InputField>

								<p className='md:col-span-2 text-xs text-gray-500 -mt-2'>
									Баланс показується покупцям як «зі слів продавця» і не впливає на ціну. Покупець підтвердить його під час передачі каналу.
								</p>

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
					channel={createdChannel}
				/>
			)}
		</>
	);
};

export default SellForm;
