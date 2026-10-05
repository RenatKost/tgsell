import { useEffect, useState } from 'react';
import { dealsAPI } from '../../services/api';

// Server timestamps are naive UTC — append Z so the browser shows local time.
const formatTime = (iso) => {
	if (!iso) return '';
	const s = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
	const d = new Date(s);
	if (Number.isNaN(d.getTime())) return '';
	return d.toLocaleString('uk-UA', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

const AutoBadge = ({ item }) => {
	if (item.auto_verified === null && !item.auto_note) return null;
	const cls =
		item.auto_verified === true
			? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
			: item.auto_verified === false
				? 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400'
				: 'bg-gray-100 text-gray-500 dark:bg-slate-700 dark:text-gray-300';
	const label = item.auto_verified === true ? 'Авто ✓' : item.auto_verified === false ? 'Авто ✗' : 'Авто ?';
	return (
		<div className='mt-1'>
			<span className={`inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded ${cls}`}>{label}</span>
			{item.auto_note && <span className='ml-1.5 text-[11px] text-gray-500 dark:text-gray-400'>{item.auto_note}</span>}
		</div>
	);
};

const SideCard = ({ side, editable, busyKey, onToggle, isMine }) => {
	const complete = side.required_done === side.required_total;
	return (
		<div className={`rounded-xl border-2 p-4 ${complete ? 'border-green-300 bg-green-50/50 dark:bg-green-900/10' : 'border-gray-200 dark:border-slate-600 bg-gray-50 dark:bg-slate-700/40'}`}>
			<div className='flex items-center justify-between mb-3'>
				<p className='font-semibold text-sm'>
					{side.label}{isMine && <span className='ml-1 text-xs font-normal text-gray-400'>(ви)</span>}
				</p>
				<div className='flex items-center gap-2'>
					{side.confirmed && (
						<span className='text-[10px] font-semibold px-1.5 py-0.5 rounded bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300'>
							Підтвердив
						</span>
					)}
					<span className={`text-xs font-bold ${complete ? 'text-green-600' : 'text-gray-500'}`}>
						{side.required_done}/{side.required_total}
					</span>
				</div>
			</div>
			<ul className='space-y-2.5'>
				{side.items.map((item) => (
					<li key={item.key} className='flex items-start gap-2.5'>
						{editable ? (
							<button
								type='button'
								onClick={() => onToggle(item)}
								disabled={busyKey !== null}
								aria-pressed={item.done}
								className={`mt-0.5 w-5 h-5 flex-shrink-0 rounded-md border-2 flex items-center justify-center text-xs font-bold transition-all disabled:opacity-50 ${
									item.done ? 'bg-green-500 border-green-500 text-white' : 'border-gray-300 dark:border-slate-500 bg-white dark:bg-slate-800 hover:border-green-400'
								}`}
							>
								{busyKey === item.key ? '…' : item.done ? '✓' : ''}
							</button>
						) : (
							<span className={`mt-0.5 w-5 h-5 flex-shrink-0 rounded-full flex items-center justify-center text-xs ${
								item.done ? 'bg-green-500 text-white' : 'bg-gray-200 dark:bg-slate-600 text-gray-400'
							}`}>
								{item.done ? '✓' : '·'}
							</span>
						)}
						<div className='min-w-0'>
							<p className={`text-sm leading-snug ${item.done ? 'text-gray-800 dark:text-gray-100' : 'text-gray-600 dark:text-gray-300'}`}>
								{item.label}
								{!item.required && <span className='ml-1 text-xs text-gray-400'>(необов’язково)</span>}
							</p>
							{item.hint && !item.done && <p className='text-[11px] text-gray-400 mt-0.5'>{item.hint}</p>}
							{item.done && item.done_at && (
								<p className='text-[11px] text-green-600 dark:text-green-400 mt-0.5'>Виконано {formatTime(item.done_at)}</p>
							)}
							<AutoBadge item={item} />
						</div>
					</li>
				))}
			</ul>
		</div>
	);
};

const TransferChecklist = ({ dealId, dealStatus, onChange, onLoaded, onError }) => {
	const [data, setData] = useState(null);
	const [busyKey, setBusyKey] = useState(null);
	const [verifying, setVerifying] = useState(false);
	const [verifyMsg, setVerifyMsg] = useState(null);

	const apply = (d) => {
		setData(d);
		onLoaded?.(d);
	};

	const load = async () => {
		try {
			const { data: d } = await dealsAPI.getChecklist(dealId);
			apply(d);
		} catch {
			// silent — deal page polls again
		}
	};

	useEffect(() => {
		load();
		const t = setInterval(load, 10000);
		return () => clearInterval(t);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [dealId, dealStatus]);

	const handleToggle = async (item) => {
		setBusyKey(item.key);
		try {
			const { data: d } = await dealsAPI.toggleChecklistItem(dealId, item.key, !item.done);
			apply(d);
			if (d.status !== dealStatus) onChange?.();
		} catch (err) {
			onError?.(err.response?.data?.detail || 'Не вдалося оновити пункт чек-листа');
		} finally {
			setBusyKey(null);
		}
	};

	const handleAutoVerify = async () => {
		setVerifying(true);
		setVerifyMsg(null);
		try {
			const { data: d } = await dealsAPI.autoVerifyChecklist(dealId);
			apply(d);
			setVerifyMsg(d.auto_verify_message || null);
		} catch (err) {
			onError?.(err.response?.data?.detail || 'Автоперевірка не вдалася');
		} finally {
			setVerifying(false);
		}
	};

	if (!data) {
		return <div className='text-sm text-gray-400 mb-5'>Завантаження чек-листа…</div>;
	}

	const mySide = data.my_side;
	const sides = mySide === 'buyer' ? [data.buyer, data.seller] : [data.seller, data.buyer];

	return (
		<div className='mb-5'>
			<div className='flex items-center justify-between gap-3 mb-3'>
				<h4 className='font-semibold text-sm'>Чек-лист передачі</h4>
				{data.active && (
					<button
						type='button'
						onClick={handleAutoVerify}
						disabled={verifying || !data.telethon_available}
						title={data.telethon_available ? 'Перевірити власника, адмінів і підписників через Telegram' : 'Автоперевірка тимчасово недоступна'}
						className='text-xs font-semibold px-3 py-1.5 rounded-lg border border-blue-200 text-blue-600 hover:bg-blue-50 dark:border-blue-800 dark:text-blue-300 dark:hover:bg-blue-900/20 disabled:opacity-40 transition-all'
					>
						{verifying ? 'Перевіряємо…' : 'Автоперевірка'}
					</button>
				)}
			</div>
			{verifyMsg && (
				<div className='text-xs text-blue-700 bg-blue-50 dark:bg-blue-900/20 dark:text-blue-300 rounded-lg px-3 py-2 mb-3'>{verifyMsg}</div>
			)}
			<div className='grid gap-3 md:grid-cols-2'>
				{sides.map((side) => (
					<SideCard
						key={side.side}
						side={side}
						isMine={mySide === side.side}
						editable={data.can_edit && mySide === side.side}
						busyKey={busyKey}
						onToggle={handleToggle}
					/>
				))}
			</div>
			<p className='text-[11px] text-gray-400 mt-2'>
				Виплата продавцю стане доступною лише після виконання всіх обов’язкових пунктів обома сторонами та підтвердження передачі.
				Автоперевірка — лише підказка і не замінює ручну перевірку.
			</p>
		</div>
	);
};

export default TransferChecklist;
