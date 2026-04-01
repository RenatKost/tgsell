import eight from '../../assets/stages/eight.png';
import five from '../../assets/stages/five.png';
import nine from '../../assets/stages/nine.png';
import seven from '../../assets/stages/seven.png';
import six from '../../assets/stages/six.png';
import StageItem from './StageItem';

const sellItems = [
	{
		img: seven,
		number: '1',
		text: 'Реєстрація',
	},
	{
		img: six,
		number: '2',
		text: 'Заповнення форми',
	},
	{
		img: eight,
		number: '3',
		text: 'Модерація',
	},
	{
		img: nine,
		number: '4',
		text: 'Оплата',
	},
	{
		img: five,
		number: '5',
		text: 'Виплата продавцю',
	},
];

const advantages = [
	'Величезна аудиторія нашого сайту – гарантія швидкого та вигідного продажу.',
	'Ви можете додати оголошення за кілька хвилин.',
	'Ми гарантуємо повний захист від шахрайства шляхом попереднього резервування коштів (гарант сервісу спеціально адаптованого під купівлю/продаж каналів).',
];

const Sell = () => {
	return (
		<>
			<h2 className='text-2xl uppercase leading-normal text-center tracking-widest font-bold mt-12 text-gray-600 dark:text-gray-300'>
				Етапи продажу
			</h2>
			<div className='xl:flex items-center grid md:grid-cols-2 space-y-4 xl:space-y-0 max-w-[700px] lg:max-w-full mx-auto bg-gradient-to-r from-blue-400  to-blue-300 px-6 py-10 rounded-xl shadow-md mt-6 justify-between'>
				{sellItems.map(({ img, number, text }) => (
					<StageItem key={text} img={img} text={text} number={number} />
				))}
			</div>
			<div className='text-lg mt-10 tracking-wider dark:text-gray-300'>
				<h3 className='font-bold dark:text-white'>Ви хочете продати свій телеграм канал?</h3>
				<ul className='mt-2 space-y-4'>
					{advantages.map(item => (
						<li key={item} className='text-start'>
							<span className='w-2 h-2 rounded-[50%] bg-[#27ae60] mr-3 inline-block' />
							{item}
						</li>
					))}
				</ul>
			</div>
		</>
	);
};

export default Sell;
