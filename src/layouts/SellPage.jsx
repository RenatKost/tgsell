import PromoBanner from '../components/Services/PromoBanner';
import PromoTop7Banner from '../components/Services/PromoTop7Banner';
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import SellForm, { hasPendingSellSubmit } from '../components/SellForm';
import { getUtm, trackFunnel } from '../utils/utm';
import { wantsDirectSingle } from '../utils/sellEntry';
import './escrow.css';
import './premium.css';
import './public.css';

const CHANNEL_URL = '/megaphone-3d.png';
const BUNDLE_URL = '/satellite-3d.png';

// color: 'pink' | 'teal'
const COLORS = {
	pink: {
		hex:        '#FF3FA4',
		border:     '1px solid #FF3FA4',
		boxShadow:  '0 0 0 1px rgba(255,63,164,0.55), 0 0 28px rgba(255,63,164,0.30), 0 0 60px rgba(255,63,164,0.12)',
		hoverShadow:'0 0 0 1px rgba(255,63,164,0.75), 0 0 42px rgba(255,63,164,0.42), 0 0 80px rgba(255,63,164,0.18)',
		glow:       'rgba(255,63,164,0.30)',
		gradient:   'linear-gradient(160deg, rgba(255,63,164,0.13) 0%, transparent 55%)',
		iconFilter: 'drop-shadow(0 0 18px rgba(255,63,164,0.75)) drop-shadow(0 0 6px rgba(255,63,164,0.5))',
		btnBorder:  '1px solid rgba(255,63,164,0.7)',
		btnColor:   '#FF3FA4',
		btnHover:   'rgba(255,63,164,0.12)',
	},
	teal: {
		hex:        '#00D4AA',
		border:     '1px solid #00D4AA',
		boxShadow:  '0 0 0 1px rgba(0,212,170,0.55), 0 0 28px rgba(0,212,170,0.30), 0 0 60px rgba(0,212,170,0.12)',
		hoverShadow:'0 0 0 1px rgba(0,212,170,0.75), 0 0 42px rgba(0,212,170,0.42), 0 0 80px rgba(0,212,170,0.18)',
		glow:       'rgba(0,212,170,0.28)',
		gradient:   'linear-gradient(160deg, rgba(0,212,170,0.11) 0%, transparent 55%)',
		iconFilter: 'drop-shadow(0 0 18px rgba(0,212,170,0.75)) drop-shadow(0 0 6px rgba(0,212,170,0.5))',
		btnBorder:  '1px solid rgba(0,212,170,0.7)',
		btnColor:   '#00D4AA',
		btnHover:   'rgba(0,212,170,0.12)',
	},
};

const ChoiceCard = ({ imgSrc, imgAlt, title, desc, cta, onClick, color = 'teal' }) => {
	const c = COLORS[color];
	return (
		<button
			onClick={onClick}
			className="group relative w-full rounded-2xl overflow-hidden flex flex-col text-left transition-all duration-300 bg-card sm:aspect-square"
			style={{ border: c.border, boxShadow: c.boxShadow }}
			onMouseEnter={e => { e.currentTarget.style.boxShadow = c.hoverShadow; }}
			onMouseLeave={e => { e.currentTarget.style.boxShadow = c.boxShadow; }}
		>
			{/* Top-left gradient tint */}
			<div className="absolute inset-0 pointer-events-none" style={{ background: c.gradient }} />

			{/* Icon glow blob */}
			<div
				className="absolute top-3 right-3 w-36 h-36 rounded-full blur-3xl pointer-events-none"
				style={{ background: c.glow }}
			/>

			{/* Icon */}
			<div className="absolute top-3 right-2 w-24 h-24 sm:w-40 sm:h-40">
				<img
					src={imgSrc}
					alt={imgAlt}
					className="w-full h-full object-contain"
					style={{ filter: c.iconFilter }}
				/>
			</div>

			{/* Text + CTA anchored to bottom */}
			<div className="relative z-10 mt-auto px-5 pb-5 pt-24 sm:pt-0">
				<h2 className="text-[1.15rem] font-black text-white mb-2 leading-snug">{title}</h2>
				<p className="text-xs text-gray-400 leading-relaxed mb-5">{desc}</p>
				<div
					className="w-full py-2.5 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-all duration-200"
					style={{ border: c.btnBorder, color: c.btnColor }}
					onMouseEnter={e => { e.currentTarget.style.background = c.btnHover; }}
					onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
				>
					{cta}
					<svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
					</svg>
				</div>
			</div>
		</button>
	);
};

const SellPage = () => {
	const [params] = useSearchParams();
	const wantedId = params.get('wanted');
	const [search] = useState(() => window.location.search);
	// IG promo campaigns (current URL or stored first touch) and ?type=single skip the type chooser.
	const [auto, setAuto] = useState(() => !wantedId && !hasPendingSellSubmit() && wantsDirectSingle(search, getUtm()?.utm_campaign));
	const [mode, setMode] = useState(wantedId || hasPendingSellSubmit() || auto ? 'channel' : null);
	const navigate = useNavigate();
	// Funnel «sell_open» for the auto-opened form: once (trackFunnel dedupes per tab session).
	useEffect(() => { if (auto) trackFunnel('sell_open', { auto: true }); }, [auto]);
	// Funnel «sell_open»: the visitor left the type chooser for a form (before any typing).
	const openChannel = () => { trackFunnel('sell_open'); setMode('channel'); };

	if (mode === 'channel') {
		return (
			<>
				{auto && (
					<div className="relative z-20 w-full max-w-2xl mx-auto px-4 text-right" style={{ marginBottom: '-5.5rem', paddingTop: '5.5rem' }}>
						<button
							type="button"
							data-testid="sell-bundle-link"
							className="text-xs text-gray-400 underline underline-offset-2 hover:text-white"
							onClick={() => { trackFunnel('sell_open'); navigate('/sell-bundle'); }}
						>
							У мене сітка
						</button>
					</div>
				)}
				<SellForm onBack={() => { setAuto(false); setMode(null); }} wantedId={wantedId} />
			</>
		);
	}

	return (
		<div className="esc-page prm-pub relative overflow-x-clip md:min-h-screen text-white flex items-center">
		<div className="esc-bg esc-bg-short" aria-hidden="true"><span className="esc-grid" /><span className="esc-blob esc-blob-1" /><span className="esc-blob esc-blob-2" /></div>
		<div className="w-full max-w-2xl mx-auto px-4" style={{ paddingTop: '7rem', paddingBottom: '5rem' }}>
				{/* Heading */}
				<div className="text-center mb-10">
					<h1 className="esc-title text-4xl md:text-5xl font-black mb-3 leading-tight">
						Що ви хочете{' '}
						<span className="text-accent">продати?</span>
					</h1>
					<p className="text-gray-400 text-sm">
						Оберіть тип оголошення — і заповніть зручну форму
					</p>
				</div>

				<PromoTop7Banner className="mb-4" onCta={(e) => { e.preventDefault(); openChannel(); }} />
				<PromoBanner className="mb-6" />

				{/* Cards */}
				<div className="grid sm:grid-cols-2 gap-5">
					<ChoiceCard
						imgSrc={CHANNEL_URL}
						imgAlt="Megaphone"
						title="Один канал"
						desc="Розмістіть окреме оголошення для одного Telegram-каналу з фіксованою ціною або аукціоном."
						cta="Оформити оголошення"
						onClick={() => openChannel()}
						color="pink"
					/>
					<ChoiceCard
						imgSrc={BUNDLE_URL}
						imgAlt="Satellite antenna"
						title="Сітка каналів"
						desc="Об'єднайте кілька каналів в одну пропозицію. Покупець придбає всю сітку одразу."
						cta="Об'єднати та продати"
						onClick={() => { trackFunnel('sell_open'); navigate('/sell-bundle'); }}
						color="teal"
					/>
				</div>
			</div>
		</div>
	);
};

export default SellPage;
