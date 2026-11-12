/** Intent-aware copy for the guest login modal on a lot page. */

export function loginModalCopy(intent) {
	if (intent === 'offer') {
		return {
			title: 'Увійдіть, щоб запропонувати ціну',
			subtitle: 'Вхід через Telegram займає кілька секунд. Після входу ви зможете надіслати продавцю свою ціну — угода не створюється автоматично.',
		};
	}
	return {
		title: 'Увійдіть, щоб купити канал',
		subtitle: 'Вхід через Telegram займає кілька секунд. Кошти будуть під захистом гаранта (ескроу), доки ви не підтвердите угоду.',
	};
}
