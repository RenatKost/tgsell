import { useFormik } from 'formik';
import { useState } from 'react';
import * as Yup from 'yup';
import { channelsAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import { options } from './Main/Calculator';
import { useNavigate } from 'react-router-dom';

const SellForm = () => {
	const { isAuthenticated } = useAuth();
	const navigate = useNavigate();
	const [submitError, setSubmitError] = useState('');

	const {
		handleSubmit,
		handleChange,
		handleBlur,
		values,
		errors,
		touched,
		isSubmitting,
		status,
	} = useFormik({
		initialValues: {
			telegram_link: '',
			channel_name: '',
			category: '',
			price: '',
			monthly_income: '',
			description: '',
			resource1: '',
			resource2: '',
		},
		validationSchema: Yup.object({
			telegram_link: Yup.string()
				.matches(/^\S*$/, 'Не повинен містити пробілів')
				.required('Поле обов\'язкове для заповнення'),
			channel_name: Yup.string()
				.required('Поле обов\'язкове для заповнення'),
			category: Yup.string()
				.required('Оберіть тематику'),
			price: Yup.number()
				.typeError('Введіть число')
				.positive('Ціна повинна бути більше 0')
				.required('Поле обов\'язкове для заповнення'),
		}),
		onSubmit: async (vals, { resetForm, setStatus }) => {
			if (!isAuthenticated) {
				setSubmitError('Увійдіть для подання заявки');
				return;
			}
			setSubmitError('');
			try {
				const resources = [vals.resource1, vals.resource2].filter(Boolean).join('\n');
				await channelsAPI.create({
					telegram_link: vals.telegram_link,
					channel_name: vals.channel_name,
					category: vals.category,
					price: parseFloat(vals.price),
					monthly_income: vals.monthly_income ? parseFloat(vals.monthly_income) : null,
					description: vals.description || null,
					resources: resources || null,
				});
				setStatus('Ваша заявка відправлена на модерацію!');
				setTimeout(() => {
					resetForm();
					navigate('/cabinet');
				}, 2000);
			} catch (err) {
				setSubmitError(err.response?.data?.detail || 'Помилка створення заявки');
			}
		},
	});

	return (
		<section className='my-28'>
			<h1 className='uppercase leading-normal tracking-widest font-bold text-center text-2xl md:text-3xl lg:text-4xl text-[#3498db]'>
				Заявка на продаж каналу
			</h1>
			<form
				className='rounded-md shadow-md lg:w-[70vw] sm:w-[80vw] mx-auto my-10 bg-white px-8 py-10'
				onSubmit={handleSubmit}
			>
				<h3 className='text-lg font-bold uppercase mb-8'>{"Обов'язкові поля"}</h3>
				<div className='grid lg:grid-cols-2 items-center gap-8 border-b-[1px] pb-10'>
					<div className='h-28'>
						<label className='text-sm block'>Посилання на канал</label>
						<input
							className='focus:border-[#3498db] block mb-1 border-gray-300 border px-3 py-4 rounded-md mt-1 w-full'
							name='telegram_link'
							value={values.telegram_link}
							onChange={handleChange}
							onBlur={handleBlur}
							type='text'
							placeholder='@username або https://t.me/...'
						/>
						{touched.telegram_link && errors.telegram_link && (
							<span className='text-sm text-red-500'>{errors.telegram_link}</span>
						)}
					</div>
					<div className='h-28'>
						<label className='text-sm block'>Назва каналу</label>
						<input
							className='focus:border-[#3498db] block mb-1 border-gray-300 border px-3 py-4 rounded-md mt-1 w-full'
							name='channel_name'
							value={values.channel_name}
							onChange={handleChange}
							onBlur={handleBlur}
							type='text'
							placeholder='Назва вашого каналу'
						/>
						{touched.channel_name && errors.channel_name && (
							<span className='text-sm text-red-500'>{errors.channel_name}</span>
						)}
					</div>
					<div className='h-28'>
						<label className='text-sm'>Тематика</label>
						<select
							className='focus:border-[#3498db] block border-gray-300 border px-3 py-4 rounded-md mt-1 w-full'
							name='category'
							value={values.category}
							onChange={handleChange}
							onBlur={handleBlur}
						>
							<option value='' disabled hidden>
								Виберіть тематику каналу
							</option>
							{options.map(option => (
								<option key={option.label} value={option.label}>
									{option.label}
								</option>
							))}
						</select>
						{touched.category && errors.category && (
							<span className='text-sm text-red-500'>{errors.category}</span>
						)}
					</div>
					<div className='h-28'>
						<label className='text-sm'>Вартість каналу (USDT)</label>
						<input
							className='focus:border-[#3498db] block border-gray-300 border px-3 py-4 rounded-md mt-1 w-full'
							name='price'
							value={values.price}
							onChange={handleChange}
							onBlur={handleBlur}
							type='text'
							placeholder='Введіть ціну в USDT'
						/>
						{touched.price && errors.price && (
							<span className='text-sm text-red-500'>{errors.price}</span>
						)}
					</div>
				</div>
				<div className='pt-10'>
					<h3 className='text-lg font-bold uppercase mb-8'>Деталі</h3>
					<div>
						<label className='text-sm'>Поточний дохід в місяць (USDT)</label>
						<input
							className='focus:border-[#3498db] block border-gray-300 border px-3 py-4 rounded-md mt-1 w-full lg:w-[47.8%]'
							name='monthly_income'
							value={values.monthly_income}
							onChange={handleChange}
							onBlur={handleBlur}
							type='text'
							placeholder='Місячний дохід'
						/>
					</div>
					<div className='mt-7'>
						<label className='text-sm'>Опис каналу</label>
						<textarea
							className='focus:border-[#3498db] block border-gray-300 border px-3 py-4 rounded-md mt-1 w-full h-28'
							name='description'
							value={values.description}
							onChange={handleChange}
							onBlur={handleBlur}
							placeholder='Розкажіть про ваш канал щоб зацікавити покупця'
						/>
					</div>
					<div className='mt-7 grid lg:grid-cols-2 gap-8'>
						<div>
							<label className='text-sm'>Додаткові ресурси</label>
							<input
								className='focus:border-[#3498db] block border-gray-300 border px-3 py-4 rounded-md mt-1 w-full'
								name='resource1'
								value={values.resource1}
								onChange={handleChange}
								onBlur={handleBlur}
								type='url'
								placeholder='Введіть URL'
							/>
						</div>
						<div>
							<label className='text-sm'>Додаткові ресурси</label>
							<input
								className='focus:border-[#3498db] block border-gray-300 border px-3 py-4 rounded-md mt-1 w-full'
								name='resource2'
								value={values.resource2}
								onChange={handleChange}
								onBlur={handleBlur}
								type='url'
								placeholder='Введіть URL'
							/>
						</div>
					</div>
				</div>
				<button
					type='submit'
					disabled={isSubmitting}
					className='font-bold text-[#27ae60] py-4 px-10 uppercase rounded-md shadow-md hover:shadow-green-400 hover:bg-[#27ae60] hover:text-white duration-500 mt-10 disabled:opacity-50'
				>
					{isSubmitting ? 'Відправка...' : 'Надіслати'}
				</button>
				{status && <span className='block mt-4 text-green-600 font-bold'>{status}</span>}
				{submitError && <span className='block mt-4 text-red-500'>{submitError}</span>}
			</form>
		</section>
	);
};

export default SellForm;
