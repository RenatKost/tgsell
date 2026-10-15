import { useState } from 'react';
import UserActivityPanel from './UserActivityPanel';
import UsersModerationPanel from './UsersModerationPanel';

const UsersPanel = () => {
	const [tab, setTab] = useState('activity');
	return (
		<div className='space-y-4'>
			<div className='flex gap-2'>
				<button onClick={() => setTab('activity')} className={`px-4 py-2 rounded-xl text-sm font-semibold ${tab === 'activity' ? 'bg-[#3498db] text-white' : 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-200'}`}>Активність</button>
				<button onClick={() => setTab('moderation')} className={`px-4 py-2 rounded-xl text-sm font-semibold ${tab === 'moderation' ? 'bg-[#3498db] text-white' : 'bg-gray-100 dark:bg-slate-700 text-gray-700 dark:text-gray-200'}`}>Модерація</button>
			</div>
			{tab === 'activity' ? <UserActivityPanel /> : <UsersModerationPanel />}
		</div>
	);
};

export default UsersPanel;
