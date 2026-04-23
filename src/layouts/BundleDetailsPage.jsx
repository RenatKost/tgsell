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
      <div className="max-w-5xl mx-auto px-4 py-10">

        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm text-gray-500 mb-6">
          <Link to="/catalog" className="hover:text-accent">Каталог</Link>
          <span>/</span>
          <span className="text-accent">📡 Сітки каналів</span>
          <span>/</span>
          <span className="text-white">{bundle.name}</span>
        </div>

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
              { label: '∑ Доходу / міс', value: stats.total_monthly_income ? fmt(stats.total_monthly_income) + ' $' : '—' },
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
          <div className="bg-card border border-card-border rounded-xl p-6 shadow-neon">
            <h2 className="text-lg font-bold mb-3">Що входить у продаж</h2>
            <p className="text-gray-300 text-sm whitespace-pre-wrap">{bundle.resources}</p>
          </div>
        )}
      </div>
    </div>
  );
}
