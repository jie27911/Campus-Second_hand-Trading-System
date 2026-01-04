import axios from 'axios';
import { createDiscreteApi } from 'naive-ui';

// ✅ 使用与 auth.ts 一致的 key
const TOKEN_KEY = 'campuswap_token';
const USER_KEY = 'campuswap_user';

// 创建 axios 实例
export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 10000,
});

function formatFastApiDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;

  if (Array.isArray(detail)) {
    // Typical FastAPI validation error format
    return detail
      .map((entry: any) => {
        const loc = Array.isArray(entry?.loc) ? entry.loc.slice(1).join('.') : entry?.loc;
        const msg = entry?.msg ?? '参数错误';
        if (loc) return `${loc}: ${msg}`;
        return String(msg);
      })
      .filter(Boolean)
      .join('；');
  }

  if (detail && typeof detail === 'object') {
    try {
      return JSON.stringify(detail);
    } catch {
      return '请求失败';
    }
  }

  return '请求失败';
}

// 请求拦截器：自动带上 Token
http.interceptors.request.use(
  (config) => {
    // ✅ 修复：使用正确的 key
    const token = localStorage.getItem(TOKEN_KEY);

    console.log('🔑 Token:', token ? `${token.substring(0, 30)}...` : '未找到');

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// 响应拦截器：处理 Token 过期 (401)
http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      // ✅ 修复：使用正确的 key
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);

      const { message } = createDiscreteApi(['message']);
      message.error('登录已过期，请重新登录');

      window.location.href = '/login';

      return Promise.reject(error);
    }

    const { message } = createDiscreteApi(['message']);
  const rawDetail = error.response?.data?.detail;
  const errorMsg = formatFastApiDetail(rawDetail) || error.message || '网络错误';

    if (!window.location.pathname.includes('/login')) {
      message.error(errorMsg);
    }

    return Promise.reject(error);
  },
);
