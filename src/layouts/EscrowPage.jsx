import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { escrowAPI } from '../services/api';
import { useAuth } from '../context/AppContext';

const inputCls = 'w-full bg-white dark:bg-slate-900 border border-gray-200 dark:border-card-border rounded-xl px-3 py-2.5 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:border-accent';
const card = 'bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-5';
const btn = 'bg-accent hover:opacity-90 text-black font-bold rounded-xl px-5 py-3 text-sm min-h-[44px] disabled:opacity-50';
const fmt = (n) => Number(n || 0).toFixed(2).replace(/\.00$/, '');
const errText = (ex, fb) => { const d = ex?.response?.data?.detail; return typeof d === 'string' ? d : fb; };

const STATUS = { open: 'Очікує покупця', accepted: 'Угоду розпочато', cancelled: 'Скасовано' };

const HowItWorks = ({ fee, min }) => (
	<section className={card}>
		<h2 className='text-lg font-bold text-gray-900 dark:text-white mb-3'>Як це працює</h2>
		<ol className='space-y-2 text-sm text-gray-600 dark:text-gray-300 list-decimal pl-5'>
			<li>Продавець вказує посилання на канал, ціну та @username покупця й отримує секретне посилання.</li>
			<li>Покупець відкриває посилання, увійшовши в Telegram-акаунт із цим @username, і підтверджує угоду.</li>
			<li>Покупець оплачує USDT (TRC-20) на окрему депозитну адресу угоди — кошти чекають у гаранта.</li>
			<li>Продавець передає права на канал за чек-листом, покупець підтверджує отримання.</li>
			<li>Після цього продавець отримує виплату за вирахуванням комісії {fee}%.</li>
		</ol>
		<p className='mt-3 text-xs text-gray-400'>Угода приватна: її не видно в каталозі, пошуку й на публічних сторінках. Мінімальна сума — {min} USDT. Комісію сплачує продавець.</p>
	</section>
);

const SellerForm = ({ meta, onCreated }) => {
	const [v, setV] = useState({ channel_link: '', price_usdt: '', buyer_username: '' });
	const [err, setErr] = useState('');
	const [busy, setBusy] = useState(false);
	const set = (k) => (e) => setV({ ...v, [k]: e.target.value });
	const price = Number(v.price_usdt) || 0;
	const fee = Math.round(price * meta.fee_percent) / 100;
	const submit = async (e) => {
		e.preventDefault();
		if (price < meta.min_price_usdt) { setErr(`Мінімальна ціна — ${meta.min_price_usdt} USDT`); return; }
		setBusy(true); setErr('');
		try {
			const r = await escrowAPI.create({ ...v, price_usdt: price });
			setV({ channel_link: '', price_usdt: '', buyer_username: '' });
			onCreated(r.data);
		} catch (ex) { setErr(errText(ex, 'Перевірте поля форми')); } finally { setBusy(false); }
	};
	return (
		<form onSubmit={submit} className={`${card} space-y-4`}>
			<h2 className='text-lg font-bold text-gray-900 dark:text-white'>Створити угоду</h2>
			<div><label className='block text-xs text-gray-400 mb-1'>Посилання на канал</label>
				<input className={inputCls} placeholder='https://t.me/назва_каналу' value={v.channel_link} onChange={set('channel_link')} required /></div>
			<div className='grid grid-cols-1 sm:grid-cols-2 gap-3'>
				<div><label className='block text-xs text-gray-400 mb-1'>Ціна, USDT</label>
					<input type='number' min={meta.min_price_usdt} step='0.01' className={inputCls} value={v.price_usdt} onChange={set('price_usdt')} required /></div>
				<div><label className='block text-xs text-gray-400 mb-1'>@username покупця</label>
					<input className={inputCls} placeholder='@buyer' value={v.buyer_username} onChange={set('buyer_username')} required /></div>
			</div>
			{price > 0 && <p className='text-sm text-gray-500 dark:text-gray-400'>Комісія {meta.fee_percent}%: {fmt(fee)} USDT · Ви отримаєте: <b className='text-gray-900 dark:text-white'>{fmt(price - fee)} USDT</b></p>}
			{err && <p className='text-sm text-red-500'>{err}</p>}
			<button className={btn} disabled={busy}>{busy ? 'Створюємо…' : 'Отримати посилання для покупця'}</button>
		</form>
	);
};

const OfferRow = ({ o, onCancel }) => {
	const [copied, setCopied] = useState(false);
	const copy = async () => { try { await navigator.clipboard.writeText(o.buyer_url); setCopied(true); } catch { /* ignore */ } };
	return (
		<div className={`${card} space-y-2`}>
			<div className='flex flex-wrap items-center justify-between gap-2'>
				<a href={o.channel_link} target='_blank' rel='noreferrer' className='font-semibold text-gray-900 dark:text-white break-all'>{o.channel_link}</a>
				<span className='text-xs px-2 py-1 rounded-lg bg-gray-100 dark:bg-white/5 text-gray-600 dark:text-gray-300'>{STATUS[o.status] || o.status}</span>
			</div>
			<p className='text-sm text-gray-500 dark:text-gray-400'>{fmt(o.price_usdt)} USDT · покупець @{o.buyer_username} · ви отримаєте {fmt(o.seller_receives)} USDT</p>
			{o.status === 'open' && (
				<div className='flex flex-col sm:flex-row gap-2'>
					<input readOnly value={o.buyer_url} className={`${inputCls} text-xs`} onFocus={(e) => e.target.select()} />
					<button type='button' onClick={copy} className='border border-accent/50 text-accent rounded-xl px-4 min-h-[44px] text-sm font-semibold whitespace-nowrap'>{copied ? 'Скопійовано' : 'Копіювати'}</button>
					<button type='button' onClick={() => onCancel(o.id)} className='text-sm text-red-500 px-3 min-h-[44px]'>Скасувати</button>
				</div>
			)}
			{o.deal_id && <Link to={`/deal/${o.deal_id}`} className='text-sm text-accent font-semibold'>Перейти до угоди →</Link>}
			{o.status === 'open' && <p className='text-xs text-gray-400'>Надішліть посилання лише покупцю. Відкрити його зможе тільки @{o.buyer_username}.</p>}
		</div>
	);
};

const BuyerInvite = ({ token }) => {
	const { isAuthenticated, loading } = useAuth();
	const navigate = useNavigate();
	const [offer, setOffer] = useState(null);
	const [err, setErr] = useState('');
	const [busy, setBusy] = useState(false);
	useEffect(() => {
		if (!isAuthenticated) return;
		escrowAPI.invite(token).then((r) => setOffer(r.data)).catch((ex) => setErr(errText(ex, 'Угоду не знайдено')));
	}, [token, isAuthenticated]);
	const accept = async () => {
		setBusy(true); setErr('');
		try { const r = await escrowAPI.accept(token); navigate(`/deal/${r.data.deal_id}`); }
		catch (ex) { setErr(errText(ex, 'Не вдалося розпочати угоду')); } finally { setBusy(false); }
	};
	if (loading) return null;
	if (!isAuthenticated) return <div className={card}><p className='text-gray-700 dark:text-gray-200'>Увійдіть через Telegram (кнопка «Увійти» вгорі), використовуючи акаунт, для якого створено угоду.</p></div>;
	if (err && !offer) return <div className={card}><p className='text-red-500'>{err}</p></div>;
	if (!offer) return <div className={card}><p className='text-gray-400'>Завантаження…</p></div>;
	return (
		<div className={`${card} space-y-3`}>
			<h2 className='text-lg font-bold text-gray-900 dark:text-white'>Запрошення до угоди</h2>
			<p className='text-sm text-gray-600 dark:text-gray-300'>Продавець: <b>{offer.seller_name || '—'}</b></p>
			<p className='text-sm text-gray-600 dark:text-gray-300 break-all'>Канал: <a className='text-accent' href={offer.channel_link} target='_blank' rel='noreferrer'>{offer.channel_link}</a></p>
			<p className='text-2xl font-bold text-gray-900 dark:text-white'>{fmt(offer.price_usdt)} USDT</p>
			<p className='text-xs text-gray-400'>Оплата USDT (TRC-20) на депозитну адресу угоди. Комісію сервісу сплачує продавець.</p>
			{err && <p className='text-sm text-red-500'>{err}</p>}
			{offer.status === 'open' && <button className={btn} onClick={accept} disabled={busy}>{busy ? 'Створюємо…' : 'Розпочати угоду'}</button>}
			{offer.status === 'accepted' && offer.deal_id && <Link className={btn + ' inline-block'} to={`/deal/${offer.deal_id}`}>Перейти до угоди</Link>}
			{offer.status === 'cancelled' && <p className='text-sm text-red-500'>Продавець скасував цю угоду.</p>}
		</div>
	);
};

const EscrowPage = () => {
	const { token } = useParams();
	const { isAuthenticated, user } = useAuth();
	const [meta, setMeta] = useState({ fee_percent: 3, min_price_usdt: 5 });
	const [offers, setOffers] = useState([]);
	useEffect(() => {
		document.title = 'Гарант для угод з Telegram-каналами — TgSell';
		escrowAPI.meta().then((r) => setMeta(r.data)).catch(() => {});
	}, []);
	const load = () => { if (isAuthenticated && !token) escrowAPI.mine().then((r) => setOffers(r.data)).catch(() => {}); };
	useEffect(load, [isAuthenticated, token]); // eslint-disable-line react-hooks/exhaustive-deps
	const cancel = async (id) => { try { await escrowAPI.cancel(id); load(); } catch { /* ignore */ } };
	const canSell = isAuthenticated && user?.telegram_id;
	return (
		<main className='min-h-screen max-w-3xl mx-auto px-4 pt-24 md:pt-28 pb-16 space-y-6'>
			<header>
				<h1 className='text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white'>Гарант для зовнішніх угод</h1>
				<p className='mt-2 text-gray-600 dark:text-gray-400'>Домовились про продаж каналу поза каталогом? Проведіть угоду через гарант TgSell — безпечно для обох сторін.</p>
			</header>
			{token ? <BuyerInvite token={token} /> : (
				<>
					{canSell ? <SellerForm meta={meta} onCreated={(o) => setOffers([o, ...offers])} /> : (
						<div className={card}><p className='text-gray-700 dark:text-gray-200'>Щоб створити угоду, увійдіть через Telegram (@tgsell_auth_bot) — кнопка «Увійти» вгорі.</p></div>
					)}
					{offers.length > 0 && (
						<section className='space-y-3'>
							<h2 className='text-lg font-bold text-gray-900 dark:text-white'>Мої угоди через гарант</h2>
							{offers.map((o) => <OfferRow key={o.id} o={o} onCancel={cancel} />)}
						</section>
					)}
				</>
			)}
			<HowItWorks fee={meta.fee_percent} min={meta.min_price_usdt} />
		</main>
	);
};

export default EscrowPage;
