// Task 24: saved catalog searches in the cabinet (list + delete).
import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { savedSearchesAPI } from '../../services/api';

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

	if (loading) {
		return (
			<div className='flex justify-center py-20'>
				<div className='animate-spin rounded-full h-10 w-10 border-b-2 border-blue-500' />
			</div>
		);
	}

	return (
		<div>
			<p className='text-sm text-gray-500 dark:text-gray-400 mb-4'>
				Збережено {items.length} з {max}. Коли з’явиться новий канал за вашими фільтрами, ми надішлемо
				повідомлення в @tgsell_alert_bot (не частіше ніж раз на годину для кожного пошуку).
			</p>
			{error && <p className='text-sm text-red-500 mb-3'>{error}</p>}
			{items.length === 0 ? (
				<div className='text-center py-16 bg-white dark:bg-slate-800 rounded-2xl border border-dashed border-gray-300 dark:border-slate-600'>
					<div className='text-5xl mb-4'>🔔</div>
					<p className='text-lg font-semibold text-gray-700 dark:text-gray-200 mb-2'>У вас поки немає збережених пошуків</p>
					<p className='text-gray-500 dark:text-gray-400 mb-6'>Налаштуйте фільтри в каталозі та натисніть «Зберегти пошук»</p>
					<NavLink to='/catalog' className='inline-flex items-center gap-2 font-bold bg-[#3498db] text-white py-3 px-8 rounded-xl hover:bg-[#2980b9] duration-300'>
						Перейти до каталогу
					</NavLink>
				</div>
			) : (
				<div className='flex flex-col gap-3'>
					{items.map(s => (
						<div key={s.id} className='flex items-center gap-3 bg-white dark:bg-slate-800 rounded-xl border border-gray-100 dark:border-slate-700 p-4'>
							<div className='min-w-0 flex-1'>
								<div className='font-semibold text-gray-900 dark:text-white truncate'>{s.name}</div>
								<div className='text-xs text-gray-500 dark:text-gray-400'>
									Створено {s.created_at ? new Date(s.created_at + 'Z').toLocaleDateString('uk-UA') : '—'}
									{s.last_delivery_status && STATUS[s.last_delivery_status] && (
										<span className={`ml-2 ${STATUS[s.last_delivery_status].cls}`}>· {STATUS[s.last_delivery_status].text}</span>
									)}
								</div>
							</div>
							<button onClick={() => remove(s.id)}
								className='text-sm text-red-500 hover:text-red-600 font-semibold px-3 py-1.5 rounded-lg border border-red-200 dark:border-red-900/40 hover:bg-red-50 dark:hover:bg-red-900/20'>
								Видалити
							</button>
						</div>
					))}
				</div>
			)}
		</div>
	);
};

export default SavedSearches;
