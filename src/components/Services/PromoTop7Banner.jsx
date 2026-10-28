import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { servicesAPI } from '../../services/api';
import { isPromoTop7 } from '../../utils/utm';
import './promo-banner.css';

const DISMISS_KEY = 'tgsell_promo_top7_dismissed';

/** Ad landing banner for visitors who came with utm_campaign=promo_top7 (/catalog, /sell).
 * Visible only while the seller promo is active (server PROMO_TOP_UNTIL, Europe/Chisinau). */
export default function PromoTop7Banner({ className = '', onCta }) {
	const [promo, setPromo] = useState(null);
	const [hidden, setHidden] = useState(() => {
		try { return sessionStorage.getItem(DISMISS_KEY) === '1'; } catch { return false; }
	});
	const eligible = isPromoTop7();
	useEffect(() => {
		if (!eligible || hidden) return undefined;
		let alive = true;
		servicesAPI.promo().then((r) => { if (alive) setPromo(r.data); }).catch(() => {});
		return () => { alive = false; };
	}, [eligible, hidden]);
	if (!eligible || hidden || !promo?.active) return null;
	if (promo.ends_at && Date.now() > Date.parse(promo.ends_at)) return null;
	const dismiss = () => {
		try { sessionStorage.setItem(DISMISS_KEY, '1'); } catch { /* ignore */ }
		setHidden(true);
	};
	return (
		<div className={`promo-top7 ${className}`} role='region' aria-label='Акція: розміщення безкоштовно' data-promo-top7>
			<span className='promo-top7__glow' aria-hidden='true' />
			<button type='button' onClick={dismiss} aria-label='Закрити' className='promo-top7__close'>×</button>
			<div className='promo-top7__row'>
				<span className='promo-top7__icon' aria-hidden='true'>🚀</span>
				<p className='promo-top7__title'>Розмістіть канал безкоштовно + Топ 7 днів до 01.11</p>
			</div>
			<Link to='/sell' onClick={onCta} className='promo-top7__cta'>Розмістити канал →</Link>
		</div>
	);
}
