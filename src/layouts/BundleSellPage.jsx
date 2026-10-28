import { MAX_PRICE_USDT, MAX_PRICE_HINT, fmtNum } from '../utils/money';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { bundlesAPI } from '../services/api';
import { utmPayload } from '../utils/utm';

const CATEGORIES = [
  'Криптовалюти', 'Фінанси', 'Новини', 'Бізнес', 'Розваги',
  'Технології', 'Освіта', 'Спорт', 'Lifestyle', 'Інше',
];

function StepIndicator({ step }) {
  const steps = ['Про сітку', 'Канали', 'Підсумок'];
  return (
    <div className="flex items-center justify-center gap-1 sm:gap-2 mb-8 max-w-full">
      {steps.map((label, i) => {
        const idx = i + 1;
        const active = idx === step;
        const done = idx < step;
        return (
          <div key={idx} className="flex items-center gap-1 sm:gap-2 min-w-0">
            <div className={`w-7 h-7 sm:w-8 sm:h-8 shrink-0 rounded-full flex items-center justify-center text-sm font-bold border-2 transition-all
              ${active ? 'border-accent bg-accent text-black' : done ? 'border-accent/60 bg-accent/20 text-accent' : 'border-card-border bg-card-inner text-gray-500'}`}>
              {done ? '✓' : idx}
            </div>
            <span className={`text-xs sm:text-sm whitespace-nowrap ${active ? 'text-white font-medium' : 'text-gray-500'}`}>{label}</span>
            {i < steps.length - 1 && (
              <div className={`w-3 sm:w-10 shrink-0 h-px ${done ? 'bg-accent/60' : 'bg-card-border'}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function BundleSellPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Step 1 state
  const [form, setForm] = useState({
    name: '',
    description: '',
    category: '',
    price: '',
    monthly_income: '',
    resources: '',
  });

  // Step 2 state
  const [links, setLinks] = useState(['', '']);
  // Task 31: per-channel seller-stated balance, aligned with links
  const [balances, setBalances] = useState([{ stars: '', ton: '' }, { stars: '', ton: '' }]);
  const updateBalance = (i, key, val) => {
    setBalances(prev => prev.map((b, idx) => (idx === i ? { ...b, [key]: val } : b)));
  };

  const isInviteLink = (l) => /(^|\/)\+|joinchat\//.test(String(l || '').trim());

  const handleFormChange = (e) => {
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const addLink = () => {
    if (links.length < 20) {
      setLinks(prev => [...prev, '']);
      setBalances(prev => [...prev, { stars: '', ton: '' }]);
    }
  };

  const removeLink = (i) => {
    if (links.length > 2) {
      setLinks(prev => prev.filter((_, idx) => idx !== i));
      setBalances(prev => prev.filter((_, idx) => idx !== i));
    }
  };

  const updateLink = (i, val) => {
    setLinks(prev => prev.map((l, idx) => (idx === i ? val : l)));
  };

  const validateStep1 = () => {
    if (!form.name.trim()) return 'Назва сітки обов\'язкова';
    if (!form.price || isNaN(Number(form.price)) || Number(form.price) <= 0)
      return 'Вкажіть коректну ціну';
    if (Number(form.price) > MAX_PRICE_USDT) return MAX_PRICE_HINT;
    return '';
  };

  const validateStep2 = () => {
    const filled = links.filter(l => l.trim());
    if (filled.length < 2) return 'Додайте щонайменше 2 канали';
    for (const b of balances) {
      if (b.stars !== '' && !/^\d+$/.test(String(b.stars).trim())) return 'Баланс Stars — ціле невідʼємне число';
      const ton = String(b.ton).trim().replace(',', '.');
      if (ton !== '' && (Number.isNaN(Number(ton)) || Number(ton) < 0)) return 'Баланс TON — невідʼємне число';
    }
    return '';
  };

  const handleStep1Next = () => {
    const err = validateStep1();
    if (err) { setError(err); return; }
    setError('');
    setStep(2);
  };

  const handleStep2Next = () => {
    const err = validateStep2();
    if (err) { setError(err); return; }
    setError('');
    setStep(3);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError('');
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || undefined,
        category: form.category || undefined,
        price: Number(form.price),
        monthly_income: form.monthly_income ? Number(form.monthly_income) : undefined,
        resources: form.resources.trim() || undefined,
        channel_links: links.filter(l => l.trim()),
        channel_subscribers: links
          .map((l, i) => ({ l, b: balances[i] || {} }))
          .filter(({ l }) => l.trim())
          .map(({ l, b }) => {
            const n = String(b.subs ?? '').replace(/\D/g, '');
            return isInviteLink(l) && n ? parseInt(n, 10) : null;
          }),
        channel_balances: links
          .map((l, i) => ({ l, b: balances[i] || { stars: '', ton: '' } }))
          .filter(({ l }) => l.trim())
          .map(({ b }) => {
            const stars = String(b.stars).trim();
            const ton = String(b.ton).trim().replace(',', '.');
            return {
              stars_balance: stars === '' ? null : parseInt(stars, 10),
              ton_balance: ton === '' ? null : Number(ton),
            };
          }),
      };
      const res = await bundlesAPI.create({ ...payload, ...utmPayload() });
      navigate('/cabinet', { state: { tab: 'bundles', bundleCreated: res.data.id } });
    } catch (e) {
      const detail = e.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Помилка при створенні сітки');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-page text-white">
      <div className="max-w-2xl mx-auto px-4 pt-24 md:pt-28 pb-12">
        <h1 className="text-3xl font-bold text-center mb-2">
          Продати <span className="text-accent">сітку каналів</span>
        </h1>
        <p className="text-center text-gray-400 mb-8 text-sm">
          Об'єднайте кілька каналів в одну пропозицію для покупців
        </p>

        <StepIndicator step={step} />

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Step 1 — Info */}
        {step === 1 && (
          <div className="bg-card border border-card-border rounded-xl p-6 shadow-neon space-y-4">
            <h2 className="text-lg font-semibold mb-2">Про сітку</h2>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Назва сітки *</label>
              <input name="name" value={form.name} onChange={handleFormChange}
                placeholder="Наприклад: Крипто-медіа UA"
                className="w-full bg-card-inner border border-card-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50" />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Категорія</label>
              <select name="category" value={form.category} onChange={handleFormChange}
                className="w-full bg-card-inner border border-card-border rounded-lg px-4 py-2.5 text-white focus:outline-none focus:border-accent/50">
                <option value="">Оберіть категорію</option>
                {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Ціна продажу (USDT) *</label>
                <input name="price" value={form.price} onChange={handleFormChange}
                  type="number" min="0" max={MAX_PRICE_USDT} title={MAX_PRICE_HINT} placeholder="0"
                  className="w-full bg-card-inner border border-card-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50" />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Місячний дохід (USDT)</label>
                <input name="monthly_income" value={form.monthly_income} onChange={handleFormChange}
                  type="number" min="0" placeholder="0"
                  className="w-full bg-card-inner border border-card-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50" />
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Опис сітки</label>
              <textarea name="description" value={form.description} onChange={handleFormChange}
                rows={3} placeholder="Розкажіть про тематику, аудиторію та переваги сітки..."
                className="w-full bg-card-inner border border-card-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 resize-none" />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Ресурси (доступи, боти, сайти)</label>
              <textarea name="resources" value={form.resources} onChange={handleFormChange}
                rows={2} placeholder="Опишіть, що входить у продаж окрім каналів..."
                className="w-full bg-card-inner border border-card-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 resize-none" />
            </div>

            <button onClick={handleStep1Next}
              className="w-full py-3 rounded-xl font-bold bg-accent text-black shadow-lg shadow-accent/30 hover:brightness-110 transition-all">
              Далі →
            </button>
          </div>
        )}

        {/* Step 2 — Channels */}
        {step === 2 && (
          <div className="bg-card border border-card-border rounded-xl p-6 shadow-neon space-y-4">
            <h2 className="text-lg font-semibold mb-2">Канали сітки</h2>
            <p className="text-sm text-gray-400">Вставте посилання на Telegram-канали (@username або t.me/...)</p>

            {links.map((link, i) => (
              <div key={i} className="space-y-1.5">
                <div className="flex gap-2 items-center">
                  <input value={link} onChange={e => updateLink(i, e.target.value)}
                    placeholder={`Канал ${i + 1} — @username або https://t.me/...`}
                    className="flex-1 bg-card-inner border border-card-border rounded-lg px-4 py-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 text-sm" />
                  {links.length > 2 && (
                    <button onClick={() => removeLink(i)}
                      className="text-red-400 hover:text-red-300 px-2 py-1 text-lg leading-none">×</button>
                  )}
                </div>
                <div className="flex gap-2">
                  <input value={balances[i]?.stars ?? ''} onChange={e => updateBalance(i, 'stars', e.target.value)}
                    inputMode="numeric" placeholder="⭐ Stars (необовʼязково)"
                    className="flex-1 min-w-0 bg-card-inner border border-card-border rounded-lg px-3 py-1.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 text-xs" />
                  <input value={balances[i]?.ton ?? ''} onChange={e => updateBalance(i, 'ton', e.target.value)}
                    inputMode="decimal" placeholder="💎 TON (необовʼязково)"
                    className="flex-1 min-w-0 bg-card-inner border border-card-border rounded-lg px-3 py-1.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 text-xs" />
                </div>
                {isInviteLink(link) && (
                  <input value={balances[i]?.subs ?? ''} onChange={e => updateBalance(i, 'subs', e.target.value)}
                    inputMode="numeric" placeholder="🔒 Закритий канал: кількість підписників (необовʼязково)"
                    className="w-full bg-card-inner border border-card-border rounded-lg px-3 py-1.5 text-white placeholder-gray-600 focus:outline-none focus:border-accent/50 text-xs" />
                )}
              </div>
            ))}
            <p className="text-xs text-gray-500">Баланс каналу в Stars/TON показується як «зі слів продавця» і не впливає на ціну.</p>

            {links.length < 20 && (
              <button onClick={addLink}
                className="text-accent text-sm hover:underline">+ Додати канал</button>
            )}

            <div className="flex gap-3 pt-2">
              <button onClick={() => { setError(''); setStep(1); }}
                className="flex-1 py-3 rounded-xl font-bold border border-card-border text-gray-300 hover:border-accent/40 hover:text-white transition-all">
                ← Назад
              </button>
              <button onClick={handleStep2Next}
                className="flex-1 py-3 rounded-xl font-bold bg-accent text-black shadow-lg shadow-accent/30 hover:brightness-110 transition-all">
                Далі →
              </button>
            </div>
          </div>
        )}

        {/* Step 3 — Summary */}
        {step === 3 && (
          <div className="bg-card border border-card-border rounded-xl p-6 shadow-neon space-y-4">
            <h2 className="text-lg font-semibold mb-2">Підсумок</h2>

            <div className="bg-card-inner rounded-lg p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-400">Назва сітки</span>
                <span className="font-medium text-white">{form.name}</span>
              </div>
              {form.category && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Категорія</span>
                  <span>{form.category}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-400">Ціна</span>
                <span className="text-accent font-bold">{fmtNum(form.price)} USDT</span>
              </div>
              {form.monthly_income && (
                <div className="flex justify-between">
                  <span className="text-gray-400">Місячний дохід</span>
                  <span>{form.monthly_income} USDT</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-400">Каналів</span>
                <span>{links.filter(l => l.trim()).length}</span>
              </div>
            </div>

            <div className="bg-card-inner rounded-lg p-4">
              <p className="text-sm text-gray-400 mb-1">Канали:</p>
              <ul className="space-y-1">
                {links.filter(l => l.trim()).map((l, i) => (
                  <li key={i} className="text-sm text-accent">{l.trim()}</li>
                ))}
              </ul>
            </div>

            <p className="text-xs text-gray-500">
              Після подачі сітка пройде модерацію. Зазвичай це займає до 24 годин.
            </p>

            <div className="flex gap-3 pt-2">
              <button onClick={() => { setError(''); setStep(2); }}
                className="flex-1 py-3 rounded-xl font-bold border border-card-border text-gray-300 hover:border-accent/40 hover:text-white transition-all">
                ← Назад
              </button>
              <button onClick={handleSubmit} disabled={submitting}
                className="flex-1 py-3 rounded-xl font-bold bg-accent text-black shadow-lg shadow-accent/30 hover:brightness-110 transition-all disabled:opacity-60">
                {submitting ? 'Відправляємо...' : '📡 Подати сітку'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
