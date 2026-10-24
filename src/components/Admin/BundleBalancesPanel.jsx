import { fmtNum } from '../../utils/money';
// Task 32: staff (admin / moderator) edit per-channel balances of any bundle.
import { useEffect, useState } from 'react';
import { adminAPI } from '../../services/api';
import BalanceBadges from '../Balance/BalanceBadges';
import BundleBalanceEditor from '../Balance/BundleBalanceEditor';

const STATUS = { pending: 'На модерації', approved: 'Опублікована', rejected: 'Відхилена', sold: 'Продана' };

const BundleBalancesPanel = () => {
	const [items, setItems] = useState([]);
	const [search, setSearch] = useState('');
	const [err, setErr] = useState('');
	const [loading, setLoading] = useState(false);
	const [editing, setEditing] = useState(null);

	const load = async (q = search) => {
		setLoading(true);
		try {
			const { data } = await adminAPI.listBundles(q ? { search: q } : {});
			setItems(data.items || []); setErr('');
		} catch (e) {
			setErr(e?.response?.data?.detail || 'Помилка завантаження');
		} finally { setLoading(false); }
	};
	useEffect(() => { load(''); }, []);

	const save = async (channel_balances) => {
		const { data } = await adminAPI.updateBundleBalances(editing.id, channel_balances);
		setItems(prev => prev.map(b => (b.id === data.id ? data : b)));
	};

	return (
		<div className='space-y-4'>
			<div className='flex items-center justify-between gap-3 flex-wrap'>
				<h1 className='text-2xl font-bold text-white'>Баланси сіток</h1>
				<form className='flex gap-2' onSubmit={e => { e.preventDefault(); load(search.trim()); }}>
					<input value={search} onChange={e => setSearch(e.target.value)} placeholder='Назва або #id сітки'
						className='bg-card-inner border border-card-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-accent/50' />
					<button type='submit' className='px-4 py-2 rounded-lg bg-accent text-black font-bold text-sm'>Знайти</button>
				</form>
			</div>
			<p className='text-sm text-gray-400'>
				Модератори та адміністратори можуть змінювати баланс у будь-який час (дія записується в журнал).
				Існуючі угоди зберігають баланс, зафіксований при їх створенні.
			</p>
			{err && <div className='text-sm text-red-400'>{err}</div>}
			{loading ? <div className='text-center py-10 text-gray-400'>Завантаження...</div> : items.length === 0 ? (
				<div className='text-center py-10 text-gray-400'>Сіток не знайдено</div>
			) : (
				<div className='space-y-3'>
					{items.map(b => (
						<div key={b.id} className='bg-card border border-card-border rounded-xl p-4'>
							<div className='flex items-start justify-between gap-3'>
								<div>
									<div className='font-bold text-white'>📡 #{b.id} {b.name}</div>
									<div className='text-xs text-gray-400'>
										{STATUS[b.status] || b.status} · продавець id={b.seller_id} · {fmtNum(b.price)} USDT
										{b.has_active_deal && <span className='ml-2 text-yellow-400'>є активна угода</span>}
									</div>
								</div>
								<button onClick={() => setEditing(b)}
									className='px-3 py-1.5 rounded-lg text-xs font-semibold bg-card-inner text-accent border border-card-border whitespace-nowrap'>
									Редагувати баланс
								</button>
							</div>
							<ul className='mt-2 space-y-1'>
								{b.channels.map(c => (
									<li key={c.id} className='text-xs text-gray-300 flex items-center gap-2 flex-wrap'>
										<span>{c.channel_name || c.telegram_link}</span>
										<BalanceBadges stars={c.stars_balance} ton={c.ton_balance} size='xs' caption={false} />
									</li>
								))}
							</ul>
						</div>
					))}
				</div>
			)}
			{editing && (
				<BundleBalanceEditor
					title={`Баланс каналів — сітка #${editing.id}`}
					channels={editing.channels}
					note={editing.has_active_deal ? 'По сітці є активна угода: її зафіксований баланс не зміниться.' : ''}
					onSave={save}
					onClose={() => setEditing(null)}
				/>
			)}
		</div>
	);
};

export default BundleBalancesPanel;
