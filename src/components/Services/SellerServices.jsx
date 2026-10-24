import { useState } from 'react';
import PromoteDialog, { useServicesCatalog, availableServices } from './PromoteDialog';

/** Prominent «Просунути» button on a seller's lot card (cabinet) → service picker + order flow. */
const SellerServices = ({ channel }) => {
	const cat = useServicesCatalog();
	const [open, setOpen] = useState(false);
	if (!['approved', 'pending'].includes(channel.status) || !cat) return null;
	if (availableServices(cat, channel).length === 0) return null;
	const min = Math.min(...availableServices(cat, channel).map((i) => Number(i.price_usdt)));
	return (
		<div className='px-4 sm:px-5 pb-4 sm:pb-5'>
			<button type='button' onClick={() => setOpen(true)}
				className='w-full inline-flex items-center justify-center gap-2 min-h-[44px] px-4 rounded-xl bg-accent/10 border border-accent/40 text-accent font-semibold text-sm hover:bg-accent hover:text-black transition-all'>
				🚀 Просунути <span className='font-normal opacity-80'>· від {min} USDT</span>
			</button>
			{open && <PromoteDialog channel={channel} onClose={() => setOpen(false)} />}
		</div>
	);
};

export default SellerServices;
