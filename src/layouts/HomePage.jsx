import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { NavLink } from 'react-router-dom';
import Calculator from '../components/Main/Calculator';
import ActivityTicker from '../components/Auction/ActivityTicker';

// ─── Animated counter ────────────────────────────────────────────────────────
const StatCounter = ({ end, label, suffix }) => {
  const [count, setCount] = useState(0);
  const ref = useRef(null);
  const done = useRef(false);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting && !done.current) {
        done.current = true;
        let s = 0;
        const steps = 50;
        const inc = end / steps;
        const iv = setInterval(() => {
          s += inc;
          if (s >= end) { setCount(end); clearInterval(iv); }
          else setCount(Math.floor(s));
        }, 1200 / steps);
      }
    }, { threshold: 0.3 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [end]);
  const fmt = n => {
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace('.0', '') + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1).replace('.0', '') + 'K';
    return String(n);
  };
  return (
    <div ref={ref} className="text-center">
      <p className="text-2xl lg:text-3xl font-black text-gray-900 dark:text-white">{fmt(count)}{suffix}</p>
      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{label}</p>
    </div>
  );
};

// ─── Section tag badge ────────────────────────────────────────────────────────
const Tag = ({ text }) => (
  <span className="inline-block bg-accent/10 border border-accent/20 text-accent text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">{text}</span>
);

// ─── How it works step ────────────────────────────────────────────────────────
const Step = ({ n, title, desc, stepCls }) => (
  <div className="flex gap-4">
    <div className={"w-9 h-9 rounded-xl flex items-center justify-center text-sm font-black flex-shrink-0 " + stepCls}>{n}</div>
    <div>
      <p className="font-bold text-gray-900 dark:text-white text-sm mb-0.5">{title}</p>
      <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{desc}</p>
    </div>
  </div>
);

// ─── Hero floating channel card ───────────────────────────────────────────────
const HeroCard = () => (
  <div className="relative ml-auto max-w-sm w-full">
    <div className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-5" style={{ boxShadow: '0 0 50px rgba(0,255,136,0.08)' }}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center text-xl font-black text-accent">₿</div>
          <div>
            <p className="font-bold text-gray-900 dark:text-white text-sm">Crypto UA</p>
            <p className="text-xs text-gray-400">t.me/cryptoua</p>
          </div>
        </div>
        <span className="text-[10px] font-black bg-accent/10 text-accent px-2 py-0.5 rounded-full border border-accent/20">Продається</span>
      </div>
      <div className="grid grid-cols-3 gap-2 mb-4">
        {[['125K', 'Підписники', 'text-gray-900 dark:text-white'], ['12.4%', 'ER', 'text-accent'], ['850', 'USDT/міс', 'text-violet-400']].map(([v, l, cls]) => (
          <div key={l} className="bg-gray-50 dark:bg-card-inner rounded-xl p-2 text-center">
            <p className={"text-sm font-black " + cls}>{v}</p>
            <p className="text-[9px] text-gray-400">{l}</p>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 bg-accent/5 border border-accent/10 rounded-xl p-3 mb-4">
        <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center flex-shrink-0">
          <span className="text-accent text-xs font-black">AI</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-gray-400">AI Score</span>
            <span className="text-xs font-black text-accent">92/100</span>
          </div>
          <div className="h-1.5 bg-gray-100 dark:bg-card rounded-full">
            <div className="h-full rounded-full bg-accent" style={{ width: '92%' }} />
          </div>
        </div>
        <span className="bg-accent text-black text-[10px] font-black px-2 py-0.5 rounded-full flex-shrink-0">КУПИТИ</span>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[10px] text-gray-400">Ціна</p>
          <p className="text-lg font-black text-gray-900 dark:text-white">15 000 <span className="text-sm font-normal text-gray-400">USDT</span></p>
        </div>
        <div className="bg-accent text-black text-xs font-black px-4 py-2 rounded-xl cursor-pointer">Купити →</div>
      </div>
    </div>
    <motion.div
      animate={{ y: [-3, 3, -3] }} transition={{ repeat: Infinity, duration: 3 }}
      className="absolute -top-3 -right-4 bg-white dark:bg-card border border-gray-100 dark:border-card-border rounded-xl px-3 py-2 shadow-lg"
    >
      <div className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
        <span className="text-xs font-bold dark:text-white">Ескроу захист</span>
      </div>
    </motion.div>
    <motion.div
      animate={{ y: [3, -3, 3] }} transition={{ repeat: Infinity, duration: 3, delay: 1.2 }}
      className="absolute -bottom-3 -left-4 bg-white dark:bg-card border border-gray-100 dark:border-card-border rounded-xl px-3 py-2 shadow-lg"
    >
      <p className="text-[9px] text-gray-400">Обіг платформи</p>
      <p className="text-sm font-black text-accent">$2.4M+ USDT</p>
    </motion.div>
  </div>
);

// ─── Mock UI: AI аналіз ───────────────────────────────────────────────────────
const AIMockUI = () => (
  <div className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-5 shadow-sm dark:shadow-neon w-full max-w-xs">
    <div className="flex items-center justify-between mb-4">
      <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">TgSell Аналіз</span>
      <span className="bg-accent text-black text-xs font-black px-3 py-1 rounded-full">КУПИТИ</span>
    </div>
    <div className="flex items-center gap-4 mb-4">
      <div className="relative w-16 h-16 flex-shrink-0">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
          <circle cx="18" cy="18" r="15" fill="none" stroke="#1A3A2A" strokeWidth="3" />
          <circle cx="18" cy="18" r="15" fill="none" stroke="#00FF88" strokeWidth="3" strokeDasharray="87 100" strokeLinecap="round" />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-accent font-black text-sm">87</span>
      </div>
      <div className="space-y-1.5 flex-1">
        {[['Аудиторія', 92, 'text-accent', 'bg-accent'], ['Контент', 85, 'text-cyan-400', 'bg-cyan-400'], ['Монетизація', 78, 'text-violet-400', 'bg-violet-400']].map(([l, v, tc, bc]) => (
          <div key={l}>
            <div className="flex justify-between text-[10px] mb-0.5">
              <span className="text-gray-400">{l}</span>
              <span className={tc}>{v}%</span>
            </div>
            <div className="h-1 bg-gray-100 dark:bg-card-inner rounded-full">
              <div className={"h-full rounded-full " + bc} style={{ width: v + '%' }} />
            </div>
          </div>
        ))}
      </div>
    </div>
    <div className="bg-accent/5 rounded-xl p-3 border border-accent/10">
      <p className="text-[10px] text-gray-400 mb-1">Висновок TgSell</p>
      <p className="text-xs text-gray-700 dark:text-gray-300">Канал має сильну органічну аудиторію та стабільний ріст. Рекомендовано до покупки.</p>
    </div>
  </div>
);

// ─── Mock UI: Ескроу ──────────────────────────────────────────────────────────
const EscrowMockUI = () => {
  const steps = ['Оплата', 'Ескроу', 'Передача', 'Виплата'];
  return (
    <div className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-5 shadow-sm dark:shadow-neon w-full max-w-xs">
      <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-4">Угода в ескроу</p>
      <div className="relative flex justify-between mb-5">
        <div className="absolute top-4 left-4 right-4 h-px bg-gray-100 dark:bg-card-border" />
        {steps.map((s, i) => (
          <div key={s} className="flex flex-col items-center gap-1 relative z-10">
            <div className={"w-8 h-8 rounded-full flex items-center justify-center text-xs font-black " + (i < 2 ? 'bg-accent text-black' : i === 2 ? 'bg-orange-400 text-white' : 'bg-gray-100 dark:bg-card-inner text-gray-400')}>
              {i < 2 ? '✓' : i + 1}
            </div>
            <span className="text-[9px] text-gray-400 text-center">{s}</span>
          </div>
        ))}
      </div>
      <div className="space-y-2">
        <div className="flex justify-between items-center bg-gray-50 dark:bg-card-inner rounded-xl p-2.5">
          <span className="text-xs text-gray-400">Покупець переказав</span>
          <span className="text-xs font-bold text-accent">1 500 USDT</span>
        </div>
        <div className="flex justify-between items-center bg-gray-50 dark:bg-card-inner rounded-xl p-2.5">
          <span className="text-xs text-gray-400">Комісія платформи</span>
          <span className="text-xs font-bold text-orange-400">3%</span>
        </div>
        <div className="flex justify-between items-center bg-accent/5 border border-accent/10 rounded-xl p-2.5">
          <span className="text-xs font-semibold text-gray-700 dark:text-gray-200">Продавець отримає</span>
          <span className="text-sm font-black text-accent">1 455 USDT</span>
        </div>
      </div>
    </div>
  );
};

// ─── Mock UI: Каталог ─────────────────────────────────────────────────────────
const CatalogMockUI = () => (
  <div className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-5 shadow-sm dark:shadow-neon w-full max-w-xs space-y-3">
    <div className="flex items-center gap-2 bg-gray-50 dark:bg-card-inner rounded-xl px-3 py-2">
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <circle cx="7" cy="7" r="5" stroke="#9ca3af" strokeWidth="1.5" />
        <path d="M11 11l2.5 2.5" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
      <span className="text-xs text-gray-400">Пошук каналу...</span>
    </div>
    <div className="flex gap-1.5 flex-wrap">
      {['Крипто', 'Бізнес', '10K-100K', 'ER > 10%'].map(f => (
        <span key={f} className="text-[10px] bg-accent/10 text-accent font-semibold px-2 py-0.5 rounded-full border border-accent/20">{f}</span>
      ))}
    </div>
    {[
      { name: 'Crypto UA', subs: '125K', er: '12%', price: '15 000', hi: true },
      { name: 'BizHub', subs: '89K', er: '8.5%', price: '9 500', hi: false },
      { name: 'IT Digest', subs: '210K', er: '9.1%', price: '28 000', hi: false },
    ].map(c => (
      <div key={c.name} className={"rounded-xl border p-3 " + (c.hi ? 'border-accent/20 bg-accent/5' : 'border-gray-100 dark:border-card-border bg-gray-50 dark:bg-card-inner')}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className={"w-7 h-7 rounded-lg flex items-center justify-center text-xs font-black " + (c.hi ? 'bg-accent/10 text-accent' : 'bg-gray-200 dark:bg-card text-gray-500')}>
              {c.name[0]}
            </div>
            <span className="text-xs font-bold dark:text-white">{c.name}</span>
          </div>
          <span className="text-xs font-black text-accent">{c.price}</span>
        </div>
        <div className="flex gap-3 mt-1.5">
          <span className="text-[10px] text-gray-400">{c.subs} підп.</span>
          <span className="text-[10px] text-emerald-400">ER {c.er}</span>
        </div>
      </div>
    ))}
  </div>
);

// ─── Mock UI: Аукціон ─────────────────────────────────────────────────────────
const AuctionMockUI = () => {
  const [bid, setBid] = useState(3200);
  return (
    <div className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-5 shadow-sm dark:shadow-neon w-full max-w-xs">
      <div className="flex items-center justify-between mb-4">
        <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">Аукціон</span>
        <span className="text-[10px] bg-orange-400/10 text-orange-400 font-bold px-2 py-0.5 rounded-full border border-orange-400/20">LIVE</span>
      </div>
      <div className="flex items-center gap-2 mb-3">
        <div className="w-8 h-8 rounded-lg bg-cyan-400/10 flex items-center justify-center text-cyan-400 font-black text-xs flex-shrink-0">T</div>
        <div>
          <p className="text-xs font-bold dark:text-white">Tech Digest UA</p>
          <p className="text-[10px] text-gray-400">210K підписників</p>
        </div>
      </div>
      <div className="bg-orange-400/5 border border-orange-400/10 rounded-xl p-3 mb-3">
        <p className="text-[10px] text-gray-400 mb-1.5">Залишилось часу</p>
        <div className="flex gap-2">
          {[['02', 'год'], ['14', 'хв'], ['38', 'с']].map(([v, l]) => (
            <div key={l} className="bg-orange-400/10 rounded-lg px-2 py-1.5 text-center flex-1">
              <p className="text-sm font-black text-orange-400 leading-none">{v}</p>
              <p className="text-[8px] text-orange-400/60 mt-0.5">{l}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="flex justify-between items-center mb-3">
        <span className="text-xs text-gray-400">Поточна ставка</span>
        <motion.span key={bid} initial={{ scale: 1.2, color: '#00FF88' }} animate={{ scale: 1, color: '#00FF88' }} className="text-lg font-black text-accent">
          {bid.toLocaleString('uk-UA')} USDT
        </motion.span>
      </div>
      <button
        onClick={() => setBid(b => b + 100)}
        className="w-full bg-accent text-black font-black py-2.5 rounded-xl text-sm hover:brightness-110 transition-all"
      >
        Зробити ставку +100 USDT
      </button>
    </div>
  );
};

// ─── Main ─────────────────────────────────────────────────────────────────────
const HomePage = () => {
  const earnCards = [
    {
      gradient: 'linear-gradient(135deg,#00FF88,#00cc6a)',
      accentColor: '#00FF88',
      label: '01',
      title: 'Купи готову аудиторію',
      benefit: 'Заробляй на рекламі з першого дня',
      points: [
        'Канал з аудиторією коштує більше порожнього',
        'Рекламний дохід окупає покупку за 6-18 міс',
        'AI-оцінка якості аудиторії перед купівлею',
      ],
      to: '/catalog',
      cta: 'Переглянути каталог',
    },
    {
      gradient: 'linear-gradient(135deg,#a78bfa,#7c3aed)',
      accentColor: '#a78bfa',
      label: '02',
      title: 'Продай свій канал',
      benefit: 'Отримай USDT з ескроу-захистом',
      points: [
        'Виставляй на продаж за 5 хвилин',
        'Безпечна передача через ескроу',
        'AI визначить справедливу ціну',
      ],
      to: '/sell',
      cta: 'Виставити на продаж',
    },
    {
      gradient: 'linear-gradient(135deg,#fb923c,#ea580c)',
      accentColor: '#fb923c',
      label: '03',
      title: 'Торгуй на аукціонах',
      benefit: 'Купуй нижче ринкової ціни',
      points: [
        'Канали стартують з низької ціни',
        'Реальна конкуренція — ти контролюєш бюджет',
        'Аукціони завершуються 24/7',
      ],
      to: '/auction',
      cta: 'Активні аукціони',
    },
  ];

  const features = [
    {
      tag: 'TgSell Аналіз',
      title: 'TgSell оцінює кожен канал',
      desc: 'TgSell аналізує останні 20 постів, 14 днів статистики і дає вердикт: купити, чекати або уникнути. Ніякого гадання.',
      points: [
        'Оцінка якості аудиторії від 0 до 100',
        'Аналіз тематики і тональності контенту',
        'Прогноз ROI і строк окупності',
        'Виявлення ботів і накрутки',
      ],
      MockUI: AIMockUI,
      reverse: false,
    },
    {
      tag: 'Ескроу захист',
      title: 'Угоди без ризику для обох сторін',
      desc: 'USDT замерзає на ескроу-гаманці до завершення передачі каналу. Ні продавець, ні покупець не можуть отримати гроші раніше строку.',
      points: [
        'Автоматична TRON-адреса для кожної угоди',
        'Гроші звільняються тільки після підтвердження',
        'Адмін-модерація спорів',
        'Комісія 3% — одна з найнижчих на ринку',
      ],
      MockUI: EscrowMockUI,
      reverse: true,
    },
    {
      tag: 'Каталог',
      title: 'Знайди ідеальний канал за секунди',
      desc: 'Фільтруй за категорією, охопленням, ER, ціною та доходом. Статистика підтягується автоматично кожні 3 години — ніякого ручного вводу.',
      points: [
        'Більше 500 каналів в каталозі',
        'Авто-збір статистики кожні 3 години',
        'Фільтр за ER, підписниками, доходом',
        'Збереження обраних каналів',
      ],
      MockUI: CatalogMockUI,
      reverse: false,
    },
    {
      tag: 'Аукціони',
      title: 'Купуй дешевше ринку на аукціонах',
      desc: 'Канали виставляються з мінімальною ціною. Ти конкуруєш в реальному часі — хто дав більше, той і отримує.',
      points: [
        'Старт від мінімальної ціни продавця',
        'Лічильник часу в реальному часі',
        'Авто-продовження при ставці в останню хвилину',
        'Переможець отримує канал через ескроу',
      ],
      MockUI: AuctionMockUI,
      reverse: true,
    },
  ];

  const howItWorks = [
    {
      title: 'Купівля каналу',
      borderCls: 'border-accent/30',
      headerCls: 'bg-accent/5',
      titleCls: 'text-accent',
      stepCls: 'bg-accent/10 text-accent',
      steps: [
        { title: 'Вибір каналу', desc: 'Переглядай каталог, фільтруй за параметрами, перевіряй AI-аналіз і статистику' },
        { title: 'Погодження умов', desc: 'Зв\'яжись з продавцем в чаті угоди, обговори деталі передачі' },
        { title: 'Оплата в ескроу', desc: 'Переказуєш USDT на захищений гаманець угоди — кошти заморожені' },
        { title: 'Отримання каналу', desc: 'Після передачі прав адмін звільняє кошти продавцю, угода закрита' },
      ],
    },
    {
      title: 'Продаж каналу',
      borderCls: 'border-violet-400/30',
      headerCls: 'bg-violet-400/5',
      titleCls: 'text-violet-400',
      stepCls: 'bg-violet-400/10 text-violet-400',
      steps: [
        { title: 'Виставлення', desc: 'Заповнюєш форму, підключаєш Telegram — статистика підтягується автоматично' },
        { title: 'Модерація', desc: 'Адмін перевіряє оголошення протягом 24 годин і публікує його' },
        { title: 'Угода', desc: 'Покупець платить USDT в ескроу, ти передаєш права на канал' },
        { title: 'Виплата', desc: 'Отримуєш USDT на свій TRC-20 гаманець мінус 3% комісія платформи' },
      ],
    },
  ];

  return (
    <div>
      {/* ── 1. HERO ─────────────────────────────────────────────────────── */}
      <section className="relative min-h-[88vh] flex items-center pt-20 pb-8 overflow-hidden">
        <div className="absolute inset-0 pointer-events-none" style={{
          backgroundImage: 'linear-gradient(rgba(0,255,136,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(0,255,136,0.025) 1px, transparent 1px)',
          backgroundSize: '60px 60px'
        }} />
        <div className="absolute top-1/3 right-1/4 w-96 h-96 rounded-full blur-3xl pointer-events-none" style={{ background: 'rgba(0,255,136,0.04)' }} />
        <div className="w-full grid lg:grid-cols-2 gap-12 items-center relative z-10">
          <motion.div initial={{ opacity: 0, y: 40 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7 }}>
            <div className="inline-flex items-center gap-2 bg-accent/10 border border-accent/20 rounded-full px-4 py-1.5 mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
              <span className="text-xs font-bold text-accent">Перша Ukrainian Telegram Marketplace</span>
            </div>
            <h1 className="text-4xl lg:text-5xl xl:text-6xl font-black text-gray-900 dark:text-white leading-tight mb-6">
              Купуй та продавай<br />
              <span className="text-accent">Telegram</span> канали<br />
              безпечно
            </h1>
            <p className="text-lg text-gray-500 dark:text-gray-300 leading-relaxed mb-8 max-w-lg">
              Ескроу-захист, AI-аналіз і аукціони в реальному часі. Більше 500 каналів для купівлі з USDT (TRC-20).
            </p>
            <div className="flex gap-8 sm:gap-12 mb-10">
              <StatCounter end={500} label="Каналів" suffix="+" />
              <StatCounter end={1200} label="Угод" suffix="+" />
              <StatCounter end={3400} label="Покупців" suffix="+" />
              <StatCounter end={2400000} label="USDT обіг" suffix="+" />
            </div>
            <div className="flex gap-4 flex-wrap">
              <NavLink to="/catalog" className="bg-accent text-black font-black px-8 py-3.5 rounded-xl text-sm uppercase tracking-wider shadow-lg shadow-accent/20 hover:brightness-110 transition-all">
                Переглянути каталог
              </NavLink>
              <NavLink to="/sell" className="border border-gray-200 dark:border-card-border text-gray-800 dark:text-white font-bold px-8 py-3.5 rounded-xl text-sm uppercase tracking-wider hover:border-accent hover:text-accent dark:hover:border-accent dark:hover:text-accent transition-all">
                Продати канал
              </NavLink>
            </div>
          </motion.div>
          <motion.div initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.7, delay: 0.2 }}>
            <HeroCard />
          </motion.div>
        </div>
      </section>

      {/* ── 2. LIVE ACTIVITY ────────────────────────────────────────────── */}
      <ActivityTicker />

      {/* ── 3. ЯК ЗАРОБИТИ ──────────────────────────────────────────────── */}
      <section className="py-20">
        <div className="text-center mb-12">
          <Tag text="Заробіток" />
          <h2 className="text-3xl lg:text-4xl font-black text-gray-900 dark:text-white">Три способи заробити</h2>
          <p className="text-gray-400 mt-3 max-w-xl mx-auto">Незалежно від ролі — ти знайдеш свою вигоду на TgSell</p>
        </div>
        <div className="grid md:grid-cols-3 gap-6">
          {earnCards.map((card, i) => (
            <motion.div
              key={card.label}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.12, duration: 0.5 }}
              className="flex flex-col"
            >
              <div className="h-1 rounded-t-2xl" style={{ background: card.gradient }} />
              <div className="bg-white dark:bg-card rounded-b-2xl border border-t-0 border-gray-100 dark:border-card-border p-6 flex flex-col flex-1">
                <span className="text-5xl font-black text-gray-100 dark:text-white/5 mb-2 leading-none select-none">{card.label}</span>
                <h3 className="text-lg font-black text-gray-900 dark:text-white mb-1">{card.title}</h3>
                <p className="text-sm font-semibold mb-4" style={{ color: card.accentColor }}>{card.benefit}</p>
                <ul className="space-y-2 mb-6 flex-1">
                  {card.points.map(p => (
                    <li key={p} className="flex items-start gap-2 text-sm text-gray-500 dark:text-gray-400">
                      <span className="w-1 h-1 rounded-full bg-accent mt-2 flex-shrink-0" />
                      {p}
                    </li>
                  ))}
                </ul>
                <NavLink to={card.to} className="text-sm font-bold text-accent hover:underline">{card.cta} →</NavLink>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── 4. FEATURES SHOWCASE ─────────────────────────────────────────── */}
      <section className="py-20">
        <div className="text-center mb-16">
          <Tag text="Інструменти" />
          <h2 className="text-3xl lg:text-4xl font-black text-gray-900 dark:text-white">Що ми пропонуємо</h2>
          <p className="text-gray-400 mt-3 max-w-xl mx-auto">Кожен інструмент створений щоб ти заробляв, а не гадав</p>
        </div>
        <div className="space-y-24">
          {features.map((f, i) => (
            <motion.div
              key={f.tag}
              initial={{ opacity: 0, y: 40 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.6 }}
              className="grid lg:grid-cols-2 gap-12 items-center"
            >
              <div className={f.reverse ? 'lg:order-2' : ''}>
                <Tag text={f.tag} />
                <h3 className="text-2xl lg:text-3xl font-black text-gray-900 dark:text-white mb-4">{f.title}</h3>
                <p className="text-gray-500 dark:text-gray-300 leading-relaxed mb-6">{f.desc}</p>
                <ul className="space-y-3">
                  {f.points.map(p => (
                    <li key={p} className="flex items-start gap-3 text-sm text-gray-600 dark:text-gray-300">
                      <div className="w-5 h-5 rounded-full bg-accent/10 border border-accent/20 flex items-center justify-center flex-shrink-0 mt-0.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                      </div>
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
              <div className={"flex " + (f.reverse ? 'lg:order-1 justify-center lg:justify-start' : 'justify-center lg:justify-end')}>
                <f.MockUI />
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── 5. КАЛЬКУЛЯТОР ───────────────────────────────────────────────── */}
      <section className="py-20">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="bg-white dark:bg-card rounded-3xl border border-gray-100 dark:border-card-border p-8 lg:p-12 shadow-sm dark:shadow-neon-lg"
        >
          <div className="text-center mb-10">
            <Tag text="Калькулятор" />
            <h2 className="text-3xl font-black text-gray-900 dark:text-white">Скільки коштує твій канал?</h2>
            <p className="text-gray-400 mt-3">Введи параметри і дізнайся ринкову вартість за нашою формулою</p>
          </div>
          <Calculator />
        </motion.div>
      </section>

      {/* ── 6. ЯК ЦЕ ПРАЦЮЄ ─────────────────────────────────────────────── */}
      <section className="py-20">
        <div className="text-center mb-12">
          <Tag text="Процес" />
          <h2 className="text-3xl lg:text-4xl font-black text-gray-900 dark:text-white">Як це працює</h2>
          <p className="text-gray-400 mt-3">Прозорий процес від першого кроку до отримання коштів</p>
        </div>
        <div className="grid md:grid-cols-2 gap-8">
          {howItWorks.map(flow => (
            <motion.div
              key={flow.title}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.5 }}
              className={"rounded-2xl border overflow-hidden " + flow.borderCls}
            >
              <div className={"px-6 py-4 " + flow.headerCls}>
                <h3 className={"font-black text-lg " + flow.titleCls}>{flow.title}</h3>
              </div>
              <div className="bg-white dark:bg-card p-6 space-y-5">
                {flow.steps.map((step, i) => (
                  <Step key={step.title} n={i + 1} title={step.title} desc={step.desc} stepCls={flow.stepCls} />
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── 7. CTA ───────────────────────────────────────────────────────── */}
      <section className="py-20">
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          className="bg-white dark:bg-card rounded-3xl border border-gray-100 dark:border-card-border p-12 text-center relative overflow-hidden"
          style={{ boxShadow: '0 0 80px rgba(0,255,136,0.06)' }}
        >
          <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse at center, rgba(0,255,136,0.05) 0%, transparent 65%)' }} />
          <div className="relative">
            <Tag text="Починай зараз" />
            <h2 className="text-4xl lg:text-5xl font-black text-gray-900 dark:text-white mb-4">Готовий почати?</h2>
            <p className="text-gray-400 text-lg mb-8 max-w-md mx-auto">Приєднуйся до тисяч покупців та продавців Telegram-каналів в Україні</p>
            <div className="flex gap-4 justify-center flex-wrap">
              <NavLink to="/catalog" className="bg-accent text-black font-black px-10 py-4 rounded-xl shadow-lg shadow-accent/20 hover:brightness-110 transition-all text-sm uppercase tracking-wider">
                Купити канал
              </NavLink>
              <NavLink to="/auction" className="border border-gray-200 dark:border-card-border text-gray-800 dark:text-white font-bold px-10 py-4 rounded-xl hover:border-accent hover:text-accent dark:hover:border-accent dark:hover:text-accent transition-all text-sm uppercase tracking-wider">
                Аукціони
              </NavLink>
              <NavLink to="/sell" className="border border-gray-200 dark:border-card-border text-gray-800 dark:text-white font-bold px-10 py-4 rounded-xl hover:border-accent hover:text-accent dark:hover:border-accent dark:hover:text-accent transition-all text-sm uppercase tracking-wider">
                Продати канал
              </NavLink>
            </div>
          </div>
        </motion.div>
      </section>
    </div>
  );
};

export default HomePage;