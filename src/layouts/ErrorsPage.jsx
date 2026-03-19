import { NavLink, useRouteError } from 'react-router-dom';

const ErrorsPage = () => {
	const error = useRouteError();
	return (
		<div className='flex items-center justify-center wrapper bg-gradient-to-tl from-blue-200  to-white '>
			<h1 className='text-5xl leading-normal tracking-widest font-bold text-[#3498db] mb-8'>
				Ой!
			</h1>
			<p className='text-[#27ae60] font-bold mb-4'>
				Вибачте, щось пішло не так
			</p>
			<p className='font-bold text-red-500'>
				{error.statusText ?? error.message}
			</p>
			<NavLink
				className='font-bold bg-white text-[#27ae60] py-4 px-10 rounded-md shadow-md shadow-green-400 hover:bg-[#27ae60] hover:text-white duration-500 mt-10'
				to='/'
			>
				На головну
			</NavLink>
		</div>
	);
};

export default ErrorsPage;
