/**
 * Display-only «що далі» for a deal that is still in `created`.
 * Does not change when the address appears — that stays payment_pending-only.
 */
const DealNextSteps = ({ deal, isBuyer, isSeller, isObserver }) => {
	const buyerDone = !!deal.buyer_ready;
	const sellerDone = !!deal.seller_ready;
	const myReady = isBuyer ? buyerDone : isSeller ? sellerDone : true;

	const steps = [
		{
			n: 1,
			done: buyerDone,
			title: isBuyer && !buyerDone ? 'Підтвердіть готовність' : (buyerDone ? 'Покупець підтвердив готовність' : 'Чекаємо підтвердження покупця'),
			hint: isBuyer && !buyerDone ? 'Натисніть кнопку нижче. Угоду ще не оплачують.' : null,
		},
		{
			n: 2,
			done: sellerDone,
			title: isSeller && !sellerDone ? 'Підтвердіть готовність' : (sellerDone ? 'Продавець підтвердив готовність' : 'Чекаємо підтвердження продавця'),
			hint: isSeller && !sellerDone ? 'Натисніть кнопку нижче, щоб покупець міг оплатити.' : null,
		},
		{
			n: 3,
			done: false,
			title: "Адреса для оплати зʼявиться тут",
			hint: 'Після підтвердження обох сторін адреса ескроу буде на цій сторінці і прийде в Telegram-бот разом із посиланням на угоду.',
		},
	];

	return (
		<div className='mb-5 rounded-xl border border-accent/25 bg-accent/5 p-4'>
			<p className='text-[11px] font-semibold uppercase tracking-wider text-accent mb-3'>Що далі</p>
			<ol className='space-y-3'>
				{steps.map((s) => (
					<li key={s.n} className='flex gap-3 items-start'>
						<span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
							s.done ? 'bg-emerald-500 text-white' : 'bg-white dark:bg-slate-700 border border-gray-200 dark:border-slate-600 text-gray-500'
						}`}>
							{s.done ? '✓' : s.n}
						</span>
						<div className='min-w-0'>
							<p className={`text-sm font-semibold ${s.done ? 'text-emerald-700 dark:text-emerald-300' : 'text-gray-900 dark:text-white'}`}>
								{s.title}
							</p>
							{s.hint && <p className='text-xs text-gray-500 dark:text-gray-400 mt-0.5 leading-snug'>{s.hint}</p>}
						</div>
					</li>
				))}
			</ol>
			{!isObserver && myReady && !(buyerDone && sellerDone) && (
				<p className='text-xs text-gray-500 dark:text-gray-400 mt-3'>Ви вже підтвердили. Чекаємо іншу сторону.</p>
			)}
		</div>
	);
};

export default DealNextSteps;
