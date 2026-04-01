import { NavLink } from 'react-router-dom';
import hero from '../../assets/header.png';
import Calculator from './Calculator';

const Main = () => {
	return (
		<section className='flex items-center justify-between pt-28 gap-4 lg:flex-row flex-col'>
			<div className='xl:max-w-2xl max-w-full	'>
				<h1 className='xl:text-5xl md:text-4xl text-3xl uppercase leading-normal tracking-widest font-bold text-[#3498db] mb-8'>
					Українська біржа
					<br /> телеграм каналів
				</h1>
				<p className='text-xl leading-normal dark:text-gray-300'>
					Знайди свій успіх в Telegram! Відкрий нові горизонти з нашою біржею
				</p>
				<div className='flex items-start sm:items-center sm:space-x-8 sm:flex-row flex-col'>
					<NavLink
						className='font-bold bg-white dark:bg-slate-800 text-[#27ae60] py-4 px-10 w-[225px] rounded-md shadow-md shadow-green-400 dark:shadow-green-900/30 hover:bg-[#27ae60] hover:text-white duration-500 mt-10'
						to='/catalog'
					>
						КУПИТИ КАНАЛ
					</NavLink>
					<NavLink
						className='font-bold bg-[#27ae60] text-white w-[225px] py-4 px-8 rounded-md shadow-md shadow-green-400 hover:bg-white hover:text-[#27ae60] duration-500 mt-10'
						to='/sell'
					>
						ПРОДАТИ КАНАЛ
					</NavLink>
				</div>
				<Calculator />
			</div>
			<div className='mx-auto'>
				<img src={hero} />
			</div>
		</section>
	);
};

export default Main;
