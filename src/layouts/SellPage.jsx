import { Link } from 'react-router-dom';
import SellForm from '../components/SellForm';

const SellPage = () => {
	return (
		<>
			<SellForm />
			<div className="max-w-2xl mx-auto px-4 pb-12 -mt-4">
				<Link to="/sell-bundle"
					className="flex items-center justify-between gap-4 p-5 rounded-xl bg-card border border-accent/20 shadow-neon hover:border-accent/40 hover:shadow-neon-lg transition-all group">
					<div className="flex items-center gap-3">
						<span className="text-3xl">📡</span>
						<div>
							<div className="font-bold text-white group-hover:text-accent transition-colors">
								Продати сетку каналів
							</div>
							<div className="text-sm text-gray-400">
								Об'єднайте кілька каналів в одну пропозицію за вигіднішою ціною
							</div>
						</div>
					</div>
					<svg className="w-5 h-5 text-accent flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
						<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
					</svg>
				</Link>
			</div>
		</>
	);
};

export default SellPage;
