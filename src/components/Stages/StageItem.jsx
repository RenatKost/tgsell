const StageItem = ({ img, number, text }) => {
	return (
		<div className='flex items-start space-x-2'>
			<div className='relative'>
				<img className='2xl:w-20 w-14' src={img} />
				<span className='absolute flex items-center justify-center rounded-[50%] bg-green-500 xl:w-8 xl:h-8 w-6 h-6 text-white bottom-0 right-0'>
					{number}
				</span>
			</div>
			<h5 className='font-bold 2xl:text-lg text-base text-white mt-4 relative stage'>
				{text}
			</h5>
		</div>
	);
};

export default StageItem;
