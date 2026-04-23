import { Link } from 'react-router-dom';

function fmt(n) {
  if (!n) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K';
  return String(n);
}

export default function BundleCard({ bundle }) {
  const channels = bundle.channels || [];
  const avatarSlice = channels.slice(0, 5);
  const extra = channels.length - 5;

  return (
    <Link to={`/bundle/${bundle.id}`}
      className="block bg-card border border-card-border rounded-xl p-5 shadow-neon hover:shadow-neon-lg hover:border-accent/30 transition-all group">

      {/* Badge + Title */}
      <div className="flex items-center gap-2 mb-3">
        <span className="inline-flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full bg-accent/15 text-accent border border-accent/30">
          📡 СІТКА · {bundle.channel_count} каналів
        </span>
      </div>

      <h3 className="font-bold text-white text-lg mb-3 group-hover:text-accent transition-colors line-clamp-1">
        {bundle.name}
      </h3>

      {/* Avatar strip */}
      {avatarSlice.length > 0 && (
        <div className="flex items-center mb-4">
          {avatarSlice.map((ch, i) => (
            <div key={ch.id} className="w-8 h-8 rounded-full bg-card-inner border-2 border-card overflow-hidden flex-shrink-0"
              style={{ marginLeft: i > 0 ? '-8px' : '0', zIndex: avatarSlice.length - i }}>
              {ch.avatar_url
                ? <img src={ch.avatar_url} alt={ch.channel_name} className="w-full h-full object-cover" />
                : <div className="w-full h-full flex items-center justify-center text-accent text-xs font-bold">
                    {(ch.channel_name || '?')[0].toUpperCase()}
                  </div>
              }
            </div>
          ))}
          {extra > 0 && (
            <div className="w-8 h-8 rounded-full bg-card-inner border-2 border-card flex items-center justify-center text-xs text-gray-400 font-bold"
              style={{ marginLeft: '-8px' }}>
              +{extra}
            </div>
          )}
          <span className="ml-3 text-xs text-gray-500">
            {channels.map(c => c.channel_name).slice(0, 3).join(', ')}
            {channels.length > 3 ? ' та ін.' : ''}
          </span>
        </div>
      )}

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-card-inner rounded-lg p-3">
          <div className="text-lg font-bold text-white">{fmt(bundle.total_subscribers)}</div>
          <div className="text-xs text-gray-500">∑ підписників</div>
        </div>
        <div className="bg-card-inner rounded-lg p-3">
          <div className="text-lg font-bold text-white">
            {bundle.avg_er != null ? bundle.avg_er.toFixed(1) + '%' : '—'}
          </div>
          <div className="text-xs text-gray-500">середній ER</div>
        </div>
        <div className="bg-card-inner rounded-lg p-3">
          <div className="text-lg font-bold text-accent">
            {bundle.monthly_income ? fmt(bundle.monthly_income) + ' $' : '—'}
          </div>
          <div className="text-xs text-gray-500">дохід / міс</div>
        </div>
        <div className="bg-card-inner rounded-lg p-3">
          <div className="text-lg font-bold text-white">{bundle.channel_count}</div>
          <div className="text-xs text-gray-500">каналів</div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-card-border">
        <div>
          <span className="text-xl font-black text-accent">{bundle.price}</span>
          <span className="text-sm text-gray-400 ml-1">USDT за всю сітку</span>
        </div>
        <span className="text-sm text-accent group-hover:underline">Переглянути →</span>
      </div>
    </Link>
  );
}
