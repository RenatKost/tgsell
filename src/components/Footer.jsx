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
		<footer className='mt-14 justify-center py-5 sm:py-10 lg:flex grid sm:grid-cols-2 items-center gap-5 md:gap-20 bg-white w-full px-5 md:px-12 shadow-md'>
			<div className='text-2xl font-bold text-center sm:text-start text-[#3498db]'>
				<a href='/'>TgSell</a>
			</div>
			<div className='lg:flex grid items-center lg:w-full ml-0 sm:ml-auto lg:ml-0 justify-between'>
				<ul className='flex items-center sm:justify-normal justify-around gap-6'>
					{footerLinks.map(({ text, src }) => (
						<li className='xl:mb-0' key={text}>
							<a
								href={src}
								className='text-[#27ae60] hover:scale-105 font-bold sm:text-lg text-base duration-500 hover:text-green-400'
							>
								{text}
							</a>
						</li>
					))}
				</ul>
				<div className='lg:flex grid lg:space-x-10 space-x-0 lg:space-y-0 space-y-2 mt-2 lg:mt-0 font-bold'>
					<a
						className='text-[#3498db] hover:text-blue-400 duration-300 sm:text-base text-sm'
						href='#'
					>
						Політика конфіденційності
					</a>
					<a
						className='text-[#3498db] hover:text-blue-400 duration-300 sm:text-base text-sm text-center sm:text-start'
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
