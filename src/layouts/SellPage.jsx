import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import SellForm from '../components/SellForm';

const MEGAPHONE_URL = 'https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@latest/assets/Megaphone/3D/megaphone_3d.png';
const SATELLITE_URL = 'https://cdn.jsdelivr.net/gh/microsoft/fluentui-emoji@latest/assets/Satellite%20antenna/3D/satellite_antenna_3d.png';

const ChoiceCard = ({ imgSrc, imgAlt, title, desc, cta, onClick, highlighted }) => (
	<button
		onClick={onClick}
		className={`group relative w-full flex flex-col items-center text-center rounded-2xl p-8 pt-10 transition-all duration-300 overflow-hidden
			${
				highlighted
					? 'bg-card border-2 border-accent shadow-[0_0_40px_rgba(0,255,136,0.18)] hover:shadow-[0_0_55px_rgba(0,255,136,0.28)]'
					: 'bg-card border border-card-border shadow-neon hover:border-accent/50 hover:shadow-[0_0_35px_rgba(0,255,136,0.13)]'
			}`}
	>
		{/* Subtle inner glow at top for highlighted card */}
		{highlighted && (
			<div className="absolute inset-x-0 top-0 h-32 bg-gradient-to-b from-accent/8 to-transparent pointer-events-none" />
		)}

		{/* 3D Icon */}
		<div className="relative mb-7">
			<div className={`absolute inset-0 rounded-full blur-2xl ${highlighted ? 'bg-accent/20' : 'bg-accent/10'}`} />
			<img
				src={imgSrc}
				alt={imgAlt}
				className="relative w-32 h-32 object-contain drop-shadow-[0_8px_24px_rgba(0,0,0,0.6)] group-hover:scale-105 transition-transform duration-300"
			/>
		</div>

		{/* Text */}
		<h2 className="text-xl font-black text-white mb-3">{title}</h2>
		<p className="text-sm text-gray-400 leading-relaxed mb-8">{desc}</p>

		{/* CTA Button */}
		<div className={`w-full py-3 px-5 rounded-xl border font-semibold text-sm flex items-center justify-center gap-2 transition-all duration-200
			${
				highlighted
					? 'border-accent text-accent group-hover:bg-accent group-hover:text-black'
					: 'border-accent/50 text-accent group-hover:bg-accent group-hover:text-black'
			}`}>
			{cta}
			<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
				<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
			</svg>
		</div>
	</button>
);

const SellPage = () => {
	const [mode, setMode] = useState(null);
	const navigate = useNavigate();

	if (mode === 'channel') {
		return <SellForm onBack={() => setMode(null)} />;
	}

	return (
		<div className="min-h-screen text-white flex items-center">
			<div className="w-full max-w-2xl mx-auto px-4 py-24">
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
						imgSrc={MEGAPHONE_URL}
						imgAlt="Megaphone"
						title="Один канал"
						desc="Розмістіть окреме оголошення для одного Telegram-каналу з фіксованою ціною або аукціоном."
						cta="Оформити оголошення"
						onClick={() => setMode('channel')}
					/>
					<ChoiceCard
						imgSrc={SATELLITE_URL}
						imgAlt="Satellite antenna"
						title="Сітка каналів"
						desc="Об'єднайте кілька каналів в одну пропозицію. Покупець придбає всю сітку одразу."
						cta="Об'єднати та продати"
						onClick={() => navigate('/sell-bundle')}
						highlighted
					/>
				</div>
			</div>
		</div>
	);
};

export default SellPage;
