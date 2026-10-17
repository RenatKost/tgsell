// Task 32: edit a bundle's per-channel seller-stated Stars / TON balances.
// Used by the seller cabinet (only while the bundle has no active deal — enforced
// server-side) and by the admin panel (staff can always edit).
// Existing deals keep their creation-time snapshot; this never changes them.
import { useState } from 'react';

const toInput = (v) => (v === null || v === undefined ? '' : String(v));

export const buildChannelBalances = (rows) => rows.map(r => ({
	channel_id: r.id,
	stars_balance: r.stars === '' ? null : parseInt(r.stars, 10),
	ton_balance: r.ton === '' ? null : Number(r.ton),
}));

export const validateRows = (rows) => {
	for (const r of rows) {
		if (r.stars !== '' && !/^\d+$/.test(String(r.stars).trim())) {
			return `Stars для «${r.name}» — ціле число ≥ 0`;
		}
		if (r.ton !== '' && (!Number.isFinite(Number(r.ton)) || Number(r.ton) < 0)) {
			return `TON для «${r.name}» — число ≥ 0`;
		}
	}
	return '';
};

const BundleBalanceEditor = ({ title, channels = [], onSave, onClose, note }) => {
	const [rows, setRows] = useState(() => channels.map(c => ({
		id: c.id,
		name: c.channel_name || c.telegram_link || `#${c.id}`,
		stars: toInput(c.stars_balance),
		ton: toInput(c.ton_balance),
	})));
	const [err, setErr] = useState('');
	const [saving, setSaving] = useState(false);

	const setField = (id, field, value) =>
		setRows(prev => prev.map(r => (r.id === id ? { ...r, [field]: value } : r)));

	const save = async () => {
		const v = validateRows(rows);
		if (v) { setErr(v); return; }
		setSaving(true); setErr('');
		try {
			await onSave(buildChannelBalances(rows));
			onClose?.();
		} catch (e) {
			setErr(e?.response?.data?.detail || 'Не вдалося зберегти баланс');
		} finally {
			setSaving(false);
		}
	};

	return (
		<div className='fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4' onClick={onClose}>
			<div className='w-full max-w-lg bg-card border border-card-border rounded-2xl p-5 shadow-neon max-h-[90vh] overflow-y-auto'
				onClick={e => e.stopPropagation()} data-testid='bundle-balance-editor'>
				<h3 className='text-lg font-bold text-white mb-1'>{title || 'Баланс каналів сітки'}</h3>
				<p className='text-xs text-gray-500 mb-4'>
					Баланс Telegram Stars / TON кожного каналу — зі слів продавця. Порожнє поле — баланс не вказано.
					{' '}Існуючі угоди зберігають баланс, зафіксований при їх створенні.
				</p>
				{note && <p className='text-xs text-yellow-400 mb-3'>{note}</p>}
				<div className='space-y-3'>
					{rows.map(r => (
						<div key={r.id} className='bg-card-inner border border-card-border rounded-xl p-3'>
							<div className='text-sm text-white font-semibold mb-2 truncate'>{r.name}</div>
							<div className='grid grid-cols-2 gap-2'>
								<label className='text-xs text-gray-400'>
									⭐ Stars
									<input type='number' min='0' step='1' inputMode='numeric' value={r.stars}
										onChange={e => setField(r.id, 'stars', e.target.value)}
										className='mt-1 w-full bg-card border border-card-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent/50' />
								</label>
								<label className='text-xs text-gray-400'>
									💎 TON
									<input type='number' min='0' step='any' inputMode='decimal' value={r.ton}
										onChange={e => setField(r.id, 'ton', e.target.value)}
										className='mt-1 w-full bg-card border border-card-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent/50' />
								</label>
							</div>
						</div>
					))}
				</div>
				{err && <div className='text-sm text-red-400 mt-3'>{err}</div>}
				<div className='flex gap-2 mt-4'>
					<button onClick={save} disabled={saving || rows.length === 0}
						className='flex-1 px-4 py-2 rounded-lg bg-accent text-black font-bold text-sm hover:brightness-110 disabled:opacity-50'>
						{saving ? 'Збереження…' : 'Зберегти'}
					</button>
					<button onClick={onClose}
						className='px-4 py-2 rounded-lg bg-card-inner text-gray-300 text-sm border border-card-border'>
						Скасувати
					</button>
				</div>
			</div>
		</div>
	);
};

export default BundleBalanceEditor;
