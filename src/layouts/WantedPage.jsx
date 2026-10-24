import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { wantedAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import { options as categoryOptions } from '../components/Main/Calculator';
import { LANGUAGE_LABELS, fmtRange, fmtDate } from '../utils/wanted';

const CATEGORIES = categoryOptions.map((o) => o.label).filter((l) => !l.includes('18+'));
const inputCls = 'w-full bg-white dark:bg-slate-900 border border-gray-200 dark:border-card-border rounded-xl px-3 py-2.5 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:border-accent';
const EMPTY = { category: '', subs_min: '', subs_max: '', budget_min: '', budget_max: '', language: 'ua', comment: '' };

const WantedCard = ({ r }) => (
	<div className='bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-5 flex flex-col gap-3'>
		<div className='flex items-start justify-between gap-2'>
			<span className='text-lg font-bold text-gray-900 dark:text-white'>{r.category}</span>
			<span className='text-xs text-gray-400 whitespace-nowrap'>{fmtDate(r.created_at)}</span>
		</div>
		<dl className='grid grid-cols-2 gap-2 text-sm'>
			<div><dt className='text-gray-400 text-xs'>Підписники</dt><dd className='text-gray-800 dark:text-gray-200 font-semibold'>{fmtRange(r.subs_min, r.subs_max)}</dd></div>
			<div><dt className='text-gray-400 text-xs'>Бюджет</dt><dd className='text-gray-800 dark:text-gray-200 font-semibold'>{fmtRange(r.budget_min, r.budget_max, 'USDT')}</dd></div>
			<div><dt className='text-gray-400 text-xs'>Мова/гео</dt><dd className='text-gray-800 dark:text-gray-200 font-semibold'>{r.language_label || LANGUAGE_LABELS[r.language] || r.language}</dd></div>
		</dl>
		{r.comment && <p className='text-sm text-gray-600 dark:text-gray-400 break-words'>{r.comment}</p>}
		<Link to={`/sell?wanted=${r.id}&src=wanted`}
			className='mt-auto text-center bg-accent/10 hover:bg-accent/20 text-accent border border-accent/50 font-semibold rounded-xl py-2.5 text-sm transition-colors'>
			У мене є такий канал
		</Link>
	</div>
);

const WantedForm = ({ onDone, onCancel }) => {
	const [v, setV] = useState(EMPTY);
	const [err, setErr] = useState('');
	const [busy, setBusy] = useState(false);
	const set = (k) => (e) => setV({ ...v, [k]: e.target.value });
	const num = (x) => (x === '' ? null : Number(x));

	const submit = async (e) => {
		e.preventDefault();
		if (!v.category) { setErr('Оберіть тематику'); return; }
		if (v.budget_max === '') { setErr('Вкажіть бюджет «до»'); return; }
		setBusy(true); setErr('');
		try {
			await wantedAPI.create({
				category: v.category, language: v.language, comment: v.comment.trim() || null,
				subs_min: num(v.subs_min), subs_max: num(v.subs_max),
				budget_min: num(v.budget_min), budget_max: num(v.budget_max),
			});
			setV(EMPTY);
			onDone();
		} catch (ex) {
			const d = ex?.response?.data?.detail;
			setErr(typeof d === 'string' ? d : 'Перевірте поля форми');
		} finally { setBusy(false); }
	};

	return (
		<form onSubmit={submit} className='bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-5 space-y-4'>
			<div>
				<label className='block text-xs text-gray-400 mb-1'>Тематика</label>
				<select className={inputCls} value={v.category} onChange={set('category')}>
					<option value=''>Оберіть тематику</option>
					{CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
				</select>
			</div>
			<div className='grid grid-cols-2 gap-3'>
				<div><label className='block text-xs text-gray-400 mb-1'>Підписники від</label><input type='number' min='0' className={inputCls} value={v.subs_min} onChange={set('subs_min')} /></div>
				<div><label className='block text-xs text-gray-400 mb-1'>Підписники до</label><input type='number' min='0' className={inputCls} value={v.subs_max} onChange={set('subs_max')} /></div>
				<div><label className='block text-xs text-gray-400 mb-1'>Бюджет від, USDT</label><input type='number' min='0' step='any' className={inputCls} value={v.budget_min} onChange={set('budget_min')} /></div>
				<div><label className='block text-xs text-gray-400 mb-1'>Бюджет до, USDT</label><input type='number' min='0' step='any' className={inputCls} value={v.budget_max} onChange={set('budget_max')} /></div>
			</div>
			<div>
				<label className='block text-xs text-gray-400 mb-1'>Мова/гео аудиторії</label>
				<select className={inputCls} value={v.language} onChange={set('language')}>
					{Object.entries(LANGUAGE_LABELS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
				</select>
			</div>
			<div>
				<label className='block text-xs text-gray-400 mb-1'>Коментар (до 300 символів)</label>
				<textarea maxLength={300} rows={3} className={inputCls} value={v.comment} onChange={set('comment')}
					placeholder='Що для вас важливо. Без контактів і посилань — ми сповістимо вас самі.' />
				<div className='text-right text-xs text-gray-400'>{v.comment.length}/300</div>
			</div>
			<p className='text-xs text-gray-400'>Запит з'явиться після модерації і буде активним 30 днів. Максимум 3 активні запити. Ваші контакти не показуються — коли з'явиться відповідний канал, ми надішлемо сповіщення в Telegram-бот.</p>
			{err && <div className='text-sm text-red-500'>{err}</div>}
			<div className='flex gap-3'>
				<button type='submit' disabled={busy} className='flex-1 bg-accent text-black font-bold rounded-xl py-2.5 text-sm disabled:opacity-60'>{busy ? 'Надсилаємо…' : 'Надіслати на модерацію'}</button>
				<button type='button' onClick={onCancel} className='px-4 border border-gray-200 dark:border-card-border rounded-xl text-sm text-gray-600 dark:text-gray-300'>Скасувати</button>
			</div>
		</form>
	);
};

const STATUS_UA = { pending: 'На модерації', approved: 'Опубліковано', rejected: 'Відхилено', closed: 'Закрито' };

const WantedPage = () => {
	const { isAuthenticated } = useAuth();
	const [items, setItems] = useState([]);
	const [loading, setLoading] = useState(true);
	const [showForm, setShowForm] = useState(false);
	const [mine, setMine] = useState(null);
	const [notice, setNotice] = useState('');

	const load = async () => {
		setLoading(true);
		try { const { data } = await wantedAPI.list(); setItems(data.items || []); } catch { setItems([]); }
		finally { setLoading(false); }
	};
	const loadMine = async () => {
		if (!isAuthenticated) { setMine(null); return; }
		try { const { data } = await wantedAPI.mine(); setMine(data); } catch { setMine(null); }
	};
	useEffect(() => { load(); }, []);
	useEffect(() => { loadMine(); }, [isAuthenticated]); // eslint-disable-line react-hooks/exhaustive-deps

	const onCreate = () => {
		if (!isAuthenticated) { setNotice('Увійдіть, щоб залишити запит'); return; }
		setNotice(''); setShowForm(true);
	};
	const closeReq = async (id) => {
		if (!window.confirm('Закрити цей запит?')) return;
		try { await wantedAPI.close(id); await Promise.all([load(), loadMine()]); } catch { /* ignore */ }
	};

	return (
		<section className='min-h-screen pt-24 md:pt-28 pb-16'>
			<div className='max-w-6xl mx-auto px-4'>
				<div className='flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8'>
					<div>
						<h1 className='text-3xl md:text-4xl font-black text-gray-900 dark:text-white'>Шукаю <span className='text-accent'>канал</span></h1>
						<p className='text-gray-500 dark:text-gray-400 mt-1'>Запити покупців. Маєте відповідний канал — виставте його на продаж.</p>
					</div>
					<button onClick={onCreate} className='bg-accent text-black font-bold rounded-xl px-6 py-3 text-sm self-start md:self-auto'>Залишити запит</button>
				</div>

				{notice && <div className='mb-6 text-sm text-yellow-500'>{notice}</div>}
				{showForm && (
					<div className='max-w-xl mb-10'>
						<WantedForm onCancel={() => setShowForm(false)}
							onDone={() => { setShowForm(false); setNotice('Запит надіслано на модерацію'); loadMine(); }} />
					</div>
				)}

				{mine?.items?.length > 0 && (
					<div className='mb-10'>
						<h2 className='text-lg font-bold text-gray-900 dark:text-white mb-3'>Мої запити ({mine.active}/{mine.max} активних)</h2>
						<div className='space-y-2'>
							{mine.items.map((r) => (
								<div key={r.id} className='flex flex-wrap items-center gap-3 bg-white dark:bg-card border border-gray-100 dark:border-card-border rounded-xl px-4 py-3 text-sm'>
									<b className='text-gray-900 dark:text-white'>{r.category}</b>
									<span className='text-gray-500'>{fmtRange(r.subs_min, r.subs_max, 'підп.')} · {fmtRange(r.budget_min, r.budget_max, 'USDT')}</span>
									<span className='text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-white/10 text-gray-600 dark:text-gray-300'>{STATUS_UA[r.status] || r.status}</span>
									{r.status === 'rejected' && r.rejection_reason && <span className='text-xs text-red-500'>{r.rejection_reason}</span>}
									{['pending', 'approved'].includes(r.status) && (
										<button onClick={() => closeReq(r.id)} className='ml-auto text-xs text-gray-400 hover:text-red-500'>Закрити</button>
									)}
								</div>
							))}
						</div>
					</div>
				)}

				{loading ? (
					<div className='grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6'>
						{[1, 2, 3].map((i) => <div key={i} className='h-48 rounded-2xl bg-white dark:bg-card animate-pulse' />)}
					</div>
				) : items.length === 0 ? (
					<div className='text-center py-16 text-gray-500 dark:text-gray-400'>Поки що немає активних запитів. Будьте першим!</div>
				) : (
					<div className='grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6'>
						{items.map((r) => <WantedCard key={r.id} r={r} />)}
					</div>
				)}
			</div>
		</section>
	);
};

export default WantedPage;
