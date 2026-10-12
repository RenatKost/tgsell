import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { dealsAPI } from '../../services/api';
import useDealChat from './useDealChat';

const STATUS_LABELS = {
	created: 'Очікує підтвердження', payment_pending: 'Очікує оплати', paid: 'Оплачено',
	channel_transferring: 'Передача каналу', awaiting_payout: 'Очікує виплати', payout_in_progress: 'Виплата в процесі',
	completed: 'Завершено', cancelled: 'Скасовано', disputed: 'Спір',
};
const STATUS_CLS = {
	completed: 'bg-green-100 text-green-700', cancelled: 'bg-gray-200 text-gray-600', disputed: 'bg-red-100 text-red-700',
	payout_in_progress: 'bg-cyan-100 text-cyan-700', awaiting_payout: 'bg-cyan-100 text-cyan-700',
};
const EVENT_ICON = {
	payment_received: '💰', payment_requested: '💳', deal_created: '🤝', ready_confirmed: '✅', transfer_confirmed: '📦',
	checklist_item: '☑️', checklist_side_done: '✅', awaiting_payout: '⏳', payout_queued: '⏳', payout_done: '💸',
	refund_done: '↩️', payout_failed: '⚠️', dispute_opened: '⚖️', cancelled: '✖️', admin_called: '🛟',
};
const ROLE_LABEL = { buyer: 'Покупець', seller: 'Продавець', guarantor: 'Гарант' };
const ALLOWED = '.jpg,.jpeg,.png,.webp,.gif,.pdf,.txt,.csv,.zip';
const MAX_MB = 10;

const fmtTime = (iso) => new Date(iso).toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' });
const fmtDay = (iso) => new Date(iso).toLocaleDateString('uk-UA', { day: 'numeric', month: 'long', year: 'numeric' });
const fmtSize = (b) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} МБ` : `${Math.max(1, Math.round(b / 1024))} КБ`);
const ago = (iso) => {
	if (!iso) return '';
	const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
	if (s < 60) return 'щойно';
	if (s < 3600) return `${Math.floor(s / 60)} хв тому`;
	if (s < 86400) return `${Math.floor(s / 3600)} год тому`;
	return new Date(iso).toLocaleDateString('uk-UA');
};

// Plain text with clickable http(s) links — never HTML.
const Linkified = ({ text }) => {
	const parts = String(text || '').split(/(https?:\/\/[^\s<>"]+)/g);
	return parts.map((p, i) => (/^https?:\/\//.test(p)
		? <a key={i} href={p} target='_blank' rel='noopener noreferrer nofollow' className='underline break-all'>{p}</a>
		: <span key={i}>{p}</span>));
};

const blobCache = new Map();
const useBlobUrl = (dealId, att, thumb) => {
	const key = att ? `${dealId}:${att.id}:${thumb ? 't' : 'f'}` : null;
	const [url, setUrl] = useState(key ? blobCache.get(key) : null);
	useEffect(() => {
		if (!key || blobCache.has(key)) { if (key) setUrl(blobCache.get(key)); return; }
		let alive = true;
		dealsAPI.chatAttachment(dealId, att.id, thumb).then(({ data }) => {
			const u = URL.createObjectURL(data);
			blobCache.set(key, u);
			if (alive) setUrl(u);
		}).catch(() => {});
		return () => { alive = false; };
	}, [key]); // eslint-disable-line react-hooks/exhaustive-deps
	return url;
};

const Attachment = ({ dealId, att, own }) => {
	const thumb = useBlobUrl(dealId, att.is_image && att.has_thumb ? att : null, true);
	const download = async () => {
		const { data } = await dealsAPI.chatAttachment(dealId, att.id, false);
		const u = URL.createObjectURL(data);
		if (att.is_image) window.open(u, '_blank', 'noopener');
		else { const a = document.createElement('a'); a.href = u; a.download = att.filename; a.click(); }
		setTimeout(() => URL.revokeObjectURL(u), 60000);
	};
	if (att.is_image) {
		return (
			<button onClick={download} className='block mb-1 rounded-xl overflow-hidden bg-black/5' title={att.filename}>
				{thumb ? <img src={thumb} alt={att.filename} className='max-h-60 max-w-full object-cover' /> : <div className='w-48 h-32 animate-pulse' />}
			</button>
		);
	}
	return (
		<button onClick={download} className={`flex items-center gap-2 mb-1 px-3 py-2 rounded-xl text-left ${own ? 'bg-white/15' : 'bg-gray-50 dark:bg-slate-700'}`}>
			<span className='text-xl'>📄</span>
			<span className='min-w-0'><span className='block text-sm font-medium truncate max-w-[200px]'>{att.filename}</span>
				<span className='block text-[11px] opacity-70'>{fmtSize(att.size)} · завантажити</span></span>
		</button>
	);
};

const Ticks = ({ id, peerRead, peerDelivered }) => {
	// Inline SVG: Montserrat has no ✓ glyph and the fallback glyph + sky-300 on blue-500
	// was practically invisible on iPhone. Read = bright, bold; sent/delivered = dimmer.
	const Tick = ({ double, read }) => (
		<svg viewBox={double ? '0 0 22 12' : '0 0 14 12'} className={`inline-block h-3 ${double ? 'w-[18px]' : 'w-3'} ${read ? 'text-white' : 'text-white/60'}`} aria-hidden='true'>
			<path d='M1 6.5l3.5 3.5L12 2' fill='none' stroke='currentColor' strokeWidth={read ? 2.2 : 1.8} strokeLinecap='round' strokeLinejoin='round' />
			{double && <path d='M8 9.5l0.5 0.5L19 2' fill='none' stroke='currentColor' strokeWidth={read ? 2.2 : 1.8} strokeLinecap='round' strokeLinejoin='round' />}
		</svg>
	);
	if (id <= peerRead) return <span className='inline-flex items-center' title='Прочитано' aria-label='Прочитано'><Tick double read /></span>;
	if (id <= peerDelivered) return <span className='inline-flex items-center' title='Доставлено' aria-label='Доставлено'><Tick double /></span>;
	return <span className='inline-flex items-center' title='Надіслано' aria-label='Надіслано'><Tick /></span>;
};

const SystemCard = ({ m }) => (
	<div className='flex justify-center my-2'>
		<div className='max-w-[90%] bg-blue-50/80 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-900/40 text-gray-700 dark:text-gray-200 rounded-xl px-3 py-2 text-xs sm:text-[13px] whitespace-pre-wrap break-words'>
			<span className='mr-1'>{EVENT_ICON[m.event] || 'ℹ️'}</span><Linkified text={m.text} />
			<span className='ml-2 text-[10px] text-gray-400'>{fmtTime(m.created_at)}</span>
		</div>
	</div>
);

const Header = ({ deal, presence, onCallAdmin, compact }) => {
	const [open, setOpen] = useState(false);
	const typing = presence.filter(p => p.typing);
	const parties = presence.filter(p => p.role === 'buyer' || p.role === 'seller');
	const status = deal?.status;
	return (
		<div className='sticky top-0 z-10 bg-white/95 dark:bg-slate-800/95 backdrop-blur border-b border-gray-100 dark:border-slate-700 px-4 py-3'>
			<div className='flex items-center gap-2 flex-wrap'>
				<h3 className='font-bold text-gray-900 dark:text-white mr-1'>Чат угоди{deal ? ` #${deal.id}` : ''}</h3>
				{status && <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${STATUS_CLS[status] || 'bg-blue-100 text-blue-700'}`}>{STATUS_LABELS[status] || status}</span>}
				{deal?.checklist && (deal.checklist.seller.total + deal.checklist.buyer.total) > 0 && (
					<button onClick={() => setOpen(o => !o)} className='text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1'>
						☑️ {deal.checklist.seller.done + deal.checklist.buyer.done}/{deal.checklist.seller.total + deal.checklist.buyer.total}
						<span>{open ? '▲' : '▼'}</span>
					</button>
				)}
				{onCallAdmin && !compact && status && !['completed', 'cancelled'].includes(status) && (
					<button onClick={onCallAdmin} className='ml-auto text-xs sm:text-sm bg-gray-50 dark:bg-slate-700/60 border border-gray-200 dark:border-slate-600 text-gray-600 dark:text-gray-300 px-3 py-1.5 rounded-xl hover:bg-gray-100'>🛟 Підтримка</button>
				)}
			</div>
			{open && deal?.checklist && (
				<div className='mt-2 grid grid-cols-2 gap-2 text-xs'>
					{['seller', 'buyer'].map(side => {
						const c = deal.checklist[side];
						const pct = c.total ? Math.round((c.done / c.total) * 100) : 0;
						return (
							<div key={side}>
								<div className='flex justify-between text-gray-500'><span>{ROLE_LABEL[side]}</span><span>{c.done}/{c.total}</span></div>
								<div className='h-1.5 bg-gray-100 dark:bg-slate-700 rounded-full overflow-hidden'><div className='h-full bg-green-500' style={{ width: `${pct}%` }} /></div>
							</div>
						);
					})}
				</div>
			)}
			<div className='text-xs leading-snug text-gray-500 dark:text-gray-400 mt-1 min-h-[16px] flex flex-wrap gap-x-3'>
				{typing.length
					? <span className='text-blue-500'>{typing.map(p => ROLE_LABEL[p.role] || p.name).join(', ')} друкує…</span>
					: parties.map(p => <span key={p.user_id} className='whitespace-nowrap'>{ROLE_LABEL[p.role]}: {p.online ? <span className='text-green-600 font-semibold'>● онлайн</span> : `був(ла) ${ago(p.last_seen_at)}`}</span>)}
			</div>
		</div>
	);
};

const Composer = ({ disabled, onSend, onUpload, onTyping }) => {
	const [text, setText] = useState('');
	const [file, setFile] = useState(null);
	const [err, setErr] = useState('');
	const fileRef = useRef(null);
	const taRef = useRef(null);
	const pick = (f) => {
		if (!f) return;
		const ext = '.' + (f.name.split('.').pop() || '').toLowerCase();
		if (!ALLOWED.split(',').includes(ext)) { setErr('Дозволено: JPG, PNG, WEBP, GIF, PDF, TXT, CSV, ZIP'); return; }
		if (f.size > MAX_MB * 1048576) { setErr(`Файл завеликий (макс. ${MAX_MB} МБ)`); return; }
		setErr(''); setFile(f);
	};
	const submit = (e) => {
		e?.preventDefault();
		const t = text.trim();
		if (disabled) return;
		if (file) { onUpload(file, t); setFile(null); setText(''); return; }
		if (!t) return;
		onSend(t); setText('');
		if (taRef.current) taRef.current.style.height = '';
	};
	return (
		<form onSubmit={submit}
			onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); pick(e.dataTransfer.files?.[0]); }}
			className='border-t border-gray-100 dark:border-slate-700 bg-white dark:bg-slate-800 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]'>
			{file && (
				<div className='flex items-center gap-2 mb-2 text-xs bg-gray-50 dark:bg-slate-700 rounded-lg px-3 py-2'>
					<span>📎 {file.name} · {fmtSize(file.size)}</span>
					<button type='button' onClick={() => setFile(null)} className='ml-auto text-gray-400'>✕</button>
				</div>
			)}
			{err && <div className='text-xs text-red-600 mb-1'>{err}</div>}
			<div className='flex items-end gap-2'>
				<button type='button' disabled={disabled} onClick={() => fileRef.current?.click()} className='w-10 h-10 rounded-xl text-gray-500 hover:bg-gray-100 dark:hover:bg-slate-700 shrink-0 disabled:opacity-40' title='Додати файл'>📎</button>
				<input ref={fileRef} type='file' accept={ALLOWED} className='hidden' onChange={e => { pick(e.target.files?.[0]); e.target.value = ''; }} />
				<textarea ref={taRef} rows={1} value={text} disabled={disabled} maxLength={2000}
					onChange={e => { setText(e.target.value); onTyping(); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 140) + 'px'; }}
					onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } }}
					onPaste={e => { const f = [...(e.clipboardData?.files || [])][0]; if (f) { e.preventDefault(); pick(f); } }}
					placeholder={disabled ? 'Надсилання недоступне' : (file ? 'Підпис…' : 'Написати…')}
					className='flex-1 min-w-0 resize-none border border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/60 dark:text-gray-100 rounded-xl px-3 sm:px-4 py-2.5 text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-400' />
				<button type='submit' disabled={disabled || (!text.trim() && !file)} className='w-10 h-10 rounded-xl bg-blue-500 hover:bg-blue-600 text-white shrink-0 disabled:opacity-30'>➤</button>
			</div>
		</form>
	);
};

/**
 * Deal chat (website). Used on the deal page and in the moderator cabinet.
 * props: dealId, userId, onCallAdmin?, compact? (modal), height? (css class)
 */
const DealChat = ({ dealId, userId, onCallAdmin, compact = false, height = 'h-[60vh] sm:h-[28rem]', canPost = true }) => {
	const chat = useDealChat(dealId);
	const listRef = useRef(null);
	const nearBottomRef = useRef(true);
	const [newBelow, setNewBelow] = useState(0);
	const firstUnreadRef = useRef(null);
	const prevLastRef = useRef(0);
	const prevHeightRef = useRef(0);
	const me = chat.me?.id ?? userId;

	const items = useMemo(() => {
		const out = [];
		let day = '';
		chat.messages.forEach(m => {
			const d = m.created_at ? m.created_at.slice(0, 10) : '';
			if (d && d !== day) { day = d; out.push({ type: 'day', key: `d-${d}`, iso: m.created_at }); }
			out.push({ type: 'msg', key: m.id, m });
		});
		return out;
	}, [chat.messages]);

	if (firstUnreadRef.current === null && chat.loaded) {
		const f = chat.messages.find(m => m.id > chat.my_last_read_id && m.sender_id !== me);
		firstUnreadRef.current = f ? f.id : 0;
	}

	const onScroll = () => {
		const el = listRef.current;
		if (!el) return;
		nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
		if (nearBottomRef.current) setNewBelow(0);
		if (el.scrollTop < 40 && chat.hasOlder) {
			prevHeightRef.current = el.scrollHeight;
			chat.loadOlder();
		}
	};

	useLayoutEffect(() => {
		const el = listRef.current;
		if (!el) return;
		const last = chat.messages.length ? chat.messages[chat.messages.length - 1].id : 0;
		if (prevHeightRef.current && el.scrollHeight > prevHeightRef.current && last === prevLastRef.current) {
			el.scrollTop += el.scrollHeight - prevHeightRef.current; // keep position after loading older
			prevHeightRef.current = 0;
			return;
		}
		if (last > prevLastRef.current) {
			const mine = chat.messages[chat.messages.length - 1]?.sender_id === me;
			if (nearBottomRef.current || mine || !prevLastRef.current) el.scrollTop = el.scrollHeight;
			else setNewBelow(n => n + chat.messages.filter(m => m.id > prevLastRef.current && m.sender_id !== me).length);
		}
		prevLastRef.current = last;
	}, [chat.messages, me]);

	useEffect(() => {
		if (chat.pending.length && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
	}, [chat.pending.length]);

	// Read receipts: only while visible and scrolled to the bottom.
	useEffect(() => {
		const last = chat.messages.length ? chat.messages[chat.messages.length - 1].id : 0;
		if (last && nearBottomRef.current && document.visibilityState === 'visible') chat.markRead(last);
	}, [chat.messages, newBelow]); // eslint-disable-line react-hooks/exhaustive-deps

	useEffect(() => {
		const base = document.title.replace(/^\(\d+\)\s*/, '');
		document.title = chat.unread ? `(${chat.unread}) ${base}` : base;
		return () => { document.title = document.title.replace(/^\(\d+\)\s*/, ''); };
	}, [chat.unread]);

	const toBottom = () => { const el = listRef.current; if (el) el.scrollTop = el.scrollHeight; setNewBelow(0); };

	return (
		<div className={`relative bg-white dark:bg-slate-800 ${compact ? '' : 'rounded-2xl shadow-sm border border-gray-100 dark:border-slate-700 mb-6'} overflow-hidden flex flex-col`}>
			<Header deal={chat.deal} presence={chat.presence} onCallAdmin={onCallAdmin} compact={compact} />
			<div ref={listRef} onScroll={onScroll} className={`${height} overflow-y-auto overscroll-contain bg-[#f6f7fb] dark:bg-slate-900/40 px-3 sm:px-4 py-3`}>
				{chat.hasOlder && <div className='text-center text-xs text-gray-400 py-1'>Прокрутіть вгору, щоб завантажити старіші</div>}
				{!chat.loaded && <div className='text-center text-gray-400 text-sm mt-24'>Завантаження…</div>}
				{chat.loaded && !chat.messages.length && !chat.pending.length && <div className='text-center text-gray-400 text-sm mt-24'>Повідомлень ще немає</div>}
				{items.map(it => {
					if (it.type === 'day') return <div key={it.key} className='text-center my-3'><span className='text-[11px] bg-white dark:bg-slate-800 text-gray-500 px-3 py-1 rounded-full shadow-sm'>{fmtDay(it.iso)}</span></div>;
					const m = it.m;
					const divider = firstUnreadRef.current && m.id === firstUnreadRef.current
						? <div className='flex items-center gap-2 my-2 text-[11px] text-blue-500'><div className='flex-1 h-px bg-blue-200' />Нові повідомлення<div className='flex-1 h-px bg-blue-200' /></div> : null;
					if (m.is_system) return <div key={it.key}>{divider}<SystemCard m={m} /></div>;
					const own = m.sender_id === me;
					return (
						<div key={it.key}>
							{divider}
							<div className={`flex mb-2 ${own ? 'justify-end' : 'justify-start'}`}>
								<div className={`max-w-[85%] sm:max-w-[75%] rounded-2xl px-3 py-2 shadow-sm ${own ? 'bg-blue-500 text-white rounded-br-md' : 'bg-white dark:bg-slate-800 text-gray-800 dark:text-gray-100 rounded-bl-md'}`}>
									{!own && <div className={`text-[11px] font-semibold mb-0.5 ${m.sender_role === 'guarantor' ? 'text-purple-600' : 'text-blue-600'}`}>{m.sender_name || 'Користувач'}{m.sender_role ? ` · ${ROLE_LABEL[m.sender_role]}` : ''}</div>}
									{m.attachment && <Attachment dealId={dealId} att={m.attachment} own={own} />}
									{!(m.attachment && m.text === `📎 ${m.attachment.filename}`) && <div className='text-[15px] sm:text-sm whitespace-pre-wrap break-words'><Linkified text={m.text} /></div>}
									<div className={`text-[11px] leading-none mt-1 flex items-center justify-end gap-1 ${own ? 'text-blue-50' : 'text-gray-400'}`}>
										{fmtTime(m.created_at)}
										{own && <Ticks id={m.id} peerRead={chat.peer_read_id} peerDelivered={chat.peer_delivered_id} />}
									</div>
								</div>
							</div>
						</div>
					);
				})}
				{chat.pending.map(p => (
					<div key={p.client_id} className='flex justify-end mb-2'>
						<div className={`max-w-[85%] rounded-2xl px-3 py-2 ${p.status === 'failed' ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-blue-400 text-white'}`}>
							<div className='text-sm whitespace-pre-wrap break-words'>{p.file ? `📎 ${p.file.name}` : p.text}</div>
							<div className='text-[10px] mt-0.5 text-right'>
								{p.status === 'sending' ? (p.file ? `${p.progress || 0}%` : '🕓') : (
									<span>{p.error || 'Не надіслано'} · <button onClick={() => chat.retry(p)} className='underline'>повторити</button> · <button onClick={() => chat.discard(p.client_id)} className='underline'>видалити</button></span>
								)}
							</div>
						</div>
					</div>
				))}
			</div>
			{newBelow > 0 && (
				<button onClick={toBottom} className='absolute right-4 bottom-20 bg-blue-500 text-white text-xs px-3 py-1.5 rounded-full shadow-lg'>↓ {newBelow} нових</button>
			)}
			{chat.error && <div className='text-xs text-red-600 px-4 py-1 bg-red-50'>{chat.error}</div>}
			{chat.deal && !chat.deal.polling && <div className='text-[11px] text-gray-400 px-4 py-1'>Угоду закрито — чат показано як історію.</div>}
			<Composer disabled={!canPost} onSend={chat.send} onUpload={chat.upload} onTyping={chat.notifyTyping} />
		</div>
	);
};

export default DealChat;
