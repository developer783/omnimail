const API_BASE = ''; // Uses Vite proxy in development

export const getStoredToken = () => localStorage.getItem('auth_token');
export const setStoredToken = (token) => localStorage.setItem('auth_token', token);
export const removeStoredToken = () => localStorage.removeItem('auth_token');

async function request(endpoint, options = {}) {
  const token = getStoredToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    credentials: 'include', // Include httpOnly cookies if set
  });

  if (response.status === 401) {
    removeStoredToken();
    if (window.location.pathname !== '/login') {
      window.dispatchEvent(new Event('auth_unauthorized'));
    }
  }

  if (!response.ok) {
    let errorMsg = 'An error occurred';
    try {
      const errorData = await response.json();
      errorMsg = errorData.detail || errorData.message || errorMsg;
    } catch (e) {
      errorMsg = response.statusText || errorMsg;
    }
    throw new Error(errorMsg);
  }

  return response.json();
}

export const api = {
  login: async (username, password) => {
    const data = await request('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    if (data.access_token) {
      setStoredToken(data.access_token);
    }
    return data;
  },

  getCurrentUser: () => request('/auth/me'),

  logout: async () => {
    try {
      await request('/auth/logout', { method: 'POST' });
    } catch (e) {
      // Ignore network errors on logout
    }
    removeStoredToken();
  },

  getAccounts: () => request('/accounts'),

  deleteAccount: (accountId) =>
    request(`/accounts/${accountId}`, { method: 'DELETE' }),

  getGoogleOAuthUrl: async () => {
    const data = await request('/auth/google/start?json=true');
    return data.url;
  },

  demoConnectAccount: (email = 'recruiter.team@gmail.com') =>
    request(`/auth/google/demo_connect?email=${encodeURIComponent(email)}`, {
      method: 'POST',
    }),

  getEmails: (accountId = null, folder = 'inbox', searchQuery = '') => {
    const params = new URLSearchParams();
    if (accountId) params.append('account_id', accountId);
    if (folder) params.append('folder', folder);
    if (searchQuery) params.append('q', searchQuery);
    return request(`/emails?${params.toString()}`);
  },

  getEmailById: (id) => request(`/emails/${id}`),

  updateEmailStatus: (id, updateData) =>
    request(`/emails/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(updateData),
    }),

  replyToEmail: (id, replyData) =>
    request(`/emails/${id}/reply`, {
      method: 'POST',
      body: JSON.stringify(replyData),
    }),

  forwardEmail: (id, forwardData) =>
    request(`/emails/${id}/forward`, {
      method: 'POST',
      body: JSON.stringify(forwardData),
    }),

  getFilters: () => request('/filters'),

  createFilter: (keyword, field = 'any') =>
    request('/filters', {
      method: 'POST',
      body: JSON.stringify({ keyword, field }),
    }),

  deleteFilter: (filterId) =>
    request(`/filters/${filterId}`, { method: 'DELETE' }),

  syncEmails: () => request('/emails/sync', { method: 'POST' }),
};
