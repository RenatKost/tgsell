// Task 31: seller-stated Telegram Stars / TON balance. Display only —
// no conversion to other currencies, never used for price / fair price / quality.

export const hasBalance = (item) =>
	Number(item?.stars_balance || 0) > 0 || Number(item?.ton_balance || 0) > 0;

export const formatStars = (v) => Number(v).toLocaleString('uk-UA', { maximumFractionDigits: 0 });
export const formatTon = (v) => Number(v).toLocaleString('uk-UA', { maximumFractionDigits: 9 });

export const balanceText = (stars, ton) => {
	const parts = [];
	if (Number(stars || 0) > 0) parts.push(`⭐ ${formatStars(stars)} Stars`);
	if (Number(ton || 0) > 0) parts.push(`💎 ${formatTon(ton)} TON`);
	return parts.join(' · ');
};

const BalanceBadges = ({ stars, ton, size = 'sm', caption = true, className = '' }) => {
	const showStars = Number(stars || 0) > 0;
	const showTon = Number(ton || 0) > 0;
	if (!showStars && !showTon) return null;
	const pad = size === 'xs' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs';
	return (
		<div className={`flex flex-wrap items-center gap-1.5 ${className}`} data-testid='balance-badges'>
			{showStars && (
				<span className={`${pad} rounded-full font-semibold bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 whitespace-nowrap`}>
					⭐ {formatStars(stars)} Stars
				</span>
			)}
			{showTon && (
				<span className={`${pad} rounded-full font-semibold bg-sky-500/10 text-sky-400 border border-sky-500/20 whitespace-nowrap`}>
					💎 {formatTon(ton)} TON
				</span>
			)}
			{caption && <span className='text-[11px] text-gray-500 whitespace-nowrap'>зі слів продавця</span>}
		</div>
	);
};

export default BalanceBadges;
