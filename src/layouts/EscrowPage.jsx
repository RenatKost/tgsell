import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { escrowAPI } from '../services/api';
import { useAuth } from '../context/AppContext';
import { ShieldCheck, Link2, AtSign, Coins, Lock, Percent, Scale, UserCheck, Wallet, KeyRound, BadgeCheck, ChevronDown, Sparkles } from 'lucide-react';
import './escrow.css';

const inputCls = 'esc-input w-full bg-white dark:bg-slate-900/70 border border-gray-200 dark:border-card-border rounded-xl px-3 py-2.5 text-sm text-gray-800 dark:text-gray-100 focus:outline-none focus:border-accent';
const card = 'bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-5';
const btn = 'esc-btn bg-accent hover:opacity-90 text-black font-bold rounded-xl px-5 py-3 text-sm min-h-[44px] disabled:opacity-50';
const fmt = (n) => Number(n || 0).toFixed(2).replace(/\.00$/, '');
const errText = (ex, fb) => { const d = ex?.response?.data?.detail; return typeof d === 'string' ? d : fb; };

const STATUS = { open: 'Очікує покупця', accepted: 'Угоду розпочато', cancelled: 'Скасовано' };

// Поява при скролі. `is-visible` ставиться напряму в DOM, тому елемент з .esc-reveal
// не повинен мати className, що змінюється при ре-рендері (React перезапише клас і сховає його).
// Fallback: елементи, що вже у viewport або вище нього (стрибок скролом), показуються одразу,
// а через REVEAL_FALLBACK_MS показуються всі — контент ніколи не лишається невидимим.
const REVEAL_FALLBACK_MS = 1500;
const useReveal = () => {
	useEffect(() => {
		const els = [...document.querySelectorAll('.esc-reveal:not(.is-visible)')];
		const show = (el) => el.classList.add('is-visible');
		if (!els.length) return undefined;
		if (!('IntersectionObserver' in window)) { els.forEach(show); return undefined; }
		const io = new IntersectionObserver((entries) => entries.forEach((en) => {
			if (en.isIntersecting || en.boundingClientRect.top < 0) { show(en.target); io.unobserve(en.target); }
		}), { threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
		els.forEach((el) => io.observe(el));
		const t = setTimeout(() => { els.forEach(show); io.disconnect(); }, REVEAL_FALLBACK_MS);
		return () => { clearTimeout(t); io.disconnect(); };
	});
};

const Hero = ({ fee }) => (
	<header className='esc-hero relative text-center pt-4 pb-2'>
		<div className='esc-shield mx-auto mb-6' aria-hidden='true'>
			<span className='esc-shield-ring' />
			<ShieldCheck className='relative w-10 h-10 sm:w-12 sm:h-12 text-accent' strokeWidth={1.75} />
		</div>
		<p className='inline-flex items-center gap-1.5 text-[11px] sm:text-xs uppercase tracking-[0.18em] text-accent/90 font-semibold mb-3'><Sparkles className='w-3.5 h-3.5' aria-hidden='true' />Гарант TgSell</p>
		<h1 className='esc-title text-[2rem] leading-[1.1] sm:text-5xl lg:text-6xl font-extrabold tracking-tight'>Гарант для зовнішніх угод</h1>
		<p className='mt-4 max-w-xl mx-auto text-[15px] sm:text-lg text-gray-600 dark:text-gray-400'>Домовились про продаж каналу поза каталогом? Проведіть угоду через гарант TgSell — безпечно для обох сторін.</p>
		<ul className='mt-6 flex flex-wrap justify-center gap-2 sm:gap-3'>
			<li className='esc-badge'><Lock className='w-4 h-4 text-accent' aria-hidden='true' />Кошти в ескроу</li>
			<li className='esc-badge'><Percent className='w-4 h-4 text-accent' aria-hidden='true' />Комісія {fee}%</li>
			<li className='esc-badge'><Scale className='w-4 h-4 text-accent' aria-hidden='true' />Спори розглядає гарант</li>
		</ul>
	</header>
);

const STEPS = [
	{ icon: Link2, title: 'Продавець створює угоду', text: 'Вказує посилання на канал, ціну та @username покупця й отримує секретне посилання.' },
	{ icon: UserCheck, title: 'Покупець підтверджує', text: 'Відкриває посилання, увійшовши в Telegram-акаунт із цим @username, і підтверджує угоду.' },
	{ icon: Wallet, title: 'Оплата в ескроу', text: 'Покупець оплачує USDT (TRC-20) на окрему депозитну адресу угоди — кошти чекають у гаранта.' },
	{ icon: KeyRound, title: 'Передача каналу', text: 'Продавець передає права на канал за чек-листом, покупець підтверджує отримання.' },
];

const HowItWorks = ({ fee, min }) => {
	const steps = [...STEPS, { icon: BadgeCheck, title: 'Виплата продавцю', text: `Після цього продавець отримує виплату за вирахуванням комісії ${fee}%.` }];
	return (
		<section className='space-y-6' aria-labelledby='esc-how'>
			<div className='text-center esc-reveal'>
				<h2 id='esc-how' className='text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white'>Як це працює</h2>
				<p className='mt-2 text-sm text-gray-500 dark:text-gray-400'>П’ять кроків від домовленості до виплати</p>
			</div>
			<ol className='esc-timeline relative grid gap-4 lg:grid-cols-5 lg:gap-4'>
				<span className='esc-line' aria-hidden='true' />
				{steps.map((st, i) => {
					const Icon = st.icon;
					return (
						<li key={st.title} className='esc-step esc-reveal relative' style={{ '--d': `${i * 90}ms` }}>
							<div className='esc-step-node'>
								<Icon className='w-5 h-5 text-accent' aria-hidden='true' />
								<span className='esc-step-num'>{i + 1}</span>
							</div>
							<div className='esc-step-card'>
								<h3 className='font-semibold text-gray-900 dark:text-white text-[15px]'>{st.title}</h3>
								<p className='mt-1.5 text-sm text-gray-600 dark:text-gray-400 leading-relaxed'>{st.text}</p>
							</div>
						</li>
					);
				})}
			</ol>
			<p className='esc-reveal text-center text-xs text-gray-400'>Угода приватна: її не видно в каталозі, пошуку й на публічних сторінках. Мінімальна сума — {min} USDT. Комісію сплачує продавець.</p>
		</section>
	);
};

const FAQ = ({ fee, min }) => {
	const items = [
		{ q: 'Де зберігаються кошти під час угоди?', a: 'Покупець оплачує USDT (TRC-20) на окрему депозитну адресу саме цієї угоди. Кошти залишаються у гаранта, доки покупець не підтвердить отримання каналу або доки гарант не ухвалить рішення у спорі.' },
		{ q: 'Хто сплачує комісію і скільки?', a: `Комісію ${fee}% сплачує продавець — вона утримується з суми угоди під час виплати. Покупець платить рівно ту ціну, про яку ви домовились. Мінімальна сума угоди — ${min} USDT.` },
		{ q: 'Чи перевіряє сервіс передачу каналу автоматично?', a: 'Ні. Для зовнішніх угод автоматичної перевірки передачі прав немає. Продавець передає канал за чек-листом, а покупець сам перевіряє, що отримав права власника, і лише тоді підтверджує отримання. Не підтверджуйте, доки не переконаєтесь.' },
		{ q: 'Що робити, якщо щось пішло не так?', a: 'Відкрийте спір на сторінці угоди. Його розглядає гарант: вивчає листування й надані сторонами докази та ухвалює рішення про виплату продавцю або повернення коштів покупцю.' },
		{ q: 'Хто може відкрити посилання на угоду?', a: 'Лише покупець, чий @username вказав продавець, — після входу через Telegram з цього акаунта. Угода приватна й не з’являється в каталозі чи пошуку.' },
	];
	const [open, setOpen] = useState(0);
	return (
		<section className='space-y-5' aria-labelledby='esc-faq'>
			<h2 id='esc-faq' className='esc-reveal text-center text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white'>Питання та відповіді</h2>
			<div className='space-y-3'>
				{items.map((it, i) => {
					const isOpen = open === i;
					return (
						<div key={it.q} className='esc-reveal' style={{ '--d': `${i * 60}ms` }}>
						<div className={`esc-faq ${isOpen ? 'is-open' : ''}`}>
							<button type='button' className='w-full flex items-center justify-between gap-3 text-left px-4 sm:px-5 py-4 min-h-[56px]' aria-expanded={isOpen} aria-controls={`esc-faq-${i}`} onClick={() => setOpen(isOpen ? -1 : i)}>
								<span className='font-semibold text-[15px] text-gray-900 dark:text-white'>{it.q}</span>
								<ChevronDown className='esc-faq-chev w-5 h-5 shrink-0 text-accent' aria-hidden='true' />
							</button>
							<div id={`esc-faq-${i}`} className='esc-faq-body' role='region'>
								<div className='overflow-hidden'><p className='px-4 sm:px-5 pb-4 text-sm leading-relaxed text-gray-600 dark:text-gray-400'>{it.a}</p></div>
							</div>
						</div>
						</div>
					);
				})}
			</div>
		</section>
	);
};

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
		<div className='esc-glass-wrap'>
		<form onSubmit={submit} className='esc-glass space-y-4 p-5 sm:p-7'>
			<div className='flex items-center gap-3'>
				<span className='esc-form-icon'><ShieldCheck className='w-5 h-5 text-accent' aria-hidden='true' /></span>
				<div>
					<h2 className='text-lg sm:text-xl font-bold text-gray-900 dark:text-white'>Створити угоду</h2>
					<p className='text-xs text-gray-500 dark:text-gray-400'>Покупець отримає приватне посилання</p>
				</div>
			</div>
			<div><label htmlFor='esc-link' className='block text-xs text-gray-400 mb-1'>Посилання на канал</label>
				<div className='esc-field'><Link2 className='esc-field-icon' aria-hidden='true' />
				<input id='esc-link' className={inputCls} placeholder='https://t.me/назва_каналу' value={v.channel_link} onChange={set('channel_link')} required /></div></div>
			<div className='grid grid-cols-1 sm:grid-cols-2 gap-3'>
				<div><label htmlFor='esc-price' className='block text-xs text-gray-400 mb-1'>Ціна, USDT</label>
					<div className='esc-field'><Coins className='esc-field-icon' aria-hidden='true' />
					<input id='esc-price' type='number' min={meta.min_price_usdt} step='0.01' className={inputCls} value={v.price_usdt} onChange={set('price_usdt')} required /></div></div>
				<div><label htmlFor='esc-buyer' className='block text-xs text-gray-400 mb-1'>@username покупця</label>
					<div className='esc-field'><AtSign className='esc-field-icon' aria-hidden='true' />
					<input id='esc-buyer' className={inputCls} placeholder='@buyer' value={v.buyer_username} onChange={set('buyer_username')} required /></div></div>
			</div>
			<div className={`esc-calc ${price > 0 ? 'is-active' : ''}`} aria-live='polite'>
				<div className='flex items-baseline justify-between gap-3'>
					<span className='text-sm text-gray-500 dark:text-gray-400 whitespace-nowrap'>Продавець отримає</span>
					<b className='text-lg sm:text-xl text-gray-900 dark:text-white tabular-nums whitespace-nowrap'>{fmt(price - fee)} <span className='text-accent text-sm'>USDT</span></b>
				</div>
				<div className='mt-1 flex items-baseline justify-between gap-3 text-xs text-gray-500 dark:text-gray-400'>
					<span>Комісія {meta.fee_percent}%</span>
					<span className='tabular-nums'>{fmt(fee)} USDT</span>
				</div>
			</div>
			{err && <p className='text-sm text-red-500'>{err}</p>}
			<button className={`${btn} w-full`} disabled={busy}><span className='relative z-[1]'>{busy ? 'Створюємо…' : 'Отримати посилання для покупця'}</span></button>
		</form>
		</div>
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
	useReveal();
	return (
		<main className='esc-page relative min-h-screen overflow-x-clip'>
			<div className='esc-bg' aria-hidden='true'><span className='esc-grid' /><span className='esc-blob esc-blob-1' /><span className='esc-blob esc-blob-2' /><span className='esc-blob esc-blob-3' /></div>
			<div className='relative max-w-3xl mx-auto px-4 pt-24 md:pt-32 pb-20 space-y-10 sm:space-y-14'>
			<Hero fee={meta.fee_percent} />
			<div className='space-y-6'>
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
			</div>
			</div>
			<div className='relative max-w-6xl mx-auto px-4 pb-10'><HowItWorks fee={meta.fee_percent} min={meta.min_price_usdt} /></div>
			<div className='relative max-w-3xl mx-auto px-4 pb-24'><FAQ fee={meta.fee_percent} min={meta.min_price_usdt} /></div>
		</main>
	);
};

export default EscrowPage;
