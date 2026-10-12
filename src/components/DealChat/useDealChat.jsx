import { useCallback, useEffect, useRef, useState } from 'react';
import { dealsAPI } from '../../services/api';

const newClientId = () =>
	(window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

/**
 * Deal chat state. Short polling with an after_id cursor (server-provided poll_interval_ms).
 * - Polling pauses entirely while the tab is hidden (visibilitychange) and resumes on focus.
 * - No polling at all for completed/cancelled deals (server returns poll_interval_ms = null):
 *   history is loaded once.
 */
export default function useDealChat(dealId) {
	const [messages, setMessages] = useState([]);
	const [pending, setPending] = useState([]); // optimistic {client_id, text, status, file, progress}
	const [state, setState] = useState({ peer_read_id: 0, peer_delivered_id: 0, presence: [], deal: null, unread: 0, my_last_read_id: 0, me: null });
	const [hasOlder, setHasOlder] = useState(false);
	const [loaded, setLoaded] = useState(false);
	const [error, setError] = useState('');
	const lastIdRef = useRef(0);
	const timerRef = useRef(null);
	const intervalRef = useRef(null);
	const inflightRef = useRef(false);
	const aliveRef = useRef(true);
	const pollRef = useRef(null);

	const merge = useCallback((incoming) => {
		if (!incoming?.length) return;
		setMessages(prev => {
			const map = new Map(prev.map(m => [m.id, m]));
			incoming.forEach(m => map.set(m.id, m));
			return [...map.values()].sort((a, b) => a.id - b.id);
		});
		const ids = new Set(incoming.map(m => m.client_id).filter(Boolean));
		if (ids.size) setPending(p => p.filter(x => !ids.has(x.client_id)));
		lastIdRef.current = Math.max(lastIdRef.current, ...incoming.map(m => m.id));
	}, []);

	const schedule = useCallback(() => {
		clearTimeout(timerRef.current);
		if (!aliveRef.current || !intervalRef.current || document.visibilityState === 'hidden') return;
		timerRef.current = setTimeout(() => pollRef.current?.(), intervalRef.current);
	}, []); // eslint-disable-line react-hooks/exhaustive-deps

	const poll = useCallback(async () => {
		if (inflightRef.current) return;
		inflightRef.current = true;
		try {
			const { data } = await dealsAPI.chatPoll(dealId, lastIdRef.current);
			if (!aliveRef.current) return;
			if (!lastIdRef.current) setHasOlder(!!data.has_older);
			merge(data.messages);
			setState({
				peer_read_id: data.peer_read_id, peer_delivered_id: data.peer_delivered_id, presence: data.presence,
				deal: data.deal, unread: data.unread, my_last_read_id: data.my_last_read_id, me: data.me,
			});
			intervalRef.current = data.poll_interval_ms || null;
			setError('');
			setLoaded(true);
			if (data.has_more) setTimeout(() => poll(), 0);
		} catch (e) {
			setError(e?.response?.data?.detail || 'Не вдалося оновити чат');
			setLoaded(true);
		} finally {
			inflightRef.current = false;
			schedule();
		}
	}, [dealId, merge, schedule]);

	pollRef.current = poll;

	useEffect(() => {
		aliveRef.current = true;
		intervalRef.current = null;
		lastIdRef.current = 0;
		setMessages([]); setPending([]); setLoaded(false);
		poll();
		const onVis = () => {
			if (document.visibilityState === 'hidden') clearTimeout(timerRef.current);
			else if (intervalRef.current) poll();
		};
		// iOS Safari: returning from another app / bfcache often fires pageshow/focus but not
		// visibilitychange — without this, polling (and presence/read sync) stayed stopped.
		const onShow = () => { if (document.visibilityState !== 'hidden' && intervalRef.current) poll(); };
		document.addEventListener('visibilitychange', onVis);
		window.addEventListener('pageshow', onShow);
		window.addEventListener('focus', onShow);
		return () => {
			aliveRef.current = false;
			clearTimeout(timerRef.current);
			document.removeEventListener('visibilitychange', onVis);
			window.removeEventListener('pageshow', onShow);
			window.removeEventListener('focus', onShow);
		};
	}, [dealId]); // eslint-disable-line react-hooks/exhaustive-deps

	const loadOlder = useCallback(async () => {
		if (!messages.length) return;
		const { data } = await dealsAPI.chatHistory(dealId, messages[0].id);
		setHasOlder(!!data.has_older);
		merge(data.messages);
	}, [dealId, messages, merge]);

	const readRef = useRef(0);
	const markRead = useCallback(async (id) => {
		if (!id || id <= readRef.current || id <= state.my_last_read_id) return;
		readRef.current = id;
		try {
			const { data } = await dealsAPI.chatRead(dealId, id);
			setState(s => ({ ...s, unread: data.unread, my_last_read_id: data.last_read_message_id }));
		} catch { /* ignore */ }
	}, [dealId, state.my_last_read_id]);

	const typingRef = useRef(0);
	const notifyTyping = useCallback(() => {
		const now = Date.now();
		if (now - typingRef.current < 2500) return;
		typingRef.current = now;
		dealsAPI.chatTyping(dealId).catch(() => {});
	}, [dealId]);

	const send = useCallback(async (text, clientId = newClientId()) => {
		setPending(p => [...p.filter(x => x.client_id !== clientId), { client_id: clientId, text, status: 'sending' }]);
		try {
			const { data } = await dealsAPI.chatSend(dealId, text, clientId);
			merge([data]);
		} catch (e) {
			setPending(p => p.map(x => x.client_id === clientId ? { ...x, status: 'failed', error: e?.response?.data?.detail } : x));
		}
	}, [dealId, merge]);

	const upload = useCallback(async (file, caption, clientId = newClientId()) => {
		setPending(p => [...p.filter(x => x.client_id !== clientId), { client_id: clientId, text: caption || file.name, file, status: 'sending', progress: 0 }]);
		try {
			const { data } = await dealsAPI.chatUpload(dealId, file, caption, clientId,
				(pr) => setPending(p => p.map(x => x.client_id === clientId ? { ...x, progress: pr } : x)));
			merge([data]);
		} catch (e) {
			setPending(p => p.map(x => x.client_id === clientId ? { ...x, status: 'failed', error: e?.response?.data?.detail } : x));
		}
	}, [dealId, merge]);

	const retry = useCallback((item) => (item.file ? upload(item.file, item.text === item.file.name ? '' : item.text, item.client_id) : send(item.text, item.client_id)), [send, upload]);
	const discard = useCallback((cid) => setPending(p => p.filter(x => x.client_id !== cid)), []);

	return { messages, pending, ...state, hasOlder, loaded, error, loadOlder, markRead, notifyTyping, send, upload, retry, discard, refresh: poll };
}
