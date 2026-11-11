import { useCallback, useEffect, useRef, useState } from 'react';
import { servicesAPI } from '../services/api';
import { openInvoices } from '../utils/topFunnel';

const POLL_MS = 20000;

/** Load GET /services/orders/my; poll every 20s only while an invoice is awaiting payment. */
export default function useMyServiceOrders(enabled = true) {
	const [orders, setOrders] = useState([]);
	const [loaded, setLoaded] = useState(false);
	const enabledRef = useRef(enabled);
	enabledRef.current = enabled;

	const refresh = useCallback(async () => {
		if (!enabledRef.current) return [];
		try {
			const { data } = await servicesAPI.mine();
			const list = Array.isArray(data) ? data : [];
			setOrders(list);
			return list;
		} catch {
			return null;
		} finally {
			setLoaded(true);
		}
	}, []);

	useEffect(() => {
		if (!enabled) return undefined;
		refresh();
		return undefined;
	}, [enabled, refresh]);

	const hasOpen = openInvoices(orders).length > 0;
	useEffect(() => {
		if (!enabled || !hasOpen) return undefined;
		const tick = () => {
			if (document.visibilityState === 'hidden') return;
			refresh();
		};
		const id = setInterval(tick, POLL_MS);
		document.addEventListener('visibilitychange', tick);
		return () => {
			clearInterval(id);
			document.removeEventListener('visibilitychange', tick);
		};
	}, [enabled, hasOpen, refresh]);

	return { orders, loaded, refresh, hasOpen };
}
