import clock from '../../assets/Advantages/clock.png';
import guard from '../../assets/Advantages/guard.png';
import help from '../../assets/Advantages/help.png';
import tech from '../../assets/Advantages/interface.png';
import range from '../../assets/Advantages/range.png';
import support from '../../assets/Advantages/support.png';

import AdvantagesItem from './AdvantagesItem';

const advantagesItems = [
	{
		img: clock,
		title: 'Час',
		text: 'Економія часу і грошей',
	},
	{
		img: guard,
		title: 'Захист',
		text: 'Гарантія захисту від шахрайства',
	},
	{
		img: support,
		title: 'Підтримка',
		text: 'Допомога професіоналів по підбору покупця/продавця',
	},
	{
		img: help,
		title: 'Супроводження',
		text: 'Супроводження справи, детальна інструкція про всі деталі її проведення',
	},
	{
		img: range,
		title: 'Асортимент',
		text: 'Широкий асортимент телеграм каналів',
	},
	{
		img: tech,
		title: 'Інтерфейс',
		text: 'Зручний інтерфейс для пошуку відповідного телеграм каналу/покупця',
	},
];

const Advantages = () => {
	return (
		<section className='pt-24'>
			<h2 className='lg:text-4xl text-3xl uppercase leading-normal text-center tracking-widest font-bold text-[#3498db] mb-8'>
				Переваги працювати з нами
			</h2>
			<div className='grid xl:grid-cols-2 gap-12 justify-center'>
				{advantagesItems.map(({ img, title, text }) => (
					<AdvantagesItem key={title} img={img} title={title} text={text} />
				))}
			</div>
		</section>
	);
};

export default Advantages;
