import first from '../../assets/stages/first.png';
import five from '../../assets/stages/five.png';
import four from '../../assets/stages/four.png';
import second from '../../assets/stages/second.png';
import StageItem from './StageItem';

const buyItems = [
	{
		img: first,
		number: '1',
		text: 'Вибір каналу',
	},
	{
		img: second,
		number: '2',
		text: 'Погодження умов',
	},
	{
		img: four,
		number: '3',
		text: 'Безпечна передача',
	},
	{
		img: five,
		number: '4',
		text: 'Виплата продавцю',
	},
];

const advantages = [
	'Зручний фільтр пошуку оголошень допоможе знайти необхідне за лічені хвилини.',
	'Вам надається максимально повна інформація, яка допоможе швидко ухвалити рішення про покупку.',
	'Статистика каналу автоматично підтягується з TgStat. Це дозволяє покупцям бачити достовірні цифри.',
	'Ми надаємо гарантію переоформлення Каналу. Ви захищені від можливого шахрайства з боку продавця завдяки сервісу верифікації (перевірки на володіння каналом).',
];

const Buy = () => {
	return (
		<>
			<h2 className='text-2xl uppercase leading-normal text-center tracking-widest font-bold text-gray-600'>
				Етапи покупки
			</h2>
			<div className='lg:flex grid md:grid-cols-2 space-y-4 lg:space-y-0 max-w-[700px] lg:max-w-full mx-auto items-center bg-gradient-to-r from-blue-400  to-blue-300 px-6 py-10 rounded-xl shadow-md mt-6 justify-between'>
				{buyItems.map(({ img, number, text }) => (
					<StageItem key={text} img={img} text={text} number={number} />
				))}
			</div>
			<div className='text-lg mt-10 tracking-wider'>
				<h3 className='font-bold'>Ви можете швидко купити Телеграм канал</h3>
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

export default Buy;
