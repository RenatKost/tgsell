import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AppContext';
import { peekPendingBuy } from '../../utils/buyIntent';

/** After Telegram login on another path, return the buyer to the lot they wanted to buy. */
const BuyIntentGate = () => {
	const { isAuthenticated } = useAuth();
	const loc = useLocation();
	const navigate = useNavigate();

	useEffect(() => {
		if (!isAuthenticated) return;
		const pending = peekPendingBuy();
		if (!pending) return;
		const target = `/channel/${pending.channelId}`;
		if (loc.pathname === target) return;
		if (loc.pathname.startsWith('/deal/')) return;
		navigate(target, { replace: false });
	}, [isAuthenticated, loc.pathname, navigate]);

	return null;
};

export default BuyIntentGate;
