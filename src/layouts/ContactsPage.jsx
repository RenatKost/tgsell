import { Send, Bot, Mail, Headphones, MessageCircle, Sparkles, ArrowUpRight } from 'lucide-react';
import { SOCIAL_LINKS } from '../components/SocialLinks';
import useReveal from '../hooks/useReveal';
import './escrow.css';
import './premium.css';
import './contacts.css';

const contacts = [
  {
    title: 'Підтримка 24/7',
    label: '@tgsell_support_bot',
    href: 'https://t.me/tgsell_support_bot',
    hint: 'Питання користувачів, угоди, акаунт',
    icon: Headphones,
    color: '0, 255, 136',
    main: true,
  },
  {
    title: 'Канал біржі',
    label: '@tgsell_exchange',
    href: 'https://t.me/tgsell_exchange',
    hint: 'Новини та оголошення TgSell',
    icon: Send,
    color: '34, 158, 217',
  },
  {
    title: 'Бот авторизації',
    label: '@tgsell_auth_bot',
    href: 'https://t.me/tgsell_auth_bot',
    hint: 'Вхід на платформу через Telegram',
    icon: Bot,
    color: '139, 92, 246',
  },
  {
    title: 'Підтримка (email)',
    label: 'tgsell.support@gmail.com',
    href: 'mailto:tgsell.support@gmail.com',
    hint: 'Питання щодо угод і акаунту',
    icon: Mail,
    color: '245, 158, 11',
  },
];

const ext = (href) => (href.startsWith('mailto:') ? {} : { target: '_blank', rel: 'noopener noreferrer' });

const ContactCard = ({ c, i }) => {
  const Icon = c.icon;
  return (
    <li className='esc-reveal' style={{ '--d': `${i * 80}ms` }}>
      <a
        href={c.href}
        {...ext(c.href)}
        className={`ctc-card esc-card esc-lift group flex h-full flex-col gap-4 p-5 sm:p-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60${c.main ? ' ctc-main prm-glow' : ''}`}
        style={{ '--c': c.color }}
      >
        <div className='flex items-start gap-4'>
          <span className='ctc-icon' aria-hidden='true'><Icon className='w-6 h-6' strokeWidth={1.9} /></span>
          <div className='min-w-0 flex-1'>
            <p className='flex flex-wrap items-center gap-2 text-xs font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400'>
              {c.title}
              {c.main && <span className='ctc-pill'>24/7</span>}
            </p>
            <p className='mt-1 text-base sm:text-lg font-semibold text-gray-900 dark:text-white break-all'>{c.label}</p>
            <p className='mt-1 text-sm text-gray-500 dark:text-gray-400'>{c.hint}</p>
          </div>
        </div>
        <span className={`esc-btn-ghost mt-auto inline-flex items-center justify-center gap-2 self-start rounded-xl px-4 py-2.5 min-h-[44px] text-sm font-bold border ${c.main ? 'bg-accent text-black border-accent' : 'border-gray-300 dark:border-card-border text-gray-800 dark:text-gray-100 group-hover:border-accent/50'}`}>
          <MessageCircle className='w-4 h-4' aria-hidden='true' />Написати<ArrowUpRight className='w-4 h-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5' aria-hidden='true' />
        </span>
      </a>
    </li>
  );
};

const ContactsPage = () => {
  useReveal();
  return (
    <main className='esc-page esc-bg-short relative overflow-x-clip'>
      <div className='esc-bg' aria-hidden='true'><span className='esc-grid' /><span className='esc-blob esc-blob-1' /><span className='esc-blob esc-blob-2' /><span className='esc-blob esc-blob-3' /></div>
      <div className='relative max-w-4xl mx-auto px-0 sm:px-4 pt-24 md:pt-32 pb-16 space-y-10 sm:space-y-12'>
        <header className='text-center'>
          <div className='esc-shield mx-auto mb-6' aria-hidden='true'>
            <span className='esc-shield-ring' />
            <MessageCircle className='relative w-10 h-10 sm:w-12 sm:h-12 text-accent' strokeWidth={1.75} />
          </div>
          <p data-qa='badge' className='inline-flex items-center gap-1.5 text-[11px] sm:text-xs uppercase tracking-[0.18em] text-accent/90 font-semibold mb-3'><Sparkles className='w-3.5 h-3.5' aria-hidden='true' />Звʼязок</p>
          <h1 className='esc-title text-[2rem] leading-[1.1] sm:text-5xl font-extrabold tracking-tight'>Контакти</h1>
          <p className='mt-4 text-[15px] sm:text-lg text-gray-600 dark:text-gray-400'>Офіційні канали звʼязку TgSell</p>
        </header>

        <ul className='grid gap-4 md:grid-cols-2'>
          {contacts.map((c, i) => <ContactCard key={c.href} c={c} i={i} />)}
        </ul>

        <section className='esc-reveal' aria-labelledby='ctc-social'>
          <div className='esc-card p-5 sm:p-6'>
            <h2 id='ctc-social' className='text-xs font-black uppercase tracking-widest text-gray-500 dark:text-gray-400 mb-4'>Соцмережі та боти</h2>
            <nav aria-label='Соцмережі TgSell' data-qa='social'>
              <ul className='ctc-social grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5'>
                {SOCIAL_LINKS.map((s) => (
                  <li key={s.key}>
                    <a href={s.href} target='_blank' rel='noopener noreferrer' aria-label={s.aria} title={s.aria}
                      className={`ctc-tile group flex items-center justify-center gap-2 min-h-12 px-3 rounded-xl border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/60${s.main ? ' is-main' : ''}`}>
                      <span className='flex-shrink-0'>{s.icon}</span>
                      <span className='text-sm font-semibold whitespace-nowrap'>{s.label}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </section>
      </div>
    </main>
  );
};

export default ContactsPage;
