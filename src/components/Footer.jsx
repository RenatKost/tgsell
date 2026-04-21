import { NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';

const Logo = () => (
  <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
    <rect width="32" height="32" rx="8" fill="#00FF88" fillOpacity=".12"/>
    <path d="M8 22l6-12 4 8 3-5 3 9" stroke="#00FF88" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const TgIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M21.8 3.4L2.7 11.2c-1.3.5-1.3 1.3-.2 1.6l4.8 1.5 11.1-7c.5-.3 1 0 .6.4L9.9 16.1v3.2c0 .9 1.1 1.2 1.6.6l2.3-2.2 4.5 3.3c.8.5 1.4.2 1.6-.7L22.7 4.6c.3-1.3-.4-1.8-1-1.2h.1z" fill="#22d3ee"/>
  </svg>
);

const EmailIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="3" y="5" width="18" height="14" rx="2" stroke="#9ca3af" strokeWidth="1.5"/>
    <path d="M3 7l9 6 9-6" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
);

const cols = [
  {
    title: 'Покупцям',
    links: [
      { to: '/catalog', label: 'Каталог каналів' },
      { to: '/auction', label: 'Аукціони' },
      { to: '/#calculator', label: 'Калькулятор ціни' },
    ],
  },
  {
    title: 'Продавцям',
    links: [
      { to: '/sell', label: 'Виставити канал' },
      { to: '/#how', label: 'Як це працює' },
      { to: '/#earn', label: 'Як заробити' },
    ],
  },
  {
    title: 'Компанія',
    links: [
      { to: '/privacy', label: 'Політика конфіденційності' },
      { to: '/oferta', label: 'Публічна оферта' },
      { to: '/cabinet', label: 'Особистий кабінет' },
    ],
  },
];

const Footer = () => {
  const year = new Date().getFullYear();
  return (
    <footer className="mt-20 bg-white dark:bg-card border-t border-gray-100 dark:border-card-border">
      {/* Top neon line */}
      <motion.div
        className="h-px w-full"
        style={{ background: 'linear-gradient(90deg, transparent 0%, #00FF88 50%, transparent 100%)' }}
        animate={{ opacity: [0.15, 0.5, 0.15] }}
        transition={{ repeat: Infinity, duration: 4, ease: 'easeInOut' }}
      />

      <div className="max-w-7xl mx-auto px-4 md:px-8 pt-12 pb-8">
        {/* Main grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-8 mb-12">

          {/* Brand col */}
          <div className="col-span-2 lg:col-span-2">
            <NavLink to="/" className="flex items-center gap-2.5 mb-4 w-fit">
              <Logo />
              <span className="text-xl font-black text-gray-900 dark:text-white tracking-tight">TgSell</span>
            </NavLink>
            <p className="text-sm text-gray-500 dark:text-gray-400 leading-relaxed mb-6 max-w-xs">
              Перша українська біржа Telegram-каналів. Безпечні угоди з ескроу-захистом, AI-аналіз та аукціони в реальному часі.
            </p>
            <div className="flex flex-col gap-2.5">
              <a
                href="https://t.me/renat_kos"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2.5 group w-fit"
              >
                <span className="w-7 h-7 rounded-lg bg-cyan-400/10 flex items-center justify-center group-hover:bg-cyan-400/20 transition-colors">
                  <TgIcon />
                </span>
                <span className="text-sm text-gray-500 dark:text-gray-400 group-hover:text-cyan-400 transition-colors">@renat_kos</span>
              </a>
              <a
                href="mailto:tgsell.support@gmail.com"
                className="flex items-center gap-2.5 group w-fit"
              >
                <span className="w-7 h-7 rounded-lg bg-gray-100 dark:bg-card-inner flex items-center justify-center group-hover:bg-accent/10 transition-colors">
                  <EmailIcon />
                </span>
                <span className="text-sm text-gray-500 dark:text-gray-400 group-hover:text-accent transition-colors">tgsell.support@gmail.com</span>
              </a>
            </div>
          </div>

          {/* Link cols */}
          {cols.map(col => (
            <div key={col.title}>
              <p className="text-xs font-black uppercase tracking-widest text-gray-400 mb-4">{col.title}</p>
              <ul className="space-y-2.5">
                {col.links.map(({ to, label }) => (
                  <li key={label}>
                    <NavLink
                      to={to}
                      className="text-sm text-gray-500 dark:text-gray-400 hover:text-accent dark:hover:text-accent transition-colors"
                    >
                      {label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Stats strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 py-6 border-y border-gray-100 dark:border-card-border mb-8">
          {[
            { value: '500+', label: 'Каналів у продажу', color: 'text-accent' },
            { value: '1 200+', label: 'Успішних угод', color: 'text-violet-400' },
            { value: '$2.4M+', label: 'Обіг USDT', color: 'text-orange-400' },
            { value: '3%', label: 'Комісія платформи', color: 'text-cyan-400' },
          ].map(({ value, label, color }) => (
            <div key={label} className="text-center">
              <p className={"text-xl font-black " + color}>{value}</p>
              <p className="text-xs text-gray-400 mt-0.5">{label}</p>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-gray-400">
            © {year} TgSell. Всі права захищені.
          </p>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" />
            <span className="text-xs text-gray-400">Угоди захищені ескроу USDT (TRC-20)</span>
          </div>
          <div className="flex gap-4">
            <NavLink to="/privacy" className="text-xs text-gray-400 hover:text-accent transition-colors">Конфіденційність</NavLink>
            <NavLink to="/oferta" className="text-xs text-gray-400 hover:text-accent transition-colors">Оферта</NavLink>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;