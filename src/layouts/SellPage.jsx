import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import SellForm from '../components/SellForm';

const TV_URL = 'https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@latest/assets/Television/3D/television_3d.png';
const SATELLITE_URL = 'https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@latest/assets/Satellite%20antenna/3D/satellite_antenna_3d.png';

// glowColor: 'blue' | 'green'
const ChoiceCard = ({ imgSrc, imgAlt, title, desc, cta, onClick, highlighted, glowColor = 'green' }) => (
	<div className="relative" style={{ paddingTop: '3.5rem' }}>
		{/* Icon floating above card — overflows the top edge */}
		<div className="absolute top-0 left-1/2 -translate-x-1/2 z-10" style={{ width: 120, height: 120 }}>
			{/* Ambient glow blob behind icon */}
			<div className={`absolute inset-0 scale-125 rounded-full blur-2xl ${
				glowColor === 'blue' ? 'bg-blue-400/25' : 'bg-accent/25'
			}`} />
			<img
				src={imgSrc}
				alt={imgAlt}
				className="relative w-full h-full object-contain drop-shadow-[0_6px_18px_rgba(0,0,0,0.55)]"
			/>
		</div>

		{/* Square card */}
		<button
			onClick={onClick}
			className={`group relative w-full rounded-2xl overflow-hidden flex flex-col justify-end text-left px-5 pb-5 transition-all duration-300 ${
				highlighted
					? 'bg-card border-2 border-accent shadow-[0_0_50px_rgba(0,255,136,0.22)] hover:shadow-[0_0_65px_rgba(0,255,136,0.33)]'
					: 'bg-[#0C1A1A] border border-[#1A2E2E] hover:border-accent/45 hover:shadow-[0_0_40px_rgba(0,255,136,0.12)]'
			}`}
			style={{ aspectRatio: '1 / 1' }}
		>
			{/* Top glow gradient matching icon color */}
			<div className={`absolute inset-x-0 top-0 h-36 pointer-events-none ${
				glowColor === 'blue'
					? 'bg-gradient-to-b from-blue-500/10 to-transparent'
					: 'bg-gradient-to-b from-accent/10 to-transparent'
			}`} />

			{/* Text + CTA — anchored to bottom */}
			<div className="relative z-10">
				<h2 className="text-[1.1rem] font-black text-white mb-2 leading-snug">{title}</h2>
				<p className="text-xs text-gray-400 leading-relaxed mb-5">{desc}</p>
				<div className={`w-full py-2.5 px-4 rounded-xl border font-semibold text-sm flex items-center justify-center gap-2 transition-all duration-200 ${
					highlighted
						? 'border-accent text-accent group-hover:bg-accent group-hover:text-black'
						: 'border-accent/55 text-accent group-hover:bg-accent group-hover:text-black'
				}`}>
					{cta}
					<svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
					</svg>
				</div>
			</div>
		</button>
	</div>
);

const SellPage = () => {
	const [mode, setMode] = useState(null);
	const navigate = useNavigate();

	if (mode === 'channel') {
		return <SellForm onBack={() => setMode(null)} />;
	}

	return (
		<div className="min-h-screen text-white flex items-center">
		<div className="w-full max-w-2xl mx-auto px-4" style={{ paddingTop: '7rem', paddingBottom: '5rem' }}>
				{/* Heading */}
				<div className="text-center mb-10">
					<h1 className="text-4xl md:text-5xl font-black mb-3 leading-tight">
						Що ви хочете{' '}
						<span className="text-accent">продати?</span>
					</h1>
					<p className="text-gray-400 text-sm">
						Оберіть тип оголошення — і заповніть зручну форму
					</p>
				</div>

				{/* Cards */}
				<div className="grid sm:grid-cols-2 gap-5">
					<ChoiceCard
						imgSrc={TV_URL}
						imgAlt="Television"
						title="Один канал"
						desc="Розмістіть окреме оголошення для одного Telegram-каналу з фіксованою ціною або аукціоном."
						cta="Оформити оголошення"
						onClick={() => setMode('channel')}
						glowColor="blue"
					/>
					<ChoiceCard
						imgSrc={SATELLITE_URL}
						imgAlt="Satellite antenna"
						title="Сітка каналів"
						desc="Об'єднайте кілька каналів в одну пропозицію. Покупець придбає всю сітку одразу."
						cta="Об'єднати та продати"
						onClick={() => navigate('/sell-bundle')}
						highlighted
						glowColor="green"
					/>
				</div>
			</div>
		</div>
	);
};

export default SellPage;
