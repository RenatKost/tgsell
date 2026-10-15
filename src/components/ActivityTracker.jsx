import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { HEARTBEAT_MS, pageFromPath, sendHeartbeat, trackEvent } from '../utils/tracking';

// Task 23: visit per page view (server dedupes per 30 min) + heartbeat only while tab is visible.
const ActivityTracker = () => {
	const { pathname } = useLocation();
	const page = pageFromPath(pathname);
	useEffect(() => { trackEvent('visit', { page }); }, [page]);
	useEffect(() => {
		sendHeartbeat();
		const t = setInterval(sendHeartbeat, HEARTBEAT_MS);
		const onVis = () => { if (document.visibilityState === 'visible') sendHeartbeat(); };
		document.addEventListener('visibilitychange', onVis);
		return () => { clearInterval(t); document.removeEventListener('visibilitychange', onVis); };
	}, []);
	return null;
};

export default ActivityTracker;
