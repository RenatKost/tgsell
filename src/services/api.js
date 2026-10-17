import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

const api = axios.create({
	baseURL: API_URL,
	headers: {
		'Content-Type': 'application/json',
	},
});

// Request interceptor — attach JWT token
api.interceptors.request.use((config) => {
	const token = localStorage.getItem('access_token');
	if (token) {
		config.headers.Authorization = `Bearer ${token}`;
	}
	return config;
});

// Response interceptor — handle 401 and token refresh
api.interceptors.response.use(
	(response) => response,
	async (error) => {
		const originalRequest = error.config;

		// Skip 401 handling for auth endpoints (login, register)
		const isAuthEndpoint = originalRequest?.url?.includes('/auth/telegram') ||
			originalRequest?.url?.includes('/auth/google') ||
			originalRequest?.url?.includes('/auth/bot-check') ||
			originalRequest?.url?.includes('/auth/refresh');

		if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
			originalRequest._retry = true;

			try {
				const refreshToken = localStorage.getItem('refresh_token');
				if (!refreshToken) {
					throw new Error('No refresh token');
				}

				const { data } = await axios.post(`${API_URL}/auth/refresh`, {
					refresh_token: refreshToken,
				});

				localStorage.setItem('access_token', data.access_token);
				localStorage.setItem('refresh_token', data.refresh_token);

				originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
				return api(originalRequest);
			} catch (refreshError) {
				localStorage.removeItem('access_token');
				localStorage.removeItem('refresh_token');
				window.location.href = '/';
				return Promise.reject(refreshError);
			}
		}

		return Promise.reject(error);
	}
);

// ===== Auth =====
export const authAPI = {
	loginTelegram: (telegramData) =>
		api.post('/auth/telegram', telegramData),

	loginGoogle: (credential) =>
		api.post('/auth/google', { credential }),

	linkTelegram: (telegramData) =>
		api.post('/auth/link/telegram', telegramData),

	createBotToken: () =>
		api.post('/auth/bot-token'),

	checkBotAuth: (token) =>
		api.get('/auth/bot-check', { params: { token } }),

	getMe: () =>
		api.get('/auth/me'),

	refresh: (refreshToken) =>
		api.post('/auth/refresh', { refresh_token: refreshToken }),
};

// ===== Channels =====
export const channelsAPI = {
	getAll: (params = {}) =>
		api.get('/channels', { params }),

	getById: (id) =>
		api.get(`/channels/${id}`),

	getStats: (id) =>
		api.get(`/channels/${id}/stats`),

	getPosts: (id, params = {}) =>
		api.get(`/channels/${id}/posts`, { params }),

	getHealth: (id) =>
		api.get(`/channels/${id}/health`),

	getAiAnalysis: (id) =>
		api.get(`/channels/${id}/ai-analysis`, { timeout: 55000 }),

	create: (channelData) =>
		api.post('/channels', channelData),

	update: (id, channelData) =>
		api.put(`/channels/${id}`, channelData),

	delete: (id) =>
		api.delete(`/channels/${id}`),
};

// ===== Deals =====
export const dealsAPI = {
	tgNotify: (id) => api.get(`/deals/${id}/tg-notify`),
	chatPoll: (id, afterId = 0) => api.get(`/deals/${id}/chat`, { params: { after_id: afterId } }),
	chatHistory: (id, beforeId) => api.get(`/deals/${id}/chat/history`, { params: { before_id: beforeId } }),
	chatSend: (id, text, clientId) => api.post(`/deals/${id}/chat/messages`, { text, client_id: clientId }),
	chatRead: (id, messageId) => api.post(`/deals/${id}/chat/read`, { message_id: messageId }),
	chatTyping: (id) => api.post(`/deals/${id}/chat/typing`),
	chatUpload: (id, file, caption, clientId, onProgress) => {
		const fd = new FormData();
		fd.append('file', file);
		if (caption) fd.append('caption', caption);
		if (clientId) fd.append('client_id', clientId);
		return api.post(`/deals/${id}/chat/attachments`, fd, {
			headers: { 'Content-Type': 'multipart/form-data' },
			onUploadProgress: (e) => onProgress?.(e.total ? Math.round((e.loaded / e.total) * 100) : 0),
		});
	},
	chatAttachment: (id, attId, thumb = false) =>
		api.get(`/deals/${id}/chat/attachments/${attId}`, { params: { thumb }, responseType: 'blob' }),
	chatUnread: (ids) => api.get('/deals/my/unread', { params: ids ? { ids: ids.join(',') } : {} }),

	create: (channelId, bundleId = null) =>
		api.post('/deals', bundleId ? { bundle_id: bundleId } : { channel_id: channelId }),

	getById: (id) =>
		api.get(`/deals/${id}`),

	getMy: () =>
		api.get('/deals/my'),

	confirmTransfer: (id) =>
		api.post(`/deals/${id}/confirm-transfer`),

	confirmReady: (id) =>
		api.post(`/deals/${id}/confirm-ready`),

	confirmChannelTransfer: (id) =>
		api.post(`/deals/${id}/confirm-channel-transfer`),

	payoutStatus: (id) => api.get(`/deals/${id}/payout-status`),
	setSellerWallet: (id, walletAddress) =>
		api.post(`/deals/${id}/seller-wallet`, { wallet_address: walletAddress }),

	setOverpayRefundAddress: (id, walletAddress) =>
		api.post(`/deals/${id}/overpay-refund-address`, { wallet_address: walletAddress }),

	callAdmin: (id) =>
		api.post(`/deals/${id}/call-admin`),

	dispute: (id, reason) =>
		api.post(`/deals/${id}/dispute`, { reason }),

	getMessages: (id) =>
		api.get(`/deals/${id}/messages`),

	sendMessage: (id, text) =>
		api.post(`/deals/${id}/messages`, { text }),

	// Transfer checklist
	getChecklist: (id) =>
		api.get(`/deals/${id}/checklist`),

	toggleChecklistItem: (id, key, done) =>
		api.post(`/deals/${id}/checklist/${key}`, typeof done === 'boolean' ? { done } : {}),

	// Task 31: buyer reports the stated Stars/TON balance is missing → dispute
	reportBalanceMismatch: (id) =>
		api.post(`/deals/${id}/checklist/balance-mismatch`),

	autoVerifyChecklist: (id) =>
		api.post(`/deals/${id}/checklist/auto-verify`, null, { timeout: 40000 }),
};

// ===== Admin =====
export const adminAPI = {
	listUsers: (params) => api.get('/admin/users', { params }),
	getUser: (id) => api.get(`/admin/users/${id}`),
	blockUser: (id, reason) => api.post(`/admin/users/${id}/block`, { reason }),
	unblockUser: (id) => api.post(`/admin/users/${id}/unblock`),
	setUserRole: (id, role) => api.post(`/admin/users/${id}/role`, null, { params: { role } }),
	dealBlockedParty: (dealId, action, note) => api.post(`/admin/deals/${dealId}/blocked-party`, { action, note }),
	inactiveChannels: () => api.get('/admin/channels/inactive'),
	removeChannel: (id, reason) => api.post(`/admin/channels/${id}/remove`, { confirm: true, reason: reason || null }),
	auditLog: (params) => api.get('/admin/audit-log', { params }),
	transactions: (params) => api.get('/admin/transactions', { params }),
	transactionsCsv: (params) => api.get('/admin/transactions', { params: { ...params, format: 'csv', limit: 500 }, responseType: 'blob' }),
	payoutQueue: () => api.get('/admin/payout-queue'),
	recheckTx: (id) => api.post(`/admin/transactions/${id}/recheck`),
	markTxFailed: (id, note) => api.post(`/admin/transactions/${id}/mark-failed`, { note }),
	escrowOverview: (refresh = false) => api.get('/admin/escrow/overview', { params: { refresh } }),
	gas: (params) => api.get('/admin/gas', { params }),
	summary: (date) => api.get('/admin/summary', { params: date ? { date } : {} }),

	getDashboardStats: () =>
		api.get('/admin/dashboard-stats'),

	getPendingChannels: () =>
		api.get('/admin/channels/pending'),

	getAllChannels: (params = {}) =>
		api.get('/admin/channels', { params }),

	approveChannel: (id) =>
		api.post(`/admin/channels/${id}/approve`),

	rejectChannel: (id, reason) =>
		api.post(`/admin/channels/${id}/reject`, { reason }),

	updateChannel: (id, data) =>
		api.put(`/admin/channels/${id}`, data),

	deleteChannel: (id) =>
		api.delete(`/admin/channels/${id}`),

	getAllDeals: (params = {}) =>
		api.get('/admin/deals', { params }),

	resolveDeal: (id, resolution) =>
		api.post(`/admin/deals/${id}/resolve`, resolution),

	cancelDeal: (id) =>
		api.post(`/admin/deals/${id}/cancel`),

	getEscrowBalances: (refresh = false) =>
		api.get('/admin/escrow/balances', { params: refresh ? { refresh: true } : {} }),

	collectFee: (dealId) => api.post(`/admin/deals/${dealId}/collect-fee`),
	feeSweepCollectAll: () => api.post('/admin/fee-sweep/collect-all'),
	overpayRefunds: () => api.get('/admin/overpay-refunds'),
	retryOverpayRefund: (dealId) => api.post(`/admin/deals/${dealId}/overpay-refund/retry`),
	payoutStatus: (dealId) => api.get(`/admin/deals/${dealId}/payout-status`),
	masterBalance: () => api.get('/admin/escrow/master-balance'),
	sweepEscrow: (dealId, toAddress) =>
		api.post(`/admin/escrow/sweep/${dealId}`, { to_address: toAddress }),

	// Auction management
	getAuctions: (params = {}) =>
		api.get('/admin/auctions', { params }),

	cancelAuction: (id) =>
		api.post(`/admin/auctions/${id}/cancel`),

	extendAuction: (id, hours) =>
		api.post(`/admin/auctions/${id}/extend`, { hours }),

	updateAuction: (id, data) =>
		api.put(`/admin/auctions/${id}`, data),

	deleteAuction: (id) =>
		api.delete(`/admin/auctions/${id}`),

	// Channel stats
	refreshChannelStats: (channelId) =>
		api.post(`/admin/channels/${channelId}/refresh-stats`),

	getTelegramDiagnostics: () =>
		api.get('/admin/diagnostics/telegram'),

	// Activity config
	getActivityConfig: () =>
		api.get('/admin/activity-config'),

	updateActivityConfig: (config) =>
		api.put('/admin/activity-config', config),

	// Telethon re-auth
	getReauthStatus: () =>
		api.get('/admin/reauth/status'),

	reauthStart: () =>
		api.post('/admin/reauth/start'),

	reauthConfirm: (code, password) =>
		api.post('/admin/reauth/confirm', { code, ...(password ? { password } : {}) }),

	runStatsNow: () =>
		api.post('/admin/run-stats-now'),

	getPendingBundles: () =>
		api.get('/admin/bundles/pending'),

	approveBundle: (id) =>
		api.post(`/admin/bundles/${id}/approve`),

	rejectBundle: (id, reason) =>
		api.post(`/admin/bundles/${id}/reject`, null, { params: { reason } }),
};

// ===== Task 24: similar channels + saved searches =====
export const similarAPI = {
	get: (channelId) => api.get(`/channels/${channelId}/similar`),
};

export const savedSearchesAPI = {
	getAll: () => api.get('/saved-searches'),
	create: (body) => api.post('/saved-searches', body),
	remove: (id) => api.delete(`/saved-searches/${id}`),
};

// ===== Favorites =====
export const favoritesAPI = {
	getAll: () =>
		api.get('/favorites'),

	getIds: () =>
		api.get('/favorites/ids'),

	add: (channelId) =>
		api.post(`/favorites/${channelId}`),

	remove: (channelId) =>
		api.delete(`/favorites/${channelId}`),
};

// ===== Auctions =====
export const auctionsAPI = {
	getAll: (params = {}) =>
		api.get('/auctions', { params }),

	getById: (id) =>
		api.get(`/auctions/${id}`),

	bid: (id, data) =>
		api.post(`/auctions/${id}/bid`, data),

	getStats: () =>
		api.get('/auctions/stats'),

	createFromChannel: (params) =>
		api.post('/auctions/from-channel', null, { params }),
};

// ===== Bundles =====
export const bundlesAPI = {
	getAll: (params = {}) =>
		api.get('/bundles', { params }),

	getById: (id) =>
		api.get(`/bundles/${id}`),

	getStats: (id) =>
		api.get(`/bundles/${id}/stats`),

	getAiAnalysis: (id) =>
		api.get(`/bundles/${id}/ai-analysis`, { timeout: 55000 }),

	create: (data) =>
		api.post('/bundles', data),

	update: (id, data) =>
		api.put(`/bundles/${id}`, data),

	delete: (id) =>
		api.delete(`/bundles/${id}`),
};

// ===== Activity / Gamification =====
export const activityAPI = {
	getStats: () =>
		api.get('/stats/activity'),

	getFeed: () =>
		api.get('/stats/feed'),
};

// ===== Users =====
export const usersAPI = {
	getProfile: (id) =>
		api.get(`/users/${id}/profile`),

	getReviews: (id) =>
		api.get(`/users/${id}/reviews`),
};

// ===== Task 23: first-party tracking (no PII) + admin activity =====
export const trackingAPI = {
	event: (body) => api.post('/track/event', body),
	heartbeat: (body) => api.post('/track/heartbeat', body),
};

export const userActivityAPI = {
	users: (params) => api.get('/admin/activity/users', { params }),
	funnel: () => api.get('/admin/activity/funnel'),
};

export default api;
