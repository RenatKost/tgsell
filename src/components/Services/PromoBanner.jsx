import { useEffect, useState } from 'react';
import { servicesAPI } from '../../services/api';
import './promo-banner.css';

const MONTHS = ['січня', 'лютого', 'березня', 'квітня', 'травня', 'червня', 'липня', 'серпня', 'вересня', 'жовтня', 'листопада', 'грудня'];

// "2026-11-01T23:59:00+02:00" → "1 листопада" (local date of the configured deadline, no TZ shift)
export function promoDateLabel(iso) {
	const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
	return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]}` : '';
}

export function promoText(p) {
	return `Акція: кожен новий лот, схвалений до ${promoDateLabel(p.ends_at_local)}, отримує Топ на ${p.days} днів безкоштовно`;
}

/** Seller promo banner: rendered only while GET /api/services/promo says active. */
export default function PromoBanner({ className = '' }) {
	const [promo, setPromo] = useState(null);
	useEffect(() => {
		let alive = true;
		servicesAPI.promo().then(r => { if (alive) setPromo(r.data); }).catch(() => {});
		return () => { alive = false; };
	}, []);
	if (!promo?.active || !promo.ends_at_local) return null;
	return (
		<div className={`promo-banner ${className}`} role='note' aria-label='Акція для продавців'>
			<span className='promo-banner__glow' aria-hidden='true' />
			<span className='promo-banner__icon' aria-hidden='true'>🎁</span>
			<div className='promo-banner__body'>
				<span className='promo-banner__tag'>Акція для продавців</span>
				<p className='promo-banner__text'>{promoText(promo)}</p>
			</div>
		</div>
	);
}
