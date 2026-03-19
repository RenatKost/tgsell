import Buy from './Buy';
import Sell from './Sell';

const Stages = () => {
	return (
		<section className='pt-24'>
			<h2 className='lg:text-4xl text-3xl uppercase leading-normal text-center tracking-widest font-bold text-[#3498db] mb-8'>
				Як це працює
			</h2>
			<Buy />
			<Sell />
		</section>
	);
};

export default Stages;
