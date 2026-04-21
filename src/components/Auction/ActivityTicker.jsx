import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { activityAPI } from '../../services/api';

/* Custom inline SVG icons -- no emoji, no Cyrillic in attributes */
const IconDeal = () => (
<svg width='15' height='15' viewBox='0 0 16 16' fill='none' aria-hidden='true'>
<circle cx='8' cy='8' r='6.5' stroke='#00FF88' strokeWidth='1.4'/>
<path d='M5 8l2 2 4-4' stroke='#00FF88' strokeWidth='1.5' strokeLinecap='round' strokeLinejoin='round'/>
</svg>
);
const IconBid = () => (
<svg width='15' height='15' viewBox='0 0 16 16' fill='none' aria-hidden='true'>
<rect x='8.5' y='1.5' width='3.5' height='6.5' rx='0.8' transform='rotate(45 8.5 1.5)' fill='#fb923c' opacity='.85'/>
<path d='M2 14l4.5-4.5' stroke='#fb923c' strokeWidth='1.8' strokeLinecap='round'/>
<path d='M10 12.5h3.5' stroke='#fb923c' strokeWidth='1.4' strokeLinecap='round'/>
</svg>
);
const IconChannel = () => (
<svg width='15' height='15' viewBox='0 0 16 16' fill='none' aria-hidden='true'>
<circle cx='8' cy='9' r='2' fill='#22d3ee'/>
<path d='M5 6.5a4 4 0 016 0' stroke='#22d3ee' strokeWidth='1.3' strokeLinecap='round'/>
<path d='M2.5 4a8 8 0 0111 0' stroke='#22d3ee' strokeWidth='1.3' strokeLinecap='round' opacity='.5'/>
<line x1='8' y1='11' x2='8' y2='14' stroke='#22d3ee' strokeWidth='1.5' strokeLinecap='round'/>
</svg>
);
const IconUser = () => (
<svg width='15' height='15' viewBox='0 0 16 16' fill='none' aria-hidden='true'>
<circle cx='7' cy='5' r='2.3' stroke='#a78bfa' strokeWidth='1.4'/>
<path d='M2.5 14c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4' stroke='#a78bfa' strokeWidth='1.4' strokeLinecap='round'/>
<path d='M11 6.5l-1.2 2h1.2l-1.3 3' stroke='#fbbf24' strokeWidth='1.2' strokeLinecap='round' strokeLinejoin='round'/>
</svg>
);

const EVENT_CONFIG = {
deal_completed: {
borderClass: 'border-l-accent',
glowStyle: '0 0 10px rgba(0,255,136,0.3)',
badgeClass: 'bg-accent/10 text-accent',
dotClass: 'bg-accent',
Icon: IconDeal,
label: 'РЈРіРѕРґР°',
},
auction_bid: {
borderClass: 'border-l-orange-400',
glowStyle: '0 0 10px rgba(251,146,60,0.35)',
badgeClass: 'bg-orange-500/10 text-orange-400',
dotClass: 'bg-orange-400',
Icon: IconBid,
label: 'РЎС‚Р°РІРєР°',
},
new_channel: {
borderClass: 'border-l-cyan-400',
glowStyle: '0 0 10px rgba(34,211,238,0.25)',
badgeClass: 'bg-cyan-400/10 text-cyan-400',
dotClass: 'bg-cyan-400',
Icon: IconChannel,
label: 'РљР°РЅР°Р»',
},
new_user: {
borderClass: 'border-l-violet-400',
glowStyle: '0 0 10px rgba(167,139,250,0.25)',
badgeClass: 'bg-violet-400/10 text-violet-400',
dotClass: 'bg-violet-400',
Icon: IconUser,
label: 'Р®Р·РµСЂ',
},
};

// Stable key -- text only (NOT timestamp) because fake events recalculate
// created_at on every poll (relative to current `now`), so timestamp always drifts.
const stableKey = (e) => (e.text || '').trim().slice(0, 60);

const timeAgo = (isoStr) => {
	const diff = Date.now() - new Date(isoStr).getTime();
	if (diff < 0) return 'С‰РѕР№РЅРѕ';
	const mins = Math.floor(diff / 60000);
	if (mins < 1) return 'С‰РѕР№РЅРѕ';
	if (mins < 60) return `${mins}С…РІ`;
	const h = Math.floor(mins / 60);
	const rem = mins % 60;
	if (h < 24) return rem > 0 ? `${h}Рі ${rem}С…РІ` : `${h}Рі`;
	return `${Math.floor(h / 24)}Рґ`;
};

const cleanText = (text) => (text || '').replace(/^.\s/, '');

/* ActivityTicker -- stats prop comes from AuctionPage (real /stats/activity data).
   Without stats prop (e.g. on HomePage) falls back to counting feed events.
   The feed itself is controlled from admin (real + configurable fake events). */
const ActivityTicker = ({ stats }) => {
const [events, setEvents] = useState([]);
// newIds stores stable content-based keys, NOT array indices
const [newIds, setNewIds] = useState(new Set());
const [flashPulse, setFlashPulse] = useState(false);
const prevKeys = useRef(new Set());

const load = async () => {
try {
const { data } = await activityAPI.getFeed();
const isFirstLoad = prevKeys.current.size === 0;

if (!isFirstLoad) {
const added = new Set();
data.forEach((e) => {
const k = stableKey(e);
if (!prevKeys.current.has(k)) added.add(k);
});
if (added.size > 0) {
setNewIds(added);
setFlashPulse(true);
setTimeout(() => { setNewIds(new Set()); setFlashPulse(false); }, 4000);
}
}

prevKeys.current = new Set(data.map(stableKey));
setEvents(data);
} catch { /* silent */ }
};

useEffect(() => {
load();
const iv = setInterval(load, 30000);
return () => clearInterval(iv);
}, []);

if (events.length === 0) return null;

/* Side-panel: use real stats prop (from /stats/activity) when available,
   fallback to counting feed events (on HomePage where stats is not passed) */
const feedCounts = events.reduce((acc, e) => {
acc[e.type] = (acc[e.type] || 0) + 1;
return acc;
}, {});

const sideStats = stats ? [
{ key: 's1', label: 'РђСѓРєС†С–РѕРЅРё', value: stats.active_auctions  ?? 0, borderClass: 'border-l-orange-400', valueClass: 'text-orange-400', barClass: 'bg-orange-400' },
{ key: 's2', label: 'РЎС‚Р°РІРѕРє',   value: stats.bids_today        ?? 0, borderClass: 'border-l-amber-400',  valueClass: 'text-amber-400',  barClass: 'bg-amber-400'  },
{ key: 's3', label: 'РЈРіРѕРґ/С‚РёР¶', value: stats.deals_this_week   ?? 0, borderClass: 'border-l-accent',     valueClass: 'text-accent',     barClass: 'bg-accent'     },
{ key: 's4', label: 'РћРЅР»Р°Р№РЅ',   value: stats.online_investors  ?? 0, borderClass: 'border-l-cyan-400',   valueClass: 'text-cyan-400',   barClass: 'bg-cyan-400'   },
] : [
{ key: 'deal_completed', label: 'РЈРіРѕРґРё',  value: feedCounts.deal_completed || 0, borderClass: 'border-l-accent',     valueClass: 'text-accent',     barClass: 'bg-accent'     },
{ key: 'auction_bid',    label: 'РЎС‚Р°РІРєРё', value: feedCounts.auction_bid    || 0, borderClass: 'border-l-orange-400', valueClass: 'text-orange-400', barClass: 'bg-orange-400' },
{ key: 'new_channel',    label: 'РљР°РЅР°Р»Рё', value: feedCounts.new_channel    || 0, borderClass: 'border-l-cyan-400',   valueClass: 'text-cyan-400',   barClass: 'bg-cyan-400'   },
{ key: 'new_user',       label: 'Р®Р·РµСЂРё',  value: feedCounts.new_user       || 0, borderClass: 'border-l-violet-400', valueClass: 'text-violet-400', barClass: 'bg-violet-400' },
];

const maxSide = Math.max(...sideStats.map(s => s.value), 1);
const visible = events.slice(0, 6);

return (
<div className='mb-6 relative'>
{/* Top neon scanline */}
<motion.div
className='absolute inset-x-0 top-0 h-px z-10 pointer-events-none'
style={{ background: 'linear-gradient(90deg, transparent 0%, #00FF88 50%, transparent 100%)' }}
animate={{ opacity: [0.12, 0.5, 0.12] }}
transition={{ repeat: Infinity, duration: 3.5, ease: 'easeInOut' }}
/>

<div
className='bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border shadow-sm overflow-hidden transition-shadow duration-700'
style={flashPulse ? { boxShadow: '0 0 36px rgba(0,255,136,0.10), 0 0 12px rgba(0,255,136,0.07)' } : {}}
>
{/* Header */}
<div className='flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-card-border'>
<div className='flex items-center gap-2.5'>
<div className='flex items-center gap-1.5 bg-accent/10 px-2 py-0.5 rounded-full'>
<motion.span
className='block w-1.5 h-1.5 rounded-full bg-accent'
animate={{ opacity: [1, 0.2, 1], scale: [1, 0.7, 1] }}
transition={{ repeat: Infinity, duration: 1.4 }}
/>
<span className='text-[10px] font-black text-accent tracking-widest uppercase'>Live</span>
</div>
<span className='text-sm font-semibold text-gray-800 dark:text-white'>РђРєС‚РёРІРЅС–СЃС‚СЊ РїР»Р°С‚С„РѕСЂРјРё</span>
</div>
        </div>


{/* Body */}
<div className='flex divide-x divide-gray-100 dark:divide-card-border'>
{/* Feed */}
<div className='flex-1 min-w-0 px-3 py-2 space-y-1'>
<AnimatePresence initial={false} mode='popLayout'>
{visible.map((event, i) => {
const cfg = EVENT_CONFIG[event.type] ?? EVENT_CONFIG.new_user;
const { Icon } = cfg;
const isNew = newIds.has(stableKey(event));
return (
<motion.div
key={stableKey(event)}
layout
initial={{ opacity: 0, x: -20 }}
animate={{ opacity: 1, x: 0, boxShadow: isNew ? cfg.glowStyle : 'none' }}
exit={{ opacity: 0, x: -12, height: 0 }}
transition={{ duration: 0.25, delay: i * 0.03 }}
className={`flex items-center gap-2.5 pl-2.5 pr-2 py-1.5 rounded-r-lg border-l-2 ${cfg.borderClass} bg-gray-50 dark:bg-card-inner`}
>
<span className='flex-shrink-0'><Icon /></span>
<span className='flex-1 text-xs text-gray-700 dark:text-gray-300 truncate'>
{cleanText(event.text)}
</span>
<div className='flex items-center gap-1 flex-shrink-0'>
{isNew && (
<motion.span
initial={{ scale: 0 }}
animate={{ scale: 1 }}
className='text-[9px] font-black text-accent bg-accent/10 px-1.5 py-0.5 rounded-full uppercase'
>
New
</motion.span>
)}
<span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${cfg.badgeClass}`}>
{timeAgo(event.created_at)}
</span>
</div>
</motion.div>
);
})}
</AnimatePresence>
</div>

{/* Stats panel */}
<div className='w-32 flex-shrink-0 px-2.5 py-2 flex flex-col gap-1.5'>
<p className='text-[9px] font-bold uppercase tracking-wider text-gray-400 mb-0.5'>
{stats ? 'Р—Р°СЂР°Р·' : 'Р—Р° С„С–РґРѕРј'}
</p>
{sideStats.map(({ key, label, value, borderClass, valueClass, barClass }) => {
const pct = Math.round((value / maxSide) * 100);
return (
<div key={key} className={`px-2 py-1.5 rounded-lg bg-gray-50 dark:bg-card-inner border-l-2 ${borderClass}`}>
<div className='flex items-center justify-between mb-0.5'>
<p className='text-[9px] text-gray-400'>{label}</p>
<motion.span
key={value}
initial={{ scale: 1.4, opacity: 0 }}
animate={{ scale: 1, opacity: 1 }}
className={`font-black text-xs ${valueClass}`}
>
{value}
</motion.span>
</div>
<div className='h-0.5 rounded-full bg-gray-200 dark:bg-card overflow-hidden'>
<motion.div
className={`h-full rounded-full ${barClass}`}
initial={{ width: 0 }}
animate={{ width: `${pct}%` }}
transition={{ duration: 0.7, ease: 'easeOut' }}
/>
</div>
</div>
);
})}
</div>
</div>

{/* Bottom scroll ticker */}
<BottomTicker events={events} />
</div>
</div>
);
};

/* Thin auto-scrolling bottom ticker */
const BottomTicker = ({ events }) => {
const ref = useRef(null);
const posRef = useRef(0);
const rafRef = useRef(null);

useEffect(() => {
const el = ref.current;
if (!el || events.length === 0) return;
const step = () => {
posRef.current += 0.4;
if (posRef.current >= el.scrollWidth / 2) posRef.current = 0;
el.scrollLeft = posRef.current;
rafRef.current = requestAnimationFrame(step);
};
rafRef.current = requestAnimationFrame(step);
return () => cancelAnimationFrame(rafRef.current);
}, [events]);

const doubled = [...events, ...events];

return (
<div className='border-t border-gray-100 dark:border-card-border relative overflow-hidden'>
<div className='absolute left-0 top-0 bottom-0 w-6 bg-gradient-to-r from-white dark:from-card to-transparent z-10 pointer-events-none' />
<div className='absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-white dark:from-card to-transparent z-10 pointer-events-none' />
<div
ref={ref}
className='flex gap-2 overflow-hidden whitespace-nowrap px-3 py-1.5'
style={{ scrollBehavior: 'auto' }}
>
{doubled.map((e, i) => {
const cfg = EVENT_CONFIG[e.type] ?? EVENT_CONFIG.new_user;
return (
<span
key={i}
className='inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-gray-50 dark:bg-card-inner border border-gray-100 dark:border-card-border flex-shrink-0 text-gray-600 dark:text-gray-400'
>
<span className={`w-1 h-1 rounded-full flex-shrink-0 ${cfg.dotClass}`} />
{cleanText(e.text)}
</span>
);
})}
</div>
</div>
);
};

export default ActivityTicker;
