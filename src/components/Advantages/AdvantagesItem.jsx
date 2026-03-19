const AdvantagesItem = ({ title, text, img }) => {
	return (
		<div className='md:max-w-full max-w-[450px] flex md:flex-row flex-col space-x-0 md:space-x-6 bg-gradient-to-r from-blue-400  to-blue-300 px-6 py-10 rounded-xl shadow-md items-start text-white'>
			<div className='md:border-r-2 md:px-4 w-28 md:w-40 mb-4 md:mb-0'>
				<img src={img} />
			</div>
			<div className='max-w-[400px]'>
				<h6 className='font-bold text-2xl md:mb-6 mb-3'>{title}</h6>
				<p className='text-lg'>{text}</p>
			</div>
		</div>
	);
};

export default AdvantagesItem;
