import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { bundlesAPI, dealsAPI } from '../services/api';
import { useAppContext } from '../context/AppContext';

function fmt(n) {
  if (!n) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

export default function BundleDetailsPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isAuthenticated, user } = useAppContext();
  const [bundle, setBundle] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [buying, setBuying] = useState(false);
  const [buyError, setBuyError] = useState('');
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const [bRes, sRes] = await Promise.all([
          bundlesAPI.getById(id),
          bundlesAPI.getStats(id),
        ]);
        setBundle(bRes.data);
        setStats(sRes.data);
      } catch {
        setError('Сітку не знайдено');
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const handleBuy = async () => {
    if (!isAuthenticated) { navigate('/'); return; }
    setBuying(true);
    setBuyError('');
    try {
      const res = await dealsAPI.create(null, Number(id));
      navigate(`/deal/${res.data.id}`);
    } catch (e) {
      const detail = e.response?.data?.detail;
      setBuyError(typeof detail === 'string' ? detail : 'Помилка при створенні угоди');
      setBuying(false);
    }
  };

  const handleAiAnalysis = async () => {
    setAiLoading(true);
    setAiError('');
    try {
      const res = await bundlesAPI.getAiAnalysis(id);
      setAiAnalysis(res.data);
    } catch (e) {
      const detail = e.response?.data?.detail;
      setAiError(typeof detail === 'string' ? detail : 'Помилка AI аналізу');
    } finally {
      setAiLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-page flex items-center justify-center">
        <div className="text-accent animate-pulse">Завантаження...</div>
      </div>
    );
  }

  if (error || !bundle) {
    return (
      <div className="min-h-screen bg-page flex items-center justify-center text-gray-400">
        {error || 'Сітку не знайдено'}
      </div>
    );
  }

  const channels = bundle.channels || [];
  const isSeller = user?.id === bundle.seller_id;
  const isSold = bundle.status === 'sold';

  return (
    <div className="min-h-screen bg-page text-white">
      <div className="max-w-5xl mx-auto px-4 pt-24 pb-16">

        {/* Hero */}
        <div className="bg-card border border-card-border rounded-xl p-6 shadow-neon mb-6">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-3">
                <span className="inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-accent/15 text-accent border border-accent/30">
                  📡 СІТКА · {bundle.channel_count} каналів
                </span>
                {bundle.category && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-card-inner text-gray-400 border border-card-border">
                    {bundle.category}
                  </span>
                )}
                {isSold && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-red-900/40 text-red-400 border border-red-800">
                    ПРОДАНО
                  </span>
                )}
              </div>
              <h1 className="text-3xl font-black text-white mb-3">{bundle.name}</h1>
              {bundle.description && (
                <p className="text-gray-400 text-sm leading-relaxed">{bundle.description}</p>
              )}
            </div>

            {/* Price + CTA */}
            <div className="md:w-72 bg-card-inner rounded-xl border border-card-border p-5 flex-shrink-0">
              <div className="text-4xl font-black text-accent mb-1">{bundle.price}</div>
              <div className="text-gray-400 text-sm mb-4">USDT за всю сітку</div>
              {bundle.monthly_income > 0 && (
                <div className="text-sm text-gray-400 mb-4">
                  Місячний дохід: <span className="text-white font-semibold">{bundle.monthly_income} USDT</span>
                </div>
              )}
              {buyError && (
                <div className="text-red-400 text-xs mb-3">{buyError}</div>
              )}
              {!isSold && !isSeller && (
                <button onClick={handleBuy} disabled={buying}
                  className="w-full py-3 rounded-xl font-bold bg-accent text-black shadow-lg shadow-accent/30 hover:brightness-110 transition-all disabled:opacity-60">
                  {buying ? 'Зачекайте...' : '💸 Купити всю сітку'}
                </button>
              )}
              {isSold && (
                <div className="text-center text-gray-500 text-sm py-3">Сітку продано</div>
              )}
              {isSeller && !isSold && (
                <div className="text-center text-gray-400 text-sm py-3">Це ваша сітка</div>
              )}
            </div>
          </div>
        </div>

        {/* Aggregate stats */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            {[
              { label: '∑ Підписників', value: fmt(stats.total_subscribers) },
              { label: 'Середній ER', value: stats.avg_er != null ? stats.avg_er.toFixed(1) + '%' : '—' },
              { label: '∑ Доходу / міс', value: stats.total_monthly_income != null ? fmt(stats.total_monthly_income) + ' USDT' : '—' },
              { label: 'Каналів', value: stats.channel_count },
            ].map(m => (
              <div key={m.label} className="bg-card border border-card-border rounded-xl p-4 shadow-neon text-center">
                <div className="text-2xl font-black text-accent">{m.value}</div>
                <div className="text-xs text-gray-500 mt-1">{m.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Channels grid */}
        <div className="mb-6">
          <h2 className="text-lg font-bold mb-4">Канали сітки</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {channels.map(ch => (
              <Link key={ch.id} to={`/channel/${ch.id}`}
                className="bg-card border border-card-border rounded-xl p-4 hover:border-accent/30 hover:shadow-neon transition-all group flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-card-inner border border-card-border flex-shrink-0 overflow-hidden">
                  {ch.avatar_url
                    ? <img src={ch.avatar_url} alt={ch.channel_name} className="w-full h-full object-cover" />
                    : <div className="w-full h-full flex items-center justify-center text-accent text-lg font-bold">
                        {(ch.channel_name || '?')[0].toUpperCase()}
                      </div>
                  }
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-white group-hover:text-accent transition-colors truncate">
                    {ch.channel_name}
                  </div>
                  <div className="text-xs text-gray-500 flex gap-3 mt-0.5">
                    {ch.subscribers_count != null && <span>{fmt(ch.subscribers_count)} підп.</span>}
                    {ch.er != null && <span>ER {ch.er.toFixed(1)}%</span>}
                  </div>
                </div>
                <svg className="w-4 h-4 text-gray-600 group-hover:text-accent flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </Link>
            ))}
          </div>
        </div>

        {/* Resources */}
        {bundle.resources && (
          <div className="bg-card border border-card-border rounded-xl p-6 shadow-neon mb-6">
            <h2 className="text-lg font-bold mb-3">Що входить у продаж</h2>
            <p className="text-gray-300 text-sm whitespace-pre-wrap">{bundle.resources}</p>
          </div>
        )}

        {/* AI Analysis */}
        <div className="bg-card border border-card-border rounded-xl p-6 shadow-neon">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-bold">🤖 AI аналіз сітки</h2>
            {!aiAnalysis && (
              <button
                onClick={handleAiAnalysis}
                disabled={aiLoading}
                className="px-4 py-2 rounded-lg bg-accent text-black text-sm font-bold shadow-lg shadow-accent/30 hover:brightness-110 transition-all disabled:opacity-60"
              >
                {aiLoading ? 'Аналізую...' : 'Запустити аналіз'}
              </button>
            )}
          </div>

          {aiError && <div className="text-red-400 text-sm mb-3">{aiError}</div>}

          {aiLoading && (
            <div className="flex items-center gap-3 text-gray-400 text-sm py-6 justify-center">
              <div className="w-5 h-5 border-2 border-accent/40 border-t-accent rounded-full animate-spin" />
              Groq AI аналізує сітку каналів...
            </div>
          )}

          {aiAnalysis && !aiAnalysis.error && (() => {
            const verdictColor = aiAnalysis.verdict === 'buy' ? 'text-accent border-accent/40 bg-accent/10'
              : aiAnalysis.verdict === 'avoid' ? 'text-red-400 border-red-400/40 bg-red-400/10'
              : 'text-yellow-400 border-yellow-400/40 bg-yellow-400/10';
            const verdictLabel = aiAnalysis.verdict === 'buy' ? '✅ Купувати'
              : aiAnalysis.verdict === 'avoid' ? '❌ Уникати' : '⏳ Чекати';
            return (
              <div className="space-y-5">
                {/* Verdict + Score */}
                <div className="flex items-center gap-4 flex-wrap">
                  <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-sm font-bold ${verdictColor}`}>
                    {verdictLabel}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-gray-500 text-xs">Рейтинг:</span>
                    <span className="text-2xl font-black text-accent">{aiAnalysis.score}</span>
                    <span className="text-gray-500 text-xs">/100</span>
                  </div>
                  {aiAnalysis.roi_months && (
                    <span className="text-xs text-gray-400">Окупність: <span className="text-white font-semibold">{aiAnalysis.roi_months} міс.</span></span>
                  )}
                </div>

                {/* Summary */}
                <p className="text-gray-300 text-sm leading-relaxed">{aiAnalysis.summary}</p>

                {/* Verdict reason */}
                {aiAnalysis.verdict_reason && (
                  <div className={`rounded-lg border p-3 text-sm ${verdictColor}`}>
                    {aiAnalysis.verdict_reason}
                  </div>
                )}

                {/* Income + Audience */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {(aiAnalysis.total_potential_income_min || aiAnalysis.total_potential_income_max) && (
                    <div className="bg-card-inner rounded-lg border border-card-border p-4">
                      <div className="text-xs text-gray-500 mb-1">Потенційний дохід / міс</div>
                      <div className="text-accent font-black text-xl">
                        {aiAnalysis.total_potential_income_min}–{aiAnalysis.total_potential_income_max} <span className="text-sm font-normal text-gray-400">USDT</span>
                      </div>
                    </div>
                  )}
                  {aiAnalysis.fair_price_estimate && (
                    <div className="bg-card-inner rounded-lg border border-card-border p-4">
                      <div className="text-xs text-gray-500 mb-1">Справедлива ціна</div>
                      <div className="text-sm text-white">{aiAnalysis.fair_price_estimate}</div>
                    </div>
                  )}
                </div>

                {/* Synergy */}
                {aiAnalysis.synergy && (
                  <div>
                    <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">Синергія каналів</div>
                    <p className="text-gray-300 text-sm">{aiAnalysis.synergy}</p>
                  </div>
                )}

                {/* Audience */}
                {aiAnalysis.audience_quality && (
                  <div>
                    <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">Якість аудиторії</div>
                    <p className="text-gray-300 text-sm">{aiAnalysis.audience_quality}</p>
                  </div>
                )}

                {/* Risks + Opportunities */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {aiAnalysis.risks?.length > 0 && (
                    <div>
                      <div className="text-xs text-red-400 uppercase tracking-wide mb-2">Ризики</div>
                      <ul className="space-y-1.5">
                        {aiAnalysis.risks.map((r, i) => (
                          <li key={i} className="text-xs text-gray-400 flex gap-2">
                            <span className="text-red-400 flex-shrink-0">▸</span>{r}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {aiAnalysis.opportunities?.length > 0 && (
                    <div>
                      <div className="text-xs text-accent uppercase tracking-wide mb-2">Можливості</div>
                      <ul className="space-y-1.5">
                        {aiAnalysis.opportunities.map((o, i) => (
                          <li key={i} className="text-xs text-gray-400 flex gap-2">
                            <span className="text-accent flex-shrink-0">▸</span>{o}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}

          {aiAnalysis?.error && (
            <div className="text-red-400 text-sm">{aiAnalysis.detail || 'Помилка AI аналізу'}</div>
          )}

          {!aiAnalysis && !aiLoading && (
            <p className="text-gray-500 text-sm">Натисніть кнопку щоб отримати AI-оцінку інвестиційної привабливості цієї сітки.</p>
          )}
        </div>
      </div>
    </div>
  );
}
