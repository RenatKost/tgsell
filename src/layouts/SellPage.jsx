import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import SellForm from '../components/SellForm';

const ChoiceCard = ({ icon, title, desc, onClick, accent }) => (
	<button
		onClick={onClick}
		className={`group w-full bg-card border rounded-2xl p-8 text-left transition-all shadow-neon hover:shadow-neon-lg
			${accent ? 'border-accent/30 hover:border-accent' : 'border-card-border hover:border-accent/40'}`}
	>
		<div className="text-5xl mb-5">{icon}</div>
		<h2 className="text-xl font-black text-white group-hover:text-accent transition-colors mb-2">{title}</h2>
		<p className="text-sm text-gray-400 leading-relaxed">{desc}</p>
		<div className={`mt-6 inline-flex items-center gap-1.5 text-sm font-semibold transition-colors
			${accent ? 'text-accent' : 'text-gray-500 group-hover:text-accent'}`}>
			Обрати
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
		<div className="min-h-screen bg-page text-white flex items-center">
			<div className="w-full max-w-2xl mx-auto px-4 py-24">
				<div className="text-center mb-12">
					<h1 className="text-4xl font-black mb-3">
						Що ви хочете <span className="text-accent">продати?</span>
					</h1>
					<p className="text-gray-400 text-sm">
						Оберіть тип оголошення — і заповніть зручну форму
					</p>
				</div>

				<div className="grid sm:grid-cols-2 gap-5">
					<ChoiceCard
						icon="📢"
						title="Один канал"
						desc="Розмістіть окреме оголошення для одного Telegram-каналу з фіксованою ціною або аукціоном."
						onClick={() => setMode('channel')}
					/>
					<ChoiceCard
						icon="📡"
						title="Сітка каналів"
						desc="Об'єднайте кілька каналів в одну пропозицію. Покупець придбає всю сітку одразу."
						onClick={() => navigate('/sell-bundle')}
						accent
					/>
				</div>
			</div>
		</div>
	);
};

export default SellPage;
