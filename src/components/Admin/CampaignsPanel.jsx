import { useCallback, useEffect, useState } from 'react';
import { utmAPI } from '../../services/api';

const box = 'bg-white dark:bg-slate-800 rounded-2xl border border-gray-100 dark:border-slate-700 p-5';
const input = 'rounded-xl border border-gray-200 dark:border-slate-600 bg-white dark:bg-slate-900 px-3 py-2 text-sm text-gray-800 dark:text-gray-100';
const pct = (a, b) => (b ? `${Math.round((a / b) * 1000) / 10}%` : '—');
const TZ = 'Europe/Kyiv';
const UA_LABELS = { ig_inapp: 'Instagram (вбудований)', fb_inapp: 'Facebook (вбудований)', tg_inapp: 'Telegram (вбудований)', mobile: 'Мобільний браузер', desktop: 'Компʼютер', bot: 'Боти', unknown: 'Невідомо (до 31.10)' };
// offset (ms) of Europe/Kyiv at the instant ms
const tzOffset = (ms) => {
	const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: TZ, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
		.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
	return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second) - Math.floor(ms / 1000) * 1000;
};
/** 'YYYY-MM-DDTHH:mm' wall time in Kyiv → UTC ISO string (with Z). */
export const kyivToUtcIso = (local) => {
	const guess = Date.parse(`${local}:00Z`);
	if (Number.isNaN(guess)) return null;
	let t = guess - tzOffset(guess);
	t = guess - tzOffset(t);
	return new Date(t).toISOString();
};
const COLS = [
	['visits', 'Візити'], ['visitors', 'Унікальні'], ['sell_open', 'Відкрили форму'],
	['sell_open_auto', '…з них авто'], ['sell_open_manual', '…вручну'], ['step1_next', 'Крок 1 «Далі»'],
	['form_start', 'Почали форму'], ['form_submit_attempt', 'Спроба подати'], ['login_click', 'Тап «Увійти»'],
	['bot_start', 'Старт бота'], ['login_success', 'Вхід успішний'],
	['registrations', 'Реєстрації'], ['lots_submitted', 'Лоти подано'], ['lots_approved', 'Лоти схвалено'],
];

/** Admin «Кампанії»: UTM visits → registrations → lots submitted → lots approved. */
const CampaignsPanel = () => {
	const [from, setFrom] = useState('');
	const [to, setTo] = useState('');
	const [data, setData] = useState(null);
	const [byUa, setByUa] = useState(false);
	const [err, setErr] = useState('');
	const load = useCallback(() => {
		setErr('');
		const params = {};
		if (from) params.date_from = kyivToUtcIso(from);
		if (to) params.date_to = kyivToUtcIso(to);
		utmAPI.campaigns(params).then((r) => setData(r.data))
			.catch((e) => setErr(typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : 'Помилка запиту'));
	}, [from, to]);
	useEffect(() => { load(); }, [load]);
	const t = data?.totals;
	return (
		<div className='space-y-4'>
			<div className={box}>
				<h2 className='text-lg font-bold text-gray-800 dark:text-white mb-1'>Кампанії (UTM)</h2>
				<p className='text-xs text-gray-500 dark:text-gray-400 mb-3'>Перший дотик: utm_source / utm_campaign / utm_content. Лоти = окремі канали + сітки. Дати — за датою візиту/реєстрації/подання. Воронка (відкрили форму → «Далі» → почали форму → тап «Увійти» → старт бота → вхід) — унікальні відвідувачі на кожному кроці; дані з 29.10. Час — за Києвом (кінець періоду не включно). Авто/вручну та тип пристрою для подій — з 31.10 (раніші події: «вручну» / «Невідомо»).</p>
				<div className='flex flex-wrap items-end gap-2'>
					<label className='text-xs text-gray-500'>Від (Київ)<br /><input type='datetime-local' className={input} value={from} onChange={(e) => setFrom(e.target.value)} /></label>
					<label className='text-xs text-gray-500'>До (Київ)<br /><input type='datetime-local' className={input} value={to} onChange={(e) => setTo(e.target.value)} /></label>
					<label className='text-sm text-gray-500 flex items-center gap-1'><input type='checkbox' checked={byUa} onChange={(e) => setByUa(e.target.checked)} /> За типом пристрою</label>
					{(from || to) && <button type='button' className='text-sm underline text-gray-500' onClick={() => { setFrom(''); setTo(''); }}>Скинути</button>}
				</div>
				{err && <p className='text-sm text-red-500 mt-2'>{err}</p>}
			</div>
			<div className={`${box} overflow-x-auto`}>
				{!data ? <p className='text-sm text-gray-400'>Завантаження…</p> : data.items.length === 0 ? (
					<p className='text-sm text-gray-400'>Немає даних за обраний період.</p>
				) : (
					<table className='w-full text-xs text-left text-gray-700 dark:text-gray-200' data-campaigns-table>
						<thead>
							<tr className='text-gray-400'>
								<th className='py-1 pr-3'>Кампанія</th><th className='py-1 pr-3'>Джерело</th><th className='py-1 pr-3'>Контент</th>
								{COLS.map(([k, l]) => <th key={k} className='py-1 pr-3 text-right'>{l}</th>)}
								<th className='py-1 text-right'>Візит→лот</th>
							</tr>
						</thead>
						<tbody>
							{data.items.map((i) => {
								const k0 = `${i.utm_source}|${i.utm_campaign}|${i.utm_content}`;
								return [
									<tr key={k0} className='border-t border-gray-100 dark:border-slate-700'>
										<td className='py-1 pr-3 font-semibold'>{i.utm_campaign || '—'}</td>
										<td className='py-1 pr-3'>{i.utm_source || '—'}</td>
										<td className='py-1 pr-3'>{i.utm_content || '—'}</td>
										{COLS.map(([k]) => <td key={k} className='py-1 pr-3 text-right tabular-nums'>{i[k] ?? 0}</td>)}
										<td className='py-1 text-right tabular-nums'>{pct(i.lots_submitted, i.visitors)}</td>
									</tr>,
									...(byUa ? Object.entries(i.by_ua || {}).map(([ua, v]) => (
										<tr key={`${k0}|${ua}`} className='text-gray-500' data-ua-row={ua}>
											<td className='py-0.5 pr-3 pl-4' colSpan={3}>↳ {UA_LABELS[ua] || ua}</td>
											{COLS.map(([k]) => <td key={k} className='py-0.5 pr-3 text-right tabular-nums'>{v[k] ?? ''}</td>)}
											<td />
										</tr>
									)) : []),
								];
							})}
							<tr className='border-t-2 border-gray-200 dark:border-slate-600 font-bold'>
								<td className='py-1 pr-3' colSpan={3}>Разом</td>
								{COLS.map(([k]) => <td key={k} className='py-1 pr-3 text-right tabular-nums'>{t[k] ?? 0}</td>)}
								<td className='py-1 text-right tabular-nums'>{pct(t.lots_submitted, t.visitors)}</td>
							</tr>
						</tbody>
					</table>
				)}
			</div>
		</div>
	);
};

export default CampaignsPanel;
