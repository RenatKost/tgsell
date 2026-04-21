import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { activityAPI } from '../../services/api';

const IconDeal = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="8" cy="8" r="6.5" stroke="#00FF88" strokeWidth="1.4"/>
    <path d="M5 8l2 2 4-4" stroke="#00FF88" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
const IconBid = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x="8.5" y="1.5" width="3.5" height="6.5" rx="0.8" transform="rotate(45 8.5 1.5)" fill="#fb923c" opacity=".85"/>
    <path d="M2 14l4.5-4.5" stroke="#fb923c" strokeWidth="1.8" strokeLinecap="round"/>
    <path d="M10 12.5h3.5" stroke="#fb923c" strokeWidth="1.4" strokeLinecap="round"/>
  </svg>
);
const IconChannel = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="8" cy="9" r="2" fill="#22d3ee"/>
    <path d="M5 6.5a4 4 0 016 0" stroke="#22d3ee" strokeWidth="1.3" strokeLinecap="round"/>
    <path d="M2.5 4a8 8 0 0111 0" stroke="#22d3ee" strokeWidth="1.3" strokeLinecap="round" opacity=".5"/>
    <line x1="8" y1="11" x2="8" y2="14" stroke="#22d3ee" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);
const IconUser = () => (
  <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <circle cx="7" cy="5" r="2.3" stroke="#a78bfa" strokeWidth="1.4"/>
    <path d="M2.5 14c0-2.5 2-4 4.5-4s4.5 1.5 4.5 4" stroke="#a78bfa" strokeWidth="1.4" strokeLinecap="round"/>
    <path d="M11 6.5l-1.2 2h1.2l-1.3 3" stroke="#fbbf24" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
const IconTrophy = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M8 11c-2.5 0-4-1.5-4-4V3h8v4c0 2.5-1.5 4-4 4z" stroke="#00FF88" strokeWidth="1.3" strokeLinejoin="round"/>
    <path d="M4 4H2.5C2 4 1.5 4.5 1.5 5.5S2 7 3 7" stroke="#00FF88" strokeWidth="1.2" strokeLinecap="round"/>
    <path d="M12 4h1.5c.5 0 1 .5 1 1.5S14 7 13 7" stroke="#00FF88" strokeWidth="1.2" strokeLinecap="round"/>
    <line x1="8" y1="11" x2="8" y2="13" stroke="#00FF88" strokeWidth="1.3" strokeLinecap="round"/>
    <line x1="5.5" y1="13" x2="10.5" y2="13" stroke="#00FF88" strokeWidth="1.3" strokeLinecap="round"/>
  </svg>
);
const IconFire = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M8 14c3 0 5-2 5-5 0-2-1-3.5-2.5-4.5 0 1.5-.5 2.5-1.5 3C9.5 6 9 4.5 9 3c-1 .5-3 2-3 5 0 1 .3 1.8.8 2.5C7 9.5 7 8 7.5 7.5 7.5 9 7 10.5 8 14z" fill="#fb923c" opacity=".85"/>
  </svg>
);

const EVENT_CONFIG = {
  deal_completed: { borderClass: 'border-l-accent',     glowStyle: '0 0 10px rgba(0,255,136,0.3)',     badgeClass: 'bg-accent/10 text-accent',         dotClass: 'bg-accent',      Icon: IconDeal    },
  auction_bid:    { borderClass: 'border-l-orange-400', glowStyle: '0 0 10px rgba(251,146,60,0.35)',    badgeClass: 'bg-orange-500/10 text-orange-400', dotClass: 'bg-orange-400', Icon: IconBid     },
  new_channel:    { borderClass: 'border-l-cyan-400',   glowStyle: '0 0 10px rgba(34,211,238,0.25)',   badgeClass: 'bg-cyan-400/10 text-cyan-400',     dotClass: 'bg-cyan-400',   Icon: IconChannel },
  new_user:       { borderClass: 'border-l-violet-400', glowStyle: '0 0 10px rgba(167,139,250,0.25)', badgeClass: 'bg-violet-400/10 text-violet-400', dotClass: 'bg-violet-400', Icon: IconUser    },
};

const CATEGORY_LABELS = {
  deal_completed: 'Угоди',
  auction_bid:    'Ставки',
  new_channel:    'Канали',
  new_user:       'Юзери',
};

// Text-only stable key — fake events recalculate created_at each poll so timestamp drifts
const stableKey = (e) => (e.text || '').trim().slice(0, 60);

const timeAgo = (isoStr) => {
  const diff = Date.now() - new Date(isoStr).getTime();
  if (diff < 0) return 'щойно';
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'щойно';
  if (mins < 60) return mins + 'хв';
  const h = Math.floor(mins / 60);
  const rem = mins % 60;
  if (h < 24) return rem > 0 ? h + 'г ' + rem + 'хв' : h + 'г';
  return Math.floor(h / 24) + 'д';
};

const cleanText = (text) => (text || '').replace(/^.\s/, '');

const extractAmount = (text) => {
  const m = (text || '').match(/(\d[\d\s]*)\s*USDT/);
  if (!m) return 0;
  return parseInt(m[1].replace(/\s/g, ''), 10) || 0;
};

const fmtAmount = (n) => n >= 1000 ? (n / 1000).toFixed(1).replace(/\.0$/, '') + 'k' : String(n);

const ActivityTicker = ({ stats }) => {
  const [events, setEvents] = useState([]);
  const [newIds, setNewIds] = useState(new Set());
  const [flashPulse, setFlashPulse] = useState(false);
  const prevKeys = useRef(new Set());

  const load = async () => {
    try {
      const { data } = await activityAPI.getFeed();
      const isFirstLoad = prevKeys.current.size === 0;
      if (!isFirstLoad) {
        const added = new Set();
        data.forEach((e) => { const k = stableKey(e); if (!prevKeys.current.has(k)) added.add(k); });
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

  useEffect(() => { load(); const iv = setInterval(load, 30000); return () => clearInterval(iv); }, []);

  if (events.length === 0) return null;

  // --- Compute side-panel "Тренди" metrics from feed events ---
  const dealEvents   = events.filter(e => e.type === 'deal_completed');
  const bidEvents    = events.filter(e => e.type === 'auction_bid');
  const moneyEvents  = [...dealEvents, ...bidEvents];
  const amounts      = moneyEvents.map(e => extractAmount(e.text));
  const topAmount    = amounts.length > 0 ? Math.max(...amounts) : 0;
  const totalVolume  = amounts.reduce((s, v) => s + v, 0);
  const topDealText  = moneyEvents.find(e => extractAmount(e.text) === topAmount);

  const feedCounts = events.reduce((acc, e) => { acc[e.type] = (acc[e.type] || 0) + 1; return acc; }, {});
  const total = events.length || 1;
  const activityRows = [
    { key: 'deal_completed', label: 'Угоди',  count: feedCounts.deal_completed || 0, barClass: 'bg-accent',      textClass: 'text-accent'      },
    { key: 'auction_bid',    label: 'Ставки', count: feedCounts.auction_bid    || 0, barClass: 'bg-orange-400',  textClass: 'text-orange-400'  },
    { key: 'new_channel',    label: 'Канали', count: feedCounts.new_channel    || 0, barClass: 'bg-cyan-400',    textClass: 'text-cyan-400'    },
    { key: 'new_user',       label: 'Юзери',  count: feedCounts.new_user       || 0, barClass: 'bg-violet-400',  textClass: 'text-violet-400'  },
  ];

  const visible = events.slice(0, 8);

  return (
    <div className="mb-6 relative">
      <motion.div
        className="absolute inset-x-0 top-0 h-px z-10 pointer-events-none"
        style={{ background: 'linear-gradient(90deg, transparent 0%, #00FF88 50%, transparent 100%)' }}
        animate={{ opacity: [0.12, 0.5, 0.12] }}
        transition={{ repeat: Infinity, duration: 3.5, ease: 'easeInOut' }}
      />
      <div
        className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border shadow-sm overflow-hidden transition-shadow duration-700"
        style={flashPulse ? { boxShadow: '0 0 36px rgba(0,255,136,0.10), 0 0 12px rgba(0,255,136,0.07)' } : {}}
      >
        {/* Header */}
        <div className="flex items-center px-4 py-2.5 border-b border-gray-100 dark:border-card-border gap-2.5">
          <div className="flex items-center gap-1.5 bg-accent/10 px-2 py-0.5 rounded-full">
            <motion.span
              className="block w-1.5 h-1.5 rounded-full bg-accent"
              animate={{ opacity: [1, 0.2, 1], scale: [1, 0.7, 1] }}
              transition={{ repeat: Infinity, duration: 1.4 }}
            />
            <span className="text-[10px] font-black text-accent tracking-widest uppercase">Live</span>
          </div>
          <span className="text-sm font-semibold text-gray-800 dark:text-white">Активність платформи</span>
        </div>

        {/* Body */}
        <div className="flex divide-x divide-gray-100 dark:divide-card-border">

          {/* Left — event feed */}
          <div className="flex-1 min-w-0 px-3 py-2 space-y-1">
            <AnimatePresence initial={false} mode="popLayout">
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
                    className={"flex items-center gap-2.5 pl-2.5 pr-2 py-1.5 rounded-r-lg border-l-2 " + cfg.borderClass + " bg-gray-50 dark:bg-card-inner"}
                  >
                    <span className="flex-shrink-0"><Icon /></span>
                    <span className="flex-1 text-xs text-gray-700 dark:text-gray-300 truncate">{cleanText(event.text)}</span>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      {isNew && (
                        <motion.span
                          initial={{ scale: 0 }}
                          animate={{ scale: 1 }}
                          className="text-[9px] font-black text-accent bg-accent/10 px-1.5 py-0.5 rounded-full uppercase"
                        >New</motion.span>
                      )}
                      <span className={"text-[10px] font-semibold px-1.5 py-0.5 rounded-md " + cfg.badgeClass}>{timeAgo(event.created_at)}</span>
                    </div>
                  </motion.div>
                );
              })}
            </AnimatePresence>
          </div>

          {/* Right — Trends panel (unique info, not duplicating dashboard) */}
          <div className="w-36 flex-shrink-0 flex flex-col divide-y divide-gray-100 dark:divide-card-border">

            {/* Record deal */}
            <div className="px-3 py-2.5">
              <div className="flex items-center gap-1 mb-1">
                <IconTrophy />
                <span className="text-[9px] font-bold uppercase tracking-wider text-gray-400">Рекорд</span>
              </div>
              {topAmount > 0 ? (
                <>
                  <motion.p
                    key={topAmount}
                    initial={{ scale: 1.2, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    className="text-lg font-black text-accent leading-none"
                  >{fmtAmount(topAmount)} <span className="text-xs font-semibold opacity-60">USDT</span></motion.p>
                  <p className="text-[10px] text-gray-400 mt-0.5 truncate">{cleanText(topDealText?.text || '')}</p>
                </>
              ) : (
                <p className="text-xs text-gray-400">— поки немає —</p>
              )}
            </div>

            {/* Total volume */}
            <div className="px-3 py-2.5">
              <div className="flex items-center gap-1 mb-1">
                <IconFire />
                <span className="text-[9px] font-bold uppercase tracking-wider text-gray-400">Обіг сесії</span>
              </div>
              <motion.p
                key={totalVolume}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-base font-black text-amber-400 leading-none"
              >{totalVolume > 0 ? fmtAmount(totalVolume) + ' USDT' : '—'}</motion.p>
            </div>

            {/* Activity split */}
            <div className="px-3 py-2 flex-1">
              <p className="text-[9px] font-bold uppercase tracking-wider text-gray-400 mb-1.5">Розподіл</p>
              <div className="space-y-1.5">
                {activityRows.map(({ key, label, count, barClass, textClass }) => {
                  const pct = Math.round((count / total) * 100);
                  return (
                    <div key={key}>
                      <div className="flex justify-between items-center mb-0.5">
                        <span className="text-[9px] text-gray-400">{label}</span>
                        <span className={"text-[9px] font-bold " + textClass}>{pct}%</span>
                      </div>
                      <div className="h-0.5 rounded-full bg-gray-200 dark:bg-card overflow-hidden">
                        <motion.div
                          className={"h-full rounded-full " + barClass}
                          initial={{ width: 0 }}
                          animate={{ width: pct + '%' }}
                          transition={{ duration: 0.7, ease: 'easeOut' }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Bottom scrolling ticker */}
        <BottomTicker events={events} />
      </div>
    </div>
  );
};

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
    <div className="border-t border-gray-100 dark:border-card-border relative overflow-hidden">
      <div className="absolute left-0 top-0 bottom-0 w-6 bg-gradient-to-r from-white dark:from-card to-transparent z-10 pointer-events-none" />
      <div className="absolute right-0 top-0 bottom-0 w-6 bg-gradient-to-l from-white dark:from-card to-transparent z-10 pointer-events-none" />
      <div ref={ref} className="flex gap-2 overflow-hidden whitespace-nowrap px-3 py-1.5" style={{ scrollBehavior: 'auto' }}>
        {doubled.map((e, i) => {
          const cfg = EVENT_CONFIG[e.type] ?? EVENT_CONFIG.new_user;
          return (
            <span key={i} className={"inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-full bg-gray-50 dark:bg-card-inner border border-gray-100 dark:border-card-border flex-shrink-0 text-gray-600 dark:text-gray-400"}>
              <span className={"w-1 h-1 rounded-full flex-shrink-0 " + cfg.dotClass} />
              {cleanText(e.text)}
            </span>
          );
        })}
      </div>
    </div>
  );
};

export default ActivityTicker;