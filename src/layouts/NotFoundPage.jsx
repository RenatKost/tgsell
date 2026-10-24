import { NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';
import './escrow.css';
import './premium.css';
import './public.css';

const NotFoundPage = () => (
  <motion.div
    initial={{ opacity: 0, y: 16 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.35 }}
    className="esc-page prm-pub relative overflow-x-clip pt-32 pb-24 flex flex-col items-center justify-center text-center px-4"
  >
    <div className="esc-bg esc-bg-short" aria-hidden="true"><span className="esc-grid" /><span className="esc-blob esc-blob-1" /><span className="esc-blob esc-blob-2" /></div>
    <p className="esc-title text-7xl sm:text-8xl font-black tracking-tighter mb-2">404</p>
    <h1 className="text-2xl font-black text-gray-900 dark:text-white mb-2">Сторінку не знайдено</h1>
    <p className="text-sm text-gray-500 dark:text-gray-400 mb-8 max-w-md">
      Такої адреси на TgSell немає. Перевірте URL або поверніться на головну.
    </p>
    <div className="flex flex-wrap gap-3 justify-center">
      <NavLink
        to="/"
        className="font-semibold bg-gradient-to-r from-emerald-500 to-green-500 text-white px-6 py-3 rounded-xl hover:shadow-lg hover:shadow-green-500/25 transition-all duration-200"
      >
        На головну
      </NavLink>
      <NavLink
        to="/catalog"
        className="font-semibold text-blue-500 border border-blue-500/30 hover:bg-blue-500 hover:text-white px-6 py-3 rounded-xl transition-all duration-200"
      >
        Каталог
      </NavLink>
      <NavLink
        to="/contacts"
        className="font-semibold text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-slate-600 hover:border-accent hover:text-accent px-6 py-3 rounded-xl transition-all duration-200"
      >
        Контакти
      </NavLink>
    </div>
  </motion.div>
);

export default NotFoundPage;
