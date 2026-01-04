import { defineStore } from 'pinia';
import { http as api } from '@/lib/http';

interface LoginPayload {
  username: string;
  password: string;
}

// ✅ 修复：匹配后端返回的数据结构
interface TokenResponse {
  access_token: string;
  token_type: string;
  // Snowflake BIGINT ids exceed JS safe integer range; keep as string.
  user_id: string;
  roles: string[];  // 后端返回的是 roles 数组
  display_name: string | null;
}

interface User {
  id: string;
  username: string;
  roles: string[];
  displayName: string | null;
}

const STORAGE_KEY = 'campuswap_token';
const USER_KEY = 'campuswap_user';

// ✅ 安全解析 localStorage
function getSafeStoredUser(): User | null {
  try {
    const userStr = localStorage.getItem(USER_KEY);
    if (!userStr || userStr === 'undefined' || userStr === 'null') {
      return null;
    }
    return JSON.parse(userStr);
  } catch {
    return null;
  }
}

function getSafeStoredToken(): string {
  const token = localStorage.getItem(STORAGE_KEY);
  if (!token || token === 'undefined' || token === 'null') {
    return '';
  }
  return token;
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: getSafeStoredToken(),
    user: getSafeStoredUser() as User | null,
    loading: false,
    error: '',
    lastLoginAt: null as string | null,
  }),

  getters: {
    isAuthenticated: (state) => !!state.token && !!state.user,
    // ✅ 修复：检查 roles 数组是否包含 'admin'
    isAdmin: (state) => {
      const hasAdminRole = state.user?.roles?.includes('admin') ?? false;
      console.log('🔍 [AuthStore] isAdmin check:', {
        user: state.user?.username,
        roles: state.user?.roles,
        hasAdminRole
      });
      return hasAdminRole;
    },
    displayName: (state) => state.user?.displayName ?? null,
    roles: (state) => state.user?.roles ?? [],
  },

  actions: {
    /** 恢复登录状态 */
    init() {
      this.token = getSafeStoredToken();
      this.user = getSafeStoredUser();
      console.log('🔄 [AuthStore] Initialized:', { token: !!this.token, user: this.user?.username, roles: this.user?.roles });
    },

    async login(payload: LoginPayload) {
      this.loading = true;
      this.error = '';
      
      try {
        const { data } = await api.post<TokenResponse>('/auth/login', payload);

        // ✅ 构建用户对象
        const userObj: User = {
          id: String(data.user_id),
          username: payload.username,
          roles: data.roles || [],
          displayName: data.display_name
        };

        // 更新状态
        this.token = data.access_token;
        this.user = userObj;

        // 持久化存储
        localStorage.setItem(STORAGE_KEY, data.access_token);
        localStorage.setItem(USER_KEY, JSON.stringify(userObj));

        // 记录登录时间
        this.lastLoginAt = new Date().toISOString();

        // ✅ 返回数据，供调用方判断角色
        return { user: userObj, isAdmin: userObj.roles.includes('admin') };

      } catch (err: any) {
        console.error('登录 API 错误:', err);
        this.error = err.response?.data?.detail || '登录失败，请检查用户名或密码';
        throw new Error(this.error);
      } finally {
        this.loading = false;
      }
    },

    logout() {
      this.token = '';
      this.user = null;
      localStorage.removeItem(STORAGE_KEY);
      localStorage.removeItem(USER_KEY);
    },

    // 监听 localStorage 变化，更新状态
    initStorageListener() {
      window.addEventListener('storage', (event) => {
        if (event.key === STORAGE_KEY || event.key === USER_KEY) {
          this.token = getSafeStoredToken();
          this.user = getSafeStoredUser();
        }
      });
    }
  }
});