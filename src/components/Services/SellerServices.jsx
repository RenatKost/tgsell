import { useEffect, useState } from 'react';
import PromoteDialog, { useServicesCatalog, availableServices } from './PromoteDialog';
import './topGlow.css';
import { topOfferFromCatalog, topButtonLabel, slotsLine, findOpenOrder, inTopUntilLabel } from '../../utils/topFunnel';

/** «Підняти в Топ» on an approved cabinet card + quieter entry to other paid services. */
const SellerServices = ({ channel, orders = [], onOpenTop, openTopRequest = 0 }) => {
	const cat = useServicesCatalog();
	const [open, setOpen] = useState(null); // 'top' | 'other' | null
	const offer = topOfferFromCatalog(cat);
	const published = channel?.status === 'approved';
	const inTop = !!channel?.is_top;
	const openInvoice = findOpenOrder(orders, channel?.id, 'top');
	const others = (availableServices(cat, channel) || []).filter((i) => i.kind !== 'top');

	useEffect(() => {
		if (openTopRequest) setOpen('top');
	}, [openTopRequest]);

	if (!published || !cat) {
		// Pending lots keep the quieter «Просунути» (pay is still blocked until approve).
		if (!['approved', 'pending'].includes(channel?.status) || !cat) return null;
		if (availableServices(cat, channel).length === 0) return null;
		const min = Math.min(...availableServices(cat, channel).map((i) => Number(i.price_usdt)));
		return (
			<div className='px-4 sm:px-5 pb-4 sm:pb-5'>
				<button type='button' onClick={() => setOpen('other')}
					className='w-full inline-flex items-center justify-center gap-2 min-h-[44px] px-4 rounded-xl bg-accent/10 border border-accent/40 text-accent font-semibold text-sm hover:bg-accent hover:text-black transition-all'>
					🚀 Просунути <span className='font-normal opacity-80'>· від {min} USDT</span>
				</button>
				{open && <PromoteDialog channel={channel} initialKind={open === 'top' ? 'top' : null} existingOrder={openInvoice} onClose={() => setOpen(null)} />}
			</div>
		);
	}

	const slotsFull = offer && offer.slotsFree === 0 && !openInvoice && !inTop;
	const showTopButton = !inTop;
	const line = slotsLine(offer);

	return (
		<div className='px-4 sm:px-5 pb-4 sm:pb-5 space-y-2'>
			{inTop && (
				<p className='text-center text-sm font-semibold text-emerald-700 dark:text-accent'>{inTopUntilLabel(channel.top_until)}</p>
			)}
			{showTopButton && (
				<button type='button' className='lot-top-btn' disabled={slotsFull}
					onClick={() => { if (!slotsFull) { onOpenTop?.(channel); setOpen('top'); } }}>
					{openInvoice ? 'Показати рахунок на Топ' : topButtonLabel(offer)}
				</button>
			)}
			{line && !inTop && (
				<p className={`text-center text-xs ${slotsFull ? 'text-amber-600 dark:text-amber-400 font-semibold' : 'text-gray-500 dark:text-gray-400'}`}>{line}</p>
			)}
			{others.length > 0 && (
				<button type='button' onClick={() => setOpen('other')}
					className='w-full text-xs font-semibold text-gray-500 dark:text-gray-400 hover:text-accent py-1'>
					Інші послуги
				</button>
			)}
			{open && (
				<PromoteDialog
					channel={channel}
					initialKind={open === 'top' ? 'top' : null}
					existingOrder={open === 'top' ? openInvoice : null}
					onClose={() => setOpen(null)}
				/>
			)}
		</div>
	);
};

export default SellerServices;
