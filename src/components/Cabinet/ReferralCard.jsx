import { useEffect, useState } from 'react';
import { meAPI } from '../../services/api';
import '../Services/promo-banner.css';

/** «Приведи продавця»: own referral link with a copy button (cabinet). */
export default function ReferralCard({ className = '' }) {
	const [data, setData] = useState(null);
	const [copied, setCopied] = useState(false);
	useEffect(() => { meAPI.referral().then((r) => setData(r.data)).catch(() => {}); }, []);
	if (!data?.link) return null;
	const copy = async () => {
		try { await navigator.clipboard.writeText(data.link); }
		catch {
			const t = document.createElement('textarea'); t.value = data.link; document.body.appendChild(t); t.select();
			document.execCommand('copy'); t.remove();
		}
		setCopied(true); setTimeout(() => setCopied(false), 2000);
	};
	return (
		<div className={`promo-banner flex-col sm:flex-row !items-stretch sm:!items-center ${className}`} role='region' aria-label='Приведи продавця'>
			<span className='promo-banner__icon hidden sm:grid' aria-hidden='true'>🤝</span>
			<div className='promo-banner__body flex-1'>
				<span className='promo-banner__tag'>Приведи продавця</span>
				<p className='promo-banner__text'>Запросіть продавця за своїм посиланням: коли модерація схвалить його перший лот, ви отримаєте значок «Перевірено TgSell» безкоштовно.</p>
				<code className='block mt-2 text-xs text-gray-400 break-all'>{data.link}</code>
				{(data.rewards_applied > 0 || data.credits > 0) && (
					<p className='mt-1 text-xs text-gray-400'>Отримано значків: {data.rewards_applied}{data.credits > 0 ? ` · очікує вашого нового лота: ${data.credits}` : ''}</p>
				)}
			</div>
			<button type='button' onClick={copy} className='relative shrink-0 rounded-xl px-4 py-2 text-sm font-semibold bg-accent text-black'>
				{copied ? 'Скопійовано ✓' : 'Копіювати посилання'}
			</button>
		</div>
	);
}
