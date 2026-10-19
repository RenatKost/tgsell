import { useState } from 'react';
import usePageMeta from '../hooks/usePageMeta';
import { A, Card, Cta, PageShell, Section } from '../components/Seo/SeoBlocks';
import { estimate, usd } from '../seo/marketData';

const PATH = '/skilky-koshtuye-telegram-kanal';
const PRESETS = [1000, 5000, 10000];
const MAX_SUBS = 10000000;
const num = (n) => n.toLocaleString('uk-UA');

const EstimateRow = ({ subs }) => {
	const e = estimate(subs);
	return (
		<div className="rounded-xl border border-gray-100 dark:border-card-border p-5">
			<p className="text-xs font-bold uppercase tracking-widest text-gray-400 mb-1">{num(subs)} підписників</p>
			<p className="text-3xl font-black text-accent">≈ {usd(e.median)}</p>
			<p className="text-sm text-gray-500 dark:text-gray-400 mt-1">діапазон {usd(e.low)} – {usd(e.high)}</p>
		</div>
	);
};

const ChannelPriceCalculatorPage = () => {
	const meta = usePageMeta(PATH);
	const [raw, setRaw] = useState('3000');
	const subs = Math.min(MAX_SUBS, Math.max(0, parseInt(String(raw).replace(/\D/g, ''), 10) || 0));

	return (
		<PageShell
			badge="Калькулятор"
			h1={meta.h1}
			lead="Скільки коштує телеграм канал з 1000, 5000 чи 10000 підписників? Нижче — орієнтовна оцінка на основі аналізу актуальних ринкових цін на українські Telegram-канали."
		>
			<Card>
				<Section title="Типові оцінки">
					<div className="grid sm:grid-cols-3 gap-4">
						{PRESETS.map((p) => <EstimateRow key={p} subs={p} />)}
					</div>
				</Section>

				<Section title="Порахуйте для свого каналу">
					<label htmlFor="subs" className="block font-bold text-gray-900 dark:text-white mb-2">Кількість підписників</label>
					<div className="flex flex-wrap gap-2 mb-4">
						<input
							id="subs"
							type="text"
							inputMode="numeric"
							value={raw}
							onChange={(e) => setRaw(e.target.value)}
							className="w-48 rounded-xl border border-gray-200 dark:border-card-border bg-gray-50 dark:bg-card-inner px-4 py-2.5 text-gray-900 dark:text-white font-bold focus:outline-none focus:border-accent"
						/>
						{PRESETS.map((p) => (
							<button
								key={p}
								type="button"
								onClick={() => setRaw(String(p))}
								className={'px-4 py-2.5 rounded-xl text-sm font-bold border transition-colors ' + (subs === p ? 'border-accent text-accent' : 'border-gray-200 dark:border-card-border text-gray-600 dark:text-gray-300 hover:border-accent')}
							>
								{num(p)}
							</button>
						))}
					</div>
					{subs > 0 ? (
						<EstimateRow subs={subs} />
					) : (
						<p className="text-gray-400">Введіть кількість підписників.</p>
					)}
				</Section>

				<Section title="Як рахується оцінка">
					<p>Оцінка = кількість підписників × середня ринкова ціна за підписника.</p>
					<p>Оцінка базується на аналізі актуальних ринкових цін на українські Telegram-канали.</p>
				</Section>

				<div className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-4 text-sm text-gray-600 dark:text-gray-300">
					<p className="font-bold text-amber-500 mb-1">Це лише орієнтовна оцінка</p>
					<p>
						Реальна вартість конкретного каналу залежить від охоплень, тематики, якості аудиторії, історії та попиту,
						тому може суттєво відрізнятися від оцінки. Для приватних каналів оцінка зазвичай нижча.
					</p>
				</div>
			</Card>

			<Cta
				title="Що далі?"
				text="Порівняйте оцінку з лотами в каталозі або виставте свій канал на продаж."
				links={[
					{ to: '/prodaty-telegram-kanal', label: 'Продати канал' },
					{ to: '/kupyty-telegram-kanal', label: 'Купити канал' },
					{ to: '/catalog', label: 'Каталог' },
				]}
			/>
			<p className="text-xs text-gray-400 text-center">
				Детальніше про угоди — у розділі <A to="/faq">FAQ</A>.
			</p>
		</PageShell>
	);
};

export default ChannelPriceCalculatorPage;
