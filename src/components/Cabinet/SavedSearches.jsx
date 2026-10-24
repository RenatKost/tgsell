// Task 24: saved catalog searches in the cabinet (list + delete).
import { useEffect, useState } from 'react';
import { savedSearchesAPI } from '../../services/api';
import { Spinner, EmptyState, LinkButton, surface, btnDanger } from './ui';

const STATUS = {
	sent: { text: 'Сповіщення надіслано', cls: 'text-green-600 dark:text-green-400' },
	not_started: { text: 'Не доставлено: запустіть @tgsell_alert_bot (Start)', cls: 'text-amber-600 dark:text-amber-400' },
	failed: { text: 'Не доставлено: помилка надсилання', cls: 'text-red-500' },
};

const SavedSearches = () => {
	const [items, setItems] = useState([]);
	const [max, setMax] = useState(10);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState('');

	const load = () => {
		setLoading(true);
		savedSearchesAPI.getAll()
			.then(({ data }) => { setItems(data.items || []); setMax(data.max || 10); })
			.catch(() => setError('Не вдалося завантажити збережені пошуки'))
			.finally(() => setLoading(false));
	};
	useEffect(load, []);

	const remove = async (id) => {
		if (!window.confirm('Видалити збережений пошук?')) return;
		try {
			await savedSearchesAPI.remove(id);
			setItems(items.filter(i => i.id !== id));
		} catch {
			setError('Не вдалося видалити пошук');
		}
	};

	if (loading) return <Spinner />;

	return (
		<div>
			<p className='text-sm text-gray-500 dark:text-gray-400 mb-4 leading-relaxed'>
				Збережено <span className='font-semibold text-gray-800 dark:text-gray-200'>{items.length} з {max}</span>. Коли з’явиться новий канал за вашими фільтрами,
				ми надішлемо повідомлення в @tgsell_alert_bot (не частіше ніж раз на годину для кожного пошуку).
			</p>
			{error && (
				<p role='alert' className='text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-900/40 rounded-xl px-3 py-2 mb-4'>{error}</p>
			)}
			{items.length === 0 ? (
				!error && (
					<EmptyState
						icon='🔔'
						title='У вас поки немає збережених пошуків'
						text='Налаштуйте фільтри в каталозі та натисніть «Зберегти пошук».'
						action={<LinkButton to='/catalog'>Перейти до каталогу</LinkButton>}
					/>
				)
			) : (
				<ul className='flex flex-col gap-3'>
					{items.map(s => (
						<li key={s.id} className={`${surface} flex flex-col sm:flex-row sm:items-center gap-3 p-4`}>
							<div className='min-w-0 flex-1'>
								<div className='font-semibold text-gray-900 dark:text-white leading-snug break-words line-clamp-2'>{s.name}</div>
								<div className='text-xs text-gray-500 dark:text-gray-400 mt-1 leading-relaxed'>
									Створено {s.created_at ? new Date(s.created_at + 'Z').toLocaleDateString('uk-UA') : '—'}
									{s.last_delivery_status && STATUS[s.last_delivery_status] && (
										<span className={`block sm:inline sm:ml-2 ${STATUS[s.last_delivery_status].cls}`}><span className='hidden sm:inline'>· </span>{STATUS[s.last_delivery_status].text}</span>
									)}
								</div>
							</div>
							<button type='button' onClick={() => remove(s.id)} className={`${btnDanger} w-full sm:w-auto`}>
								Видалити
							</button>
						</li>
					))}
				</ul>
			)}
		</div>
	);
};

export default SavedSearches;
