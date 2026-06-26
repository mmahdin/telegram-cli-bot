import axios from 'axios';

const DEFAULT_BASE_URL = 'http://localhost:8000';
export const BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/$/, '');

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 20000,
});

export const absoluteUrl = (path?: string | null) => {
  if (!path) return null;
  if (/^https?:\/\//i.test(path) || path.startsWith('data:')) return path;
  return `${BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
};

export const checkAuthStatus = () => api.get('/auth/status');
export const connectExistingSession = () => api.post('/auth/connect');
export const login = (data: { phone?: string; code?: string; password?: string }) => api.post('/auth/login', data);
export const logout = () => api.post('/auth/logout');

export const getDialogs = (limit = 80) => api.get(`/dialogs?limit=${limit}`);
export const syncDialogs = (limit = 80) => api.post(`/dialogs/sync?limit=${limit}`);
export const setDialogImportance = (chatId: number, important: boolean) =>
  api.patch(`/dialogs/${chatId}/importance`, { important });
export const syncAvatars = (limit = 12) => api.post(`/avatars/sync?limit=${limit}`);

export const getMessages = (userId: number, limit = 50, offsetId = 0, afterId = 0) =>
  api.get(`/messages/${userId}?limit=${limit}&offset_id=${offsetId}&after_id=${afterId}`);

export const syncMessages = (
  userId: number,
  limit = 60,
  offsetId = 0,
  afterId = 0,
  markRead = false,
) => api.post(`/messages/${userId}/sync?limit=${limit}&offset_id=${offsetId}&after_id=${afterId}&mark_read=${markRead}`);

export const markDialogRead = (userId: number) => api.post(`/messages/${userId}/read`);

export const sendMessage = (userId: number, text: string, replyTo?: number) =>
  api.post(`/messages/${userId}/send`, { text, reply_to: replyTo });

export const sendPhoto = (userId: number, file: File, caption = '', replyTo?: number) => {
  const form = new FormData();
  form.append('file', file);
  form.append('caption', caption);
  if (replyTo) form.append('reply_to', String(replyTo));
  return api.post(`/messages/${userId}/send-photo`, form);
};

export const sendAudio = (userId: number, file: File, caption = '', replyTo?: number) => {
  const form = new FormData();
  form.append('file', file);
  form.append('caption', caption);
  if (replyTo) form.append('reply_to', String(replyTo));
  return api.post(`/messages/${userId}/send-audio`, form);
};

export const editMessage = (userId: number, messageId: number, newText: string) =>
  api.put(`/messages/${userId}/${messageId}`, { new_text: newText });

export const deleteMessage = (userId: number, messageId: number) => api.delete(`/messages/${userId}/${messageId}`);
