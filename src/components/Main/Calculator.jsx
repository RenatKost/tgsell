import { useState } from 'react';
import { motion } from 'framer-motion';

export const options = [
  { coef: '1.3', label: 'Новини/ЗМІ' },
  { coef: '1.2', label: 'Регіональні' },
  { coef: '1', label: 'Пізнавальні' },
  { coef: '1', label: 'Гумор' },
  { coef: '1', label: 'Жіночі' },
  { coef: '1.2', label: 'Лінгвістика' },
  { coef: '1', label: 'Вульгарні' },
  { coef: '1', label: 'Кулінарія' },
  { coef: '1.1', label: 'Вакансія/Робота' },
  { coef: '2', label: 'Криптовалюта' },
  { coef: '1', label: 'Чоловіче' },
  { coef: '1.3', label: 'Авто/Мото' },
  { coef: '1.2', label: 'Новини 18+' },
  { coef: '1.3', label: 'Політика' },
  { coef: '1', label: 'Медицина' },
  { coef: '1', label: 'Музика' },
  { coef: '1.2', label: 'Подорожі/Країни' },
  { coef: '1.7', label: 'Бізнес' },
  { coef: '1.7', label: 'ІТ/Додатки' },
  { coef: '1.4', label: 'Дизайн' },
  { coef: '1.5', label: 'Авторські' },
  { coef: '1', label: 'Історичні' },
  { coef: '1', label: 'Спорт' },
  { coef: '1', label: 'Товари/Магазини' },
  { coef: '1', label: 'Кіно/Мультфільми' },
  { coef: '1.8', label: 'Інвестиції/Акції' },
  { coef: '1', label: 'Блогери' },
  { coef: '1', label: 'Гороскопи' },
  { coef: '1', label: 'Фотографії' },
  { coef: '1', label: 'Ігри' },
  { coef: '1', label: 'Тварини' },
  { coef: '1', label: 'Цитати' },
  { coef: '1', label: 'Аніме' },
  { coef: '1.7', label: 'Нерухомість' },
  { coef: '1', label: 'Релігія' },
  { coef: '1.7', label: 'Нейромережі' },
  { coef: '1', label: 'Щоу бізнес' },
  { coef: '1', label: 'Мистецтво' },
  { coef: '1', label: 'Інше' },
];

const trafficItems = [
  { coef: '1', label: 'Telegram' },
  { coef: '0.5', label: 'ТікTok' },
  { coef: '1', label: 'Meta' },
  { coef: '1', label: 'Інше' },
];

const inputCls = "w-full bg-white dark:bg-card-inner border border-gray-200 dark:border-card-border rounded-xl px-4 py-3 text-sm text-gray-800 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 focus:outline-none focus:border-accent dark:focus:border-accent transition-colors";
const labelCls = "block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5";

const Calculator = () => {
  const [categoryCoef, setCategoryCoef] = useState(0);
  const [trafficCoef, setTrafficCoef] = useState(0);
  const [subscribers, setSubscribers] = useState(0);
  const [applications, setApplications] = useState(0);
  const [income, setIncome] = useState(0);
  const [reach, setReach] = useState(0);

  const handleCategoryChange = e => {
    const selected = options.find(o => o.label === e.target.value);
    setCategoryCoef(parseFloat(selected?.coef || 0));
  };
  const handleTrafficChange = e => {
    const selected = trafficItems.find(o => o.label === e.target.value);
    setTrafficCoef(parseFloat(selected?.coef || 0));
  };
  const n = e => parseFloat(e.target.value) || 0;

  const calculateTotal = () => {
    const total =
      3 * subscribers * categoryCoef * trafficCoef +
      applications * categoryCoef * trafficCoef +
      income * categoryCoef * trafficCoef +
      reach * 0.25 * categoryCoef * trafficCoef +
      income * 3;
    return isNaN(total) ? 0 : Math.round(total);
  };

  const formatCurrency = num => new Intl.NumberFormat('uk-UA').format(num) + ' USDT';
  const total = calculateTotal();

  return (
    <div>
      <div className="grid sm:grid-cols-2 gap-4 mb-6">
        <div>
          <label className={labelCls}>Категорія</label>
          <select className={inputCls} defaultValue="placeholder" onChange={handleCategoryChange}>
            <option value="placeholder" disabled hidden>Виберіть категорію</option>
            {options.map(o => <option key={o.label}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Джерело трафіку</label>
          <select className={inputCls} defaultValue="placeholder" onChange={handleTrafficChange}>
            <option value="placeholder" disabled hidden>Виберіть трафік</option>
            {trafficItems.map(o => <option key={o.label}>{o.label}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Підписників</label>
          <input className={inputCls} type="number" placeholder="наприклад 50 000" onChange={e => setSubscribers(n(e))} />
        </div>
        <div>
          <label className={labelCls}>Заявок на місяць</label>
          <input className={inputCls} type="number" placeholder="наприклад 120" onChange={e => setApplications(n(e))} />
        </div>
        <div>
          <label className={labelCls}>Місячний дохід (USDT)</label>
          <input className={inputCls} type="number" placeholder="наприклад 500" onChange={e => setIncome(n(e))} />
        </div>
        <div>
          <label className={labelCls}>Охоплення (перегляди)</label>
          <input className={inputCls} type="number" placeholder="наприклад 10 000" onChange={e => setReach(n(e))} />
        </div>
      </div>
      <div className="bg-card-inner rounded-2xl border border-card-border p-5 flex items-center justify-between">
        <div>
          <p className="text-xs text-gray-400 mb-1">Орієнтовна вартість каналу</p>
          <motion.p
            key={total}
            initial={{ scale: 0.92, opacity: 0.4 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.3 }}
            className="text-3xl font-black text-accent"
          >
            {formatCurrency(total)}
          </motion.p>
        </div>
        <div className="text-right hidden sm:block">
          <p className="text-[11px] text-gray-500 leading-relaxed">*Кінцева вартість<br />визначається продавцем</p>
        </div>
      </div>
    </div>
  );
};

export default Calculator;