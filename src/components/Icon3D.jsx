/**
 * Icon3D — reusable 3D gradient icon containers
 * Uses lucide-react SVGs with colored gradient backgrounds and glow shadows
 */
import {
  Users, BarChart2, DollarSign, Radio,
  Trophy, Package, AlertTriangle, Rocket,
  Target, Link2, User, TrendingUp,
  ShoppingCart, Megaphone, Handshake,
  Shield, CheckCircle2, XCircle, Clock,
  Wallet, Send, Activity, Zap,
  Search, Star, Lock, Eye,
  LayoutGrid, ChevronRight, Cpu,
} from 'lucide-react';

/**
 * Preset configs: { gradient, shadow, iconColor }
 */
export const presets = {
  green:   { gradient: 'linear-gradient(145deg,#00FF88,#00cc70)', shadow: '0 6px 20px rgba(0,255,136,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' },
  emerald: { gradient: 'linear-gradient(145deg,#10b981,#059669)', shadow: '0 6px 20px rgba(16,185,129,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' },
  blue:    { gradient: 'linear-gradient(145deg,#38bdf8,#0ea5e9)', shadow: '0 6px 20px rgba(56,189,248,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' },
  purple:  { gradient: 'linear-gradient(145deg,#a78bfa,#7c3aed)', shadow: '0 6px 20px rgba(167,139,250,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' },
  gold:    { gradient: 'linear-gradient(145deg,#fbbf24,#f59e0b)', shadow: '0 6px 20px rgba(251,191,36,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' },
  orange:  { gradient: 'linear-gradient(145deg,#fb923c,#ea580c)', shadow: '0 6px 20px rgba(251,146,60,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' },
  red:     { gradient: 'linear-gradient(145deg,#f87171,#ef4444)', shadow: '0 6px 20px rgba(239,68,68,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' },
  pink:    { gradient: 'linear-gradient(145deg,#f472b6,#ec4899)', shadow: '0 6px 20px rgba(244,114,182,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' },
  cyan:    { gradient: 'linear-gradient(145deg,#22d3ee,#0891b2)', shadow: '0 6px 20px rgba(34,211,238,0.45), inset 0 1px 0 rgba(255,255,255,0.25)' },
  slate:   { gradient: 'linear-gradient(145deg,#64748b,#475569)', shadow: '0 6px 20px rgba(100,116,139,0.35), inset 0 1px 0 rgba(255,255,255,0.15)' },
};

const sizes = {
  xs:  { box: 'w-6 h-6',   icon: 12 },
  sm:  { box: 'w-8 h-8',   icon: 15 },
  md:  { box: 'w-10 h-10', icon: 18 },
  lg:  { box: 'w-12 h-12', icon: 22 },
  xl:  { box: 'w-14 h-14', icon: 26 },
};

/**
 * @param {string} preset - color key from presets
 * @param {string} size   - xs|sm|md|lg|xl
 * @param {ReactNode} children - icon from lucide-react
 * @param {string} className - extra classes
 */
export const Icon3D = ({ preset = 'green', size = 'md', children, className = '' }) => {
  const p = presets[preset];
  const s = sizes[size];
  return (
    <div
      className={`${s.box} rounded-xl flex items-center justify-center flex-shrink-0 ${className}`}
      style={{ background: p.gradient, boxShadow: p.shadow }}
    >
      {children}
    </div>
  );
};

/** Convenience wrappers — pass size and optional className */
const ico = (LucideIcon, preset) =>
  ({ size = 'md', className = '', strokeWidth = 2 }) => {
    const s = sizes[size];
    return (
      <Icon3D preset={preset} size={size} className={className}>
        <LucideIcon size={s.icon} color="#fff" strokeWidth={strokeWidth} />
      </Icon3D>
    );
  };

export const IcoUsers    = ico(Users,         'green');
export const IcoChart    = ico(BarChart2,      'blue');
export const IcoDollar   = ico(DollarSign,     'gold');
export const IcoSignal   = ico(Radio,          'purple');
export const IcoTrophy   = ico(Trophy,         'gold');
export const IcoPackage  = ico(Package,        'orange');
export const IcoWarning  = ico(AlertTriangle,  'red');
export const IcoRocket   = ico(Rocket,         'purple');
export const IcoTarget   = ico(Target,         'cyan');
export const IcoLink     = ico(Link2,          'blue');
export const IcoUser     = ico(User,           'slate');
export const IcoTrend    = ico(TrendingUp,     'emerald');
export const IcoCart     = ico(ShoppingCart,   'green');
export const IcoMega     = ico(Megaphone,      'orange');
export const IcoHandshake= ico(Handshake,      'blue');
export const IcoShield   = ico(Shield,         'emerald');
export const IcoCheck    = ico(CheckCircle2,   'green');
export const IcoCross    = ico(XCircle,        'red');
export const IcoClock    = ico(Clock,          'slate');
export const IcoWallet   = ico(Wallet,         'gold');
export const IcoSend     = ico(Send,           'cyan');
export const IcoActivity = ico(Activity,       'purple');
export const IcoZap      = ico(Zap,            'gold');
export const IcoSearch   = ico(Search,         'blue');
export const IcoStar     = ico(Star,           'gold');
export const IcoLock     = ico(Lock,           'slate');
export const IcoEye      = ico(Eye,            'blue');
export const IcoGrid     = ico(LayoutGrid,     'purple');
export const IcoCpu      = ico(Cpu,            'cyan');
