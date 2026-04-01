const footerLinks = [
	{
		text: 'Email',
		src: 'mailto:wavschool.sup@gmail.com',
	},
	{
		text: 'Telegram',
		src: 'https://t.me/WaV_School_Courses',
	},
];

const Footer = () => {
	return (
		<footer id='footer' className='mt-14 justify-center py-5 sm:py-10 lg:flex grid sm:grid-cols-2 items-center gap-5 md:gap-20 bg-white dark:bg-slate-900 w-full px-5 md:px-12 shadow-md dark:shadow-slate-800/50 border-t border-gray-100 dark:border-slate-800 transition-colors duration-300'>
			<div className='sm:text-start text-center'>
				<a href='/'>
					<img src='/logo.png' alt='TgSell' className='h-10 w-auto object-contain inline-block' />
				</a>
			</div>
			<div className='lg:flex grid items-center lg:w-full ml-0 sm:ml-auto lg:ml-0 justify-between'>
				<ul className='flex items-center sm:justify-normal justify-around gap-6'>
					{footerLinks.map(({ text, src }) => (
						<li className='xl:mb-0' key={text}>
							<a
								href={src}
								className='text-emerald-500 hover:text-emerald-400 font-bold sm:text-lg text-base duration-300'
							>
								{text}
							</a>
						</li>
					))}
				</ul>
				<div className='lg:flex grid lg:space-x-10 space-x-0 lg:space-y-0 space-y-2 mt-2 lg:mt-0 font-bold'>
					<a
						className='text-gray-500 dark:text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 duration-300 sm:text-base text-sm'
						href='#'
					>
						Політика конфіденційності
					</a>
					<a
						className='text-gray-500 dark:text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 duration-300 sm:text-base text-sm text-center sm:text-start'
						href='#'
					>
						Публічна оферта
					</a>
				</div>
			</div>
		</footer>
	);
};

export default Footer;
