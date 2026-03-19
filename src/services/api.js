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

		if (error.response?.status === 401 && !originalRequest._retry) {
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

	create: (channelData) =>
		api.post('/channels', channelData),

	update: (id, channelData) =>
		api.put(`/channels/${id}`, channelData),

	delete: (id) =>
		api.delete(`/channels/${id}`),
};

// ===== Deals =====
export const dealsAPI = {
	create: (channelId) =>
		api.post('/deals', { channel_id: channelId }),

	getById: (id) =>
		api.get(`/deals/${id}`),

	getMy: () =>
		api.get('/deals/my'),

	confirmTransfer: (id) =>
		api.post(`/deals/${id}/confirm-transfer`),

	dispute: (id, reason) =>
		api.post(`/deals/${id}/dispute`, { reason }),

	getMessages: (id) =>
		api.get(`/deals/${id}/messages`),

	sendMessage: (id, text) =>
		api.post(`/deals/${id}/messages`, { text }),
};

// ===== Admin =====
export const adminAPI = {
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
};

// ===== Users =====
export const usersAPI = {
	getProfile: (id) =>
		api.get(`/users/${id}/profile`),

	getReviews: (id) =>
		api.get(`/users/${id}/reviews`),
};

export default api;
