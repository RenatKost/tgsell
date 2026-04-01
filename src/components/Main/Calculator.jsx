import { useState } from 'react';

export const options = [
	{ coef: '1.3', label: 'Новини/ЗМІ' },
	{ coef: '1.2', label: 'Регіональні' },
	{ coef: '1', label: 'Пізнавальні' },
	{ coef: '1', label: 'Гумор' },
	{ coef: '1', label: 'Жіночі' },
	{ coef: '1.2', label: 'Лінгвістика' },
	{ coef: '1', label: 'Вульгарні' },
	{ coef: '1', label: 'Кулінарія' },
	{ coef: '1.1', label: 'Вакансія/Робота' },
	{ coef: '2', label: 'Криптовалюта' },
	{ coef: '1', label: 'Чоловіче' },
	{ coef: '1.3', label: 'Авто/Мото' },
	{ coef: '1.2', label: 'Новини 18+' },
	{ coef: '1.3', label: 'Політика' },
	{ coef: '1', label: 'Медицина' },
	{ coef: '1', label: 'Музика' },
	{ coef: '1.2', label: 'Подорожі/Країни' },
	{ coef: '1.7', label: 'Бізнес' },
	{ coef: '1.7', label: 'ІТ/Додатки' },
	{ coef: '1.4', label: 'Дизайн' },
	{ coef: '1.5', label: 'Авторські' },
	{ coef: '1', label: 'Історичні' },
	{ coef: '1', label: 'Спорт' },
	{ coef: '1', label: 'Товари/Магазини' },
	{ coef: '1', label: 'Кіно/Мультфільми' },
	{ coef: '1.8', label: 'Інвестиції/Акції' },
	{ coef: '1', label: 'Блогери' },
	{ coef: '1', label: 'Гороскопи' },
	{ coef: '1', label: 'Фотографії' },
	{ coef: '1', label: 'Ігри' },
	{ coef: '1', label: 'Тварини' },
	{ coef: '1', label: 'Цитати' },
	{ coef: '1', label: 'Аніме' },
	{ coef: '1.7', label: 'Нерухомість' },
	{ coef: '1', label: 'Релігія' },
	{ coef: '1.7', label: 'Нейромережі' },
	{ coef: '1', label: 'Щоу бізнес' },
	{ coef: '1', label: 'Мистецтво' },
	{ coef: '1', label: 'Інше' },
];

const trafficItems = [
	{ coef: '1', label: 'Telegram' },
	{ coef: '0.5', label: 'ТікTok' },
	{ coef: '1', label: 'Meta' },
	{ coef: '1', label: 'Інше' },
];

const Calculator = () => {
	const [categoryCoef, setCategoryCoef] = useState(0);
	const [trafficCoef, setTrafficCoef] = useState(0);
	const [subscribers, setSubscribers] = useState(0);
	const [applications, setApplications] = useState(0);
	const [income, setIncome] = useState(0);
	const [reach, setReach] = useState(0);

	const handleCategoryChange = e => {
		const selectedCategory = e.target.value;
		const selectedCategoryCoef =
			options.find(option => option.label === selectedCategory)?.coef || '0';
		const categoryCoef = parseFloat(selectedCategoryCoef) || 0;
		setCategoryCoef(categoryCoef);
	};

	const handleTrafficChange = e => {
		const selectedTraffic = e.target.value;
		const selectedTrafficCoef =
			trafficItems.find(item => item.label === selectedTraffic)?.coef || '0';
		const trafficCoef = parseFloat(selectedTrafficCoef) || 0;
		setTrafficCoef(trafficCoef);
	};

	const handleSubscribersChange = e => {
		const value = e.target.value;
		const parsedValue = value ? parseFloat(value) : 0;
		setSubscribers(parsedValue);
	};

	const handleApplicationsChange = e => {
		const value = e.target.value;
		const parsedValue = value ? parseFloat(value) : 0;
		setApplications(parsedValue);
	};

	const handleIncomeChange = e => {
		const value = e.target.value;
		const parsedValue = value ? parseFloat(value) : 0;
		setIncome(parsedValue);
	};

	const handleReachChange = e => {
		const value = e.target.value;
		const parsedValue = value ? parseFloat(value) : 0;
		setReach(parsedValue);
	};

	const calculateTotal = () => {
		const total =
			3 * subscribers * categoryCoef * trafficCoef +
			applications * categoryCoef * trafficCoef +
			income * categoryCoef * trafficCoef +
			reach * 0.25 * categoryCoef * trafficCoef +
			income * 3;

		return isNaN(total) ? 0 : Math.round(total);
	};

	const formatCurrency = number => {
		return new Intl.NumberFormat('uk-UA', {
			minimumFractionDigits: 0,
			maximumFractionDigits: 2,
		}).format(number) + ' USDT';
	};

	return (
		<div className='mt-10'>
			<div className='mb-10'>
				<h2 className='font-bold text-xl dark:text-white'>
					Калькулятор вартості Telegram каналу
				</h2>
			</div>
			<form className='grid sm:grid-cols-2 gap-8'>
				<div>
					<label>Категорія:</label>
					<select
						className='focus:border-[#3498db] block border-gray-300 border px-3 py-4 rounded-md mt-1 w-full'
						name='theme'
						type='text'
						defaultValue='placeholder'
						onChange={handleCategoryChange}
					>
						<option value='placeholder' disabled hidden data-coef={0}>
							Виберіть категорію
						</option>
						{options.map(option => (
							<option key={option.label} data-coef={option.coef}>
								{option.label}
							</option>
						))}
					</select>
				</div>
				<div>
					<label>Трафік:</label>
					<select
						className='focus:border-[#3498db] block border-gray-300 border px-3 py-4 rounded-md mt-1 w-full'
						name='theme'
						type='text'
						defaultValue='placeholder'
						onChange={handleTrafficChange}
					>
						<option value='placeholder' disabled hidden data-coef={0}>
							Виберіть трафік
						</option>
						{trafficItems.map(option => (
							<option key={option.label} data-coef={option.coef}>
								{option.label}
							</option>
						))}
					</select>
				</div>
				<div>
					<label>Кількість підписників:</label>
					<input
						className='focus:border-[#3498db] block border-gray-300 dark:border-slate-600 border px-3 py-4 rounded-md mt-1 w-full dark:bg-slate-800 dark:text-white '
						name='subscribers'
						type='text'
						placeholder='Підписників'
						onChange={handleSubscribersChange}
						data-coef={1}
					/>
				</div>
				<div>
					<label>Кількість заявок:</label>
					<input
						className='focus:border-[#3498db] block border-gray-300 dark:border-slate-600 border px-3 py-4 rounded-md mt-1 w-full dark:bg-slate-800 dark:text-white '
						name='applications'
						type='text'
						placeholder='Заявок'
						data-coef={1}
						onChange={handleApplicationsChange}
					/>
				</div>
				<div>
					<label>Місячний дохід (USDT):</label>
					<input
						className='focus:border-[#3498db] block border-gray-300 dark:border-slate-600 border px-3 py-4 rounded-md mt-1 w-full dark:bg-slate-800 dark:text-white '
						name='applications'
						type='text'
						placeholder='0 USDT'
						data-coef={1}
						onChange={handleIncomeChange}
					/>
				</div>
				<div>
					<label>Охоплення:</label>
					<input
						className='focus:border-[#3498db] block border-gray-300 dark:border-slate-600 border px-3 py-4 rounded-md mt-1 w-full dark:bg-slate-800 dark:text-white '
						name='applications'
						type='text'
						placeholder='Охоплення'
						data-coef={0.25}
						onChange={handleReachChange}
					/>
				</div>
			</form>
			<h3 className='mt-10 dark:text-gray-200'>
				<span className='font-bold mr-2 text-lg'>Вартість:</span>
				<span className='text-red-500 font-bold mr-1'>
					{formatCurrency(calculateTotal())}
				</span>
				(*Кінцева вартість визначається продавцем)
			</h3>
		</div>
	);
};

export default Calculator;
