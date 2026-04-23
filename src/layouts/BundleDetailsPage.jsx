import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import Chart from 'react-apexcharts';
import { bundlesAPI, dealsAPI } from '../services/api';
import { useAppContext } from '../context/AppContext';

function fmt(n) {
  if (n == null) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

function ScoreRing({ score }) {
  const r = 34;
  const circ = 2 * Math.PI * r;
  const dash = ((score || 0) / 100) * circ;
  const color = score >= 65 ? '#00FF88' : score >= 40 ? '#FACC15' : '#F87171';
  return (
    <div className="relative w-20 h-20 flex-shrink-0 flex items-center justify-center">
      <svg className="w-20 h-20 -rotate-90" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r={r} fill="none" stroke="#1A3A2A" strokeWidth="7" />
        <circle cx="40" cy="40" r={r} fill="none" stroke={color} strokeWidth="7"
          strokeDasharray={`${dash} ${circ}`} strokeLinecap="round" />
      </svg>
      <div className="absolute text-center">
        <div className="text-xl font-black leading-none" style={{ color }}>{score}</div>
        <div className="text-[9px] text-gray-600">/100</div>
      </div>
    </div>
  );
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
  const [descExpanded, setDescExpanded] = useState(false);

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

  const handleAiAnalysis = async () => {
    setAiLoading(true);
    setAiError('');
    try {
      const res = await bundlesAPI.getAiAnalysis(id);
      if (res.data?.error) {
        setAiError(res.data.detail || 'Помилка AI аналізу');
      } else {
        setAiAnalysis(res.data);
      }
    } catch (e) {
      if (e.code === 'ECONNABORTED' || e.message?.includes('timeout')) {
        setAiError('AI аналіз перевищив ліміт часу. Натисніть "Спробувати ще раз".');
      } else {
        const detail = e.response?.data?.detail;
        setAiError(typeof detail === 'string' ? detail : 'Не вдалося отримати AI аналіз. Спробуйте ще раз.');
      }
    } finally {
      setAiLoading(false);
    }
  };

  useEffect(() => {
    if (bundle) handleAiAnalysis();
  }, [bundle?.id]);

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
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
          <div className="text-gray-500 text-sm">Завантаження сітки...</div>
        </div>
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

  // Best channel by ER
  const sortedByEr = [...channels].sort((a, b) => (b.er || 0) - (a.er || 0));
  const topChannel = sortedByEr[0];

  // Quick ROI
  const income = bundle.monthly_income || stats?.total_monthly_income;
  const roi = income > 0 ? Math.round(bundle.price / income) : (aiAnalysis?.roi_months || null);

  // ── CHART OPTIONS ──
  const subsLabels = channels.map(c =>
    c.channel_name?.length > 14 ? c.channel_name.slice(0, 14) + '…' : c.channel_name || '?'
  );
  const subsSeries = channels.map(c => c.subscribers_count || 0);
  const CHART_COLORS = ['#00FF88', '#00D4AA', '#00AAFF', '#A78BFA', '#F59E0B', '#F87171'];

  const donutOptions = {
    chart: { type: 'donut', background: 'transparent', toolbar: { show: false } },
    labels: subsLabels,
    colors: CHART_COLORS,
    legend: {
      labels: { colors: '#6B7280' }, position: 'bottom', fontSize: '11px',
      markers: { width: 8, height: 8, radius: 4 }, itemMargin: { horizontal: 6, vertical: 2 },
    },
    dataLabels: { enabled: false },
    plotOptions: {
      pie: {
        donut: {
          size: '72%',
          labels: {
            show: true,
            total: {
              show: true, label: 'Підписників', color: '#6B7280', fontSize: '11px',
              formatter: () => fmt(stats?.total_subscribers),
            },
            value: { color: '#00FF88', fontSize: '16px', fontWeight: 700 },
          },
        },
      },
    },
    stroke: { colors: ['#0D1717'], width: 2 },
    tooltip: { theme: 'dark', y: { formatter: v => `${fmt(v)} підп.` } },
  };

  const erCategories = sortedByEr.map(c =>
    c.channel_name?.length > 14 ? c.channel_name.slice(0, 14) + '…' : c.channel_name || '?'
  );
  const erSeries = [{ name: 'ER %', data: sortedByEr.map(c => parseFloat((c.er || 0).toFixed(2))) }];
  const erOptions = {
    chart: { type: 'bar', background: 'transparent', toolbar: { show: false } },
    plotOptions: {
      bar: { horizontal: true, borderRadius: 4, barHeight: '55%', distributed: true, dataLabels: { position: 'top' } },
    },
    colors: CHART_COLORS,
    dataLabels: {
      enabled: true, formatter: v => v.toFixed(1) + '%',
      style: { colors: ['#9CA3AF'], fontSize: '10px', fontWeight: 600 }, offsetX: 6,
    },
    xaxis: {
      categories: erCategories,
      labels: { style: { colors: '#6B7280', fontSize: '11px' } },
      axisBorder: { color: '#1A3A2A' }, axisTicks: { color: '#1A3A2A' },
    },
    yaxis: { labels: { style: { colors: '#9CA3AF', fontSize: '11px' }, maxWidth: 110 } },
    grid: { borderColor: '#1A3A2A', xaxis: { lines: { show: true } }, yaxis: { lines: { show: false } } },
    legend: { show: false },
    tooltip: { theme: 'dark', y: { formatter: v => v.toFixed(2) + '%' } },
  };

  // AI verdict styles
  const verdictCfg = {
    buy:   { cls: 'text-accent border-accent/40 bg-accent/10',         label: '✅ Купувати' },
    avoid: { cls: 'text-red-400 border-red-400/40 bg-red-900/20',      label: '❌ Уникати'  },
    hold:  { cls: 'text-yellow-400 border-yellow-400/40 bg-yellow-900/20', label: '⏳ Чекати' },
  };
  const vCfg = verdictCfg[aiAnalysis?.verdict] || verdictCfg.hold;

  return (
    <div className="min-h-screen bg-page text-white">
      <div className="max-w-6xl mx-auto px-4 pt-24 pb-16 space-y-5">

        {/* ═══════════ HERO ═══════════ */}
        <div className="bg-card border border-card-border rounded-2xl p-6 shadow-neon-lg">
          <div className="flex flex-col lg:flex-row gap-6">

            {/* Left */}
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2 mb-3">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold px-3 py-1 rounded-full bg-accent/15 text-accent border border-accent/30">
                  📡 СІТКА · {bundle.channel_count} каналів
                </span>
                {bundle.category && (
                  <span className="text-xs px-2.5 py-1 rounded-full bg-card-inner text-gray-400 border border-card-border">
                    {bundle.category}
                  </span>
                )}
                {isSold && (
                  <span className="text-xs px-2.5 py-1 rounded-full bg-red-900/40 text-red-400 border border-red-800">ПРОДАНО</span>
                )}
              </div>
              <h1 className="text-3xl lg:text-4xl font-black text-white mb-3 leading-tight">{bundle.name}</h1>
              {bundle.description && (
                <div>
                  <p className={`text-gray-400 text-sm leading-relaxed ${!descExpanded ? 'line-clamp-3' : ''}`}>
                    {bundle.description}
                  </p>
                  {bundle.description.length > 180 && (
                    <button onClick={() => setDescExpanded(v => !v)}
                      className="text-accent text-xs mt-1 hover:underline">
                      {descExpanded ? 'Згорнути' : 'Читати далі'}
                    </button>
                  )}
                </div>
              )}
              {roi && (
                <div className="mt-4 inline-flex items-center gap-2 bg-accent/10 border border-accent/20 rounded-lg px-3 py-2">
                  <span className="text-accent text-sm font-bold">⚡ Окупність ~{roi} міс.</span>
                  {income > 0 && <span className="text-gray-500 text-xs">при {fmt(income)} USDT/міс</span>}
                </div>
              )}
            </div>

            {/* Right: price */}
            <div className="lg:w-64 flex-shrink-0">
              <div className="bg-card-inner rounded-xl border border-card-border p-5 flex flex-col h-full">
                <div className="text-5xl font-black text-accent tracking-tight mb-0.5">
                  {Number(bundle.price)?.toLocaleString('en') ?? bundle.price}
                </div>
                <div className="text-gray-500 text-sm mb-3">USDT за всю сітку</div>
                {income > 0 && (
                  <div className="flex items-center justify-between text-sm py-3 border-t border-b border-card-border mb-4">
                    <span className="text-gray-500">Дохід / міс</span>
                    <span className="text-white font-bold">{income} USDT</span>
                  </div>
                )}
                {buyError && <div className="text-red-400 text-xs mb-3">{buyError}</div>}
                <div className="mt-auto">
                  {!isSold && !isSeller && (
                    <button onClick={handleBuy} disabled={buying}
                      className="w-full py-3 rounded-xl font-bold bg-accent text-black text-base shadow-lg shadow-accent/30 hover:brightness-110 transition-all disabled:opacity-60">
                      {buying ? 'Зачекайте...' : '💸 Купити всю сітку'}
                    </button>
                  )}
                  {isSold && <div className="text-center text-gray-500 text-sm py-3">Сітку продано</div>}
                  {isSeller && !isSold && <div className="text-center text-gray-400 text-sm py-3">Це ваша сітка</div>}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ═══════════ STATS BAR ═══════════ */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { icon: '👥', label: '∑ Підписників',  value: fmt(stats.total_subscribers) },
              { icon: '📊', label: 'Середній ER',    value: stats.avg_er != null ? stats.avg_er.toFixed(1) + '%' : '—' },
              { icon: '💰', label: '∑ Дохід / міс',  value: stats.total_monthly_income > 0 ? fmt(stats.total_monthly_income) + ' USDT' : '—' },
              { icon: '📡', label: 'Каналів у сітці', value: stats.channel_count },
            ].map(m => (
              <div key={m.label}
                className="bg-card border border-card-border rounded-xl p-4 text-center shadow-neon hover:border-accent/20 transition-colors">
                <div className="text-2xl mb-1">{m.icon}</div>
                <div className="text-2xl font-black text-accent">{m.value}</div>
                <div className="text-xs text-gray-500 mt-1">{m.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* ═══════════ CHANNELS + CHARTS ═══════════ */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">

          {/* Left: channels (3/5) */}
          <div className="lg:col-span-3 space-y-4">

            {/* Top channel highlight */}
            {topChannel && (
              <div className="bg-card border border-accent/25 rounded-xl p-4 shadow-neon relative overflow-hidden">
                <div className="absolute top-0 right-0 w-28 h-28 bg-accent/5 rounded-full -translate-y-1/2 translate-x-1/2 pointer-events-none" />
                <div className="text-xs text-accent font-bold uppercase tracking-wider mb-3">🏆 Топ канал за ER</div>
                <Link to={`/channel/${topChannel.id}`} className="flex items-center gap-3 group">
                  <div className="w-14 h-14 rounded-full bg-card-inner border-2 border-accent/30 flex-shrink-0 overflow-hidden">
                    {topChannel.avatar_url
                      ? <img src={topChannel.avatar_url} alt={topChannel.channel_name} className="w-full h-full object-cover" />
                      : <div className="w-full h-full flex items-center justify-center text-accent text-xl font-black">
                          {(topChannel.channel_name || '?')[0].toUpperCase()}
                        </div>
                    }
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-white group-hover:text-accent transition-colors text-base truncate">
                      {topChannel.channel_name}
                    </div>
                    <div className="flex flex-wrap gap-3 mt-1">
                      <span className="text-xs text-gray-500">{fmt(topChannel.subscribers_count)} підп.</span>
                      <span className="text-xs font-bold text-accent">ER {topChannel.er?.toFixed(1)}%</span>
                      {topChannel.avg_views != null && (
                        <span className="text-xs text-gray-500">{fmt(topChannel.avg_views)} перегл.</span>
                      )}
                    </div>
                  </div>
                  <div className="w-7 h-7 rounded-full bg-accent/10 border border-accent/30 flex items-center justify-center flex-shrink-0">
                    <svg className="w-3.5 h-3.5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>
                </Link>
              </div>
            )}

            {/* All channels */}
            <div className="bg-card border border-card-border rounded-xl p-5 shadow-neon">
              <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-4">Всі канали сітки</div>
              <div className="space-y-2">
                {sortedByEr.map((ch, idx) => {
                  const maxEr = topChannel?.er || 1;
                  const barPct = ((ch.er || 0) / maxEr) * 100;
                  return (
                    <Link key={ch.id} to={`/channel/${ch.id}`}
                      className="flex items-center gap-3 p-3 rounded-xl bg-card-inner hover:bg-card-hover border border-card-border hover:border-accent/30 transition-all group">
                      <div className="text-xs text-gray-600 w-4 text-center font-mono flex-shrink-0">{idx + 1}</div>
                      <div className="w-9 h-9 rounded-full bg-card border border-card-border flex-shrink-0 overflow-hidden">
                        {ch.avatar_url
                          ? <img src={ch.avatar_url} alt={ch.channel_name} className="w-full h-full object-cover" />
                          : <div className="w-full h-full flex items-center justify-center text-accent text-sm font-black">
                              {(ch.channel_name || '?')[0].toUpperCase()}
                            </div>
                        }
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-white group-hover:text-accent transition-colors truncate text-sm">
                          {ch.channel_name}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <div className="flex-1 h-1 bg-card rounded-full overflow-hidden">
                            <div className="h-full bg-accent/60 rounded-full" style={{ width: `${barPct}%` }} />
                          </div>
                          <span className="text-xs text-gray-500 flex-shrink-0">{fmt(ch.subscribers_count)} підп.</span>
                        </div>
                      </div>
                      {ch.er != null && (
                        <div className="text-right flex-shrink-0">
                          <div className="text-accent font-bold text-sm">{ch.er.toFixed(1)}%</div>
                          <div className="text-[10px] text-gray-600">ER</div>
                        </div>
                      )}
                      <svg className="w-4 h-4 text-gray-600 group-hover:text-accent flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </Link>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Right: charts (2/5) */}
          <div className="lg:col-span-2 space-y-4">

            {/* Donut: subscriber distribution */}
            {channels.length > 0 && stats?.total_subscribers > 0 && (
              <div className="bg-card border border-card-border rounded-xl p-4 shadow-neon">
                <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Розподіл підписників</div>
                <Chart type="donut" options={donutOptions} series={subsSeries} height={230} />
              </div>
            )}

            {/* Bar: ER comparison */}
            {channels.length > 0 && (
              <div className="bg-card border border-card-border rounded-xl p-4 shadow-neon">
                <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Engagement Rate</div>
                <Chart type="bar" options={erOptions} series={erSeries}
                  height={Math.max(130, channels.length * 44)} />
              </div>
            )}

            {/* Avg views mini-table */}
            {channels.some(c => c.avg_views > 0) && (
              <div className="bg-card border border-card-border rounded-xl p-4 shadow-neon">
                <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Середні перегляди</div>
                <div className="space-y-2.5">
                  {[...channels].sort((a, b) => (b.avg_views || 0) - (a.avg_views || 0)).map(ch => {
                    const maxV = Math.max(...channels.map(c => c.avg_views || 0));
                    const pct = maxV > 0 ? ((ch.avg_views || 0) / maxV) * 100 : 0;
                    return (
                      <div key={ch.id} className="flex items-center gap-2">
                        <div className="text-xs text-gray-400 w-20 truncate flex-shrink-0">
                          {ch.channel_name?.length > 9 ? ch.channel_name.slice(0, 9) + '…' : ch.channel_name}
                        </div>
                        <div className="flex-1 h-1.5 bg-card-inner rounded-full overflow-hidden">
                          <div className="h-full bg-accent/50 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="text-xs text-accent font-semibold w-10 text-right flex-shrink-0">
                          {fmt(ch.avg_views)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ═══════════ RESOURCES ═══════════ */}
        {bundle.resources && (
          <div className="bg-card border border-card-border rounded-xl p-5 shadow-neon">
            <div className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">📦 Що входить у продаж</div>
            <p className="text-gray-300 text-sm whitespace-pre-wrap leading-relaxed">{bundle.resources}</p>
          </div>
        )}

        {/* ═══════════ AI ANALYSIS ═══════════ */}
        <div className="bg-card border border-card-border rounded-2xl p-6 shadow-neon-lg">

          <div className="flex items-center gap-3 mb-5">
            <div className="w-8 h-8 rounded-lg bg-accent/15 border border-accent/30 flex items-center justify-center text-sm">🤖</div>
            <div>
              <h2 className="text-base font-bold leading-none">AI аналіз сітки</h2>
              <div className="text-[10px] text-gray-600 mt-0.5">Groq · Llama 3.3 70B · кеш 7 днів</div>
            </div>
          </div>

          {aiError && (
            <div className="flex items-start gap-3 bg-red-950/40 border border-red-900/50 rounded-xl p-4 mb-4">
              <span className="text-red-400 text-lg flex-shrink-0">⚠️</span>
              <div className="flex-1">
                <div className="text-red-400 text-sm">{aiError}</div>
                <button onClick={handleAiAnalysis}
                  className="mt-2 text-xs px-3 py-1 rounded-lg border border-red-400/30 text-red-400 hover:bg-red-400/10 transition-colors">
                  Спробувати ще раз
                </button>
              </div>
            </div>
          )}

          {aiLoading && (
            <div className="flex flex-col items-center justify-center py-10 gap-4">
              <div className="relative w-14 h-14">
                <div className="absolute inset-0 border-2 border-accent/15 rounded-full" />
                <div className="absolute inset-0 border-2 border-t-accent rounded-full animate-spin" />
                <div className="absolute inset-2 border-2 border-t-transparent border-l-accent/40 rounded-full animate-spin"
                  style={{ animationDirection: 'reverse', animationDuration: '1.8s' }} />
              </div>
              <div className="text-center">
                <div className="text-gray-400 text-sm">Groq аналізує {channels.length} каналів...</div>
                <div className="text-gray-600 text-xs mt-1">Зазвичай 10–20 секунд</div>
              </div>
            </div>
          )}

          {aiAnalysis && !aiAnalysis.error && (
            <div className="space-y-5">

              {/* Verdict row */}
              <div className="flex flex-wrap items-center gap-4 p-4 bg-card-inner rounded-xl border border-card-border">
                <ScoreRing score={aiAnalysis.score || 0} />
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full border text-sm font-bold ${vCfg.cls}`}>
                      {vCfg.label}
                    </span>
                    {aiAnalysis.roi_months && (
                      <span className="text-xs bg-card border border-card-border rounded-full px-3 py-1 text-gray-300">
                        📅 Окупність: <strong>{aiAnalysis.roi_months} міс.</strong>
                      </span>
                    )}
                  </div>
                  {aiAnalysis.verdict_reason && (
                    <p className="text-gray-300 text-sm leading-relaxed">{aiAnalysis.verdict_reason}</p>
                  )}
                </div>
              </div>

              {/* Summary */}
              {aiAnalysis.summary && (
                <div className="text-gray-300 text-sm leading-relaxed border-l-2 border-accent/30 pl-3">
                  {aiAnalysis.summary}
                </div>
              )}

              {/* Key metrics */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {(aiAnalysis.total_potential_income_min || aiAnalysis.total_potential_income_max) && (
                  <div className="bg-card-inner rounded-xl border border-card-border p-4">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1.5">💰 Потенційний дохід / міс</div>
                    <div className="text-accent font-black text-lg">
                      {aiAnalysis.total_potential_income_min}–{aiAnalysis.total_potential_income_max}
                    </div>
                    <div className="text-xs text-gray-600">USDT</div>
                  </div>
                )}
                {aiAnalysis.fair_price_estimate && (
                  <div className="bg-card-inner rounded-xl border border-card-border p-4">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1.5">🎯 Справедлива ціна</div>
                    <div className="text-white text-sm leading-snug">{aiAnalysis.fair_price_estimate}</div>
                  </div>
                )}
                {(aiAnalysis.synergy || aiAnalysis.audience_quality) && (
                  <div className="bg-card-inner rounded-xl border border-card-border p-4">
                    <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1.5">
                      {aiAnalysis.synergy ? '🔗 Синергія' : '👤 Аудиторія'}
                    </div>
                    <div className="text-white text-sm leading-snug">
                      {aiAnalysis.synergy || aiAnalysis.audience_quality}
                    </div>
                  </div>
                )}
              </div>

              {/* Audience quality */}
              {aiAnalysis.audience_quality && aiAnalysis.synergy && (
                <div className="bg-card-inner rounded-xl border border-card-border p-4">
                  <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1.5 font-semibold">👤 Якість аудиторії</div>
                  <p className="text-gray-300 text-sm">{aiAnalysis.audience_quality}</p>
                </div>
              )}

              {/* Risks + Opportunities */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {aiAnalysis.risks?.length > 0 && (
                  <div className="bg-red-950/25 border border-red-900/40 rounded-xl p-4">
                    <div className="text-xs text-red-400 font-bold uppercase tracking-wide mb-3">⚠️ Ризики</div>
                    <ul className="space-y-2">
                      {aiAnalysis.risks.map((r, i) => (
                        <li key={i} className="text-xs text-gray-400 flex gap-2 leading-relaxed">
                          <span className="text-red-400 flex-shrink-0 mt-0.5">▸</span>
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {aiAnalysis.opportunities?.length > 0 && (
                  <div className="bg-accent/5 border border-accent/20 rounded-xl p-4">
                    <div className="text-xs text-accent font-bold uppercase tracking-wide mb-3">🚀 Можливості</div>
                    <ul className="space-y-2">
                      {aiAnalysis.opportunities.map((o, i) => (
                        <li key={i} className="text-xs text-gray-400 flex gap-2 leading-relaxed">
                          <span className="text-accent flex-shrink-0 mt-0.5">▸</span>
                          <span>{o}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {!aiAnalysis && !aiLoading && !aiError && (
            <p className="text-gray-600 text-sm text-center py-4">Аналіз недоступний для цієї сітки.</p>
          )}
        </div>

      </div>
    </div>
  );
}

