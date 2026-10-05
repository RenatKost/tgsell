import { motion } from 'framer-motion';

const contacts = [
  {
    title: 'Канал біржі',
    label: '@tgsell_exchange',
    href: 'https://t.me/tgsell_exchange',
    hint: 'Новини та оголошення TgSell',
    icon: 'tg',
  },
  {
    title: 'Бот авторизації',
    label: '@tgsell_auth_bot',
    href: 'https://t.me/tgsell_auth_bot',
    hint: 'Вхід на платформу через Telegram',
    icon: 'bot',
  },
  {
    title: 'Підтримка (email)',
    label: 'tgsell.support@gmail.com',
    href: 'mailto:tgsell.support@gmail.com',
    hint: 'Питання щодо угод і акаунту',
    icon: 'email',
  },
  {
    title: 'Підтримка 24/7',
    label: '@tgsell_support_bot',
    href: 'https://t.me/tgsell_support_bot',
    hint: 'Питання користувачів, угоди, акаунт',
    icon: 'admin',
  },
  {
    title: 'Instagram',
    label: 'instagram.com/tgsell.me',
    href: 'https://instagram.com/tgsell.me',
    hint: 'Соцмережі TgSell',
    icon: 'ig',
  },
];

const Icon = ({ type }) => {
  const wrap = 'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0';
  if (type === 'email') {
    return (
      <span className={`${wrap} bg-gray-100 dark:bg-card-inner`}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="3" y="5" width="18" height="14" rx="2" stroke="#9ca3af" strokeWidth="1.5"/>
          <path d="M3 7l9 6 9-6" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      </span>
    );
  }
  if (type === 'ig') {
    return (
      <span className={`${wrap} bg-pink-500/10`}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="5" stroke="#ec4899" strokeWidth="1.5"/>
          <circle cx="12" cy="12" r="4" stroke="#ec4899" strokeWidth="1.5"/>
          <circle cx="17.5" cy="6.5" r="1" fill="#ec4899"/>
        </svg>
      </span>
    );
  }
  return (
    <span className={`${wrap} bg-cyan-400/10`}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M21.8 3.4L2.7 11.2c-1.3.5-1.3 1.3-.2 1.6l4.8 1.5 11.1-7c.5-.3 1 0 .6.4L9.9 16.1v3.2c0 .9 1.1 1.2 1.6.6l2.3-2.2 4.5 3.3c.8.5 1.4.2 1.6-.7L22.7 4.6c.3-1.3-.4-1.8-1-1.2h.1z" fill="#22d3ee"/>
      </svg>
    </span>
  );
};

const ContactsPage = () => (
  <motion.div
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4 }}
    className="py-12 max-w-3xl mx-auto"
  >
    <div className="mb-10">
      <span className="inline-block bg-cyan-400/10 border border-cyan-400/20 text-cyan-400 text-xs font-bold uppercase tracking-widest px-3 py-1 rounded-full mb-3">Звʼязок</span>
      <h1 className="text-3xl font-black text-gray-900 dark:text-white mb-2">Контакти</h1>
      <p className="text-sm text-gray-400">Офіційні канали звʼязку TgSell</p>
    </div>

    <div className="bg-white dark:bg-card rounded-2xl border border-gray-100 dark:border-card-border p-6 sm:p-8 shadow-sm dark:shadow-neon">
      <ul className="space-y-3">
        {contacts.map((c) => (
          <li key={c.href}>
            <a
              href={c.href}
              target={c.href.startsWith('mailto:') ? undefined : '_blank'}
              rel={c.href.startsWith('mailto:') ? undefined : 'noopener noreferrer'}
              className="flex items-center gap-4 p-4 rounded-xl border border-gray-100 dark:border-card-border hover:border-accent/40 hover:bg-accent/5 transition-all group"
            >
              <Icon type={c.icon} />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-0.5">{c.title}</p>
                <p className="text-sm font-semibold text-gray-900 dark:text-white group-hover:text-accent transition-colors truncate">{c.label}</p>
                <p className="text-xs text-gray-500 mt-0.5">{c.hint}</p>
              </div>
              <span className="text-gray-300 group-hover:text-accent transition-colors text-lg flex-shrink-0">→</span>
            </a>
          </li>
        ))}
      </ul>
    </div>
  </motion.div>
);

export default ContactsPage;
