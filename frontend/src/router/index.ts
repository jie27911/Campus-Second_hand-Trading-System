import { createRouter, createWebHistory } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { http as api } from '@/lib/http';
import { createDiscreteApi } from 'naive-ui';

// 布局组件
import UserLayout from '@/components/UserLayout.vue';
import AdminLayout from '@/components/AdminLayout.vue';

// 普通用户页面
import MarketplaceView from '@/views/MarketplaceView.vue';
import MessagesView from '@/views/MessagesView.vue';
import MyItemsView from '@/views/MyItemsView.vue';
import OrdersView from '@/views/OrdersView.vue';
import ProfileCenterView from '@/views/ProfileCenterView.vue';
import UserProfileView from '@/views/UserProfileView.vue';
import ShoppingCartView from '@/views/ShoppingCartView.vue';
import CheckoutView from '@/views/CheckoutView.vue';
import SearchHistoryView from '@/views/SearchHistoryView.vue';
import UserSettingsView from '@/views/UserSettingsView.vue';
import LoginView from '@/views/LoginView.vue';
import ItemDetailView from '@/views/ItemDetailView.vue';
import PublishItemView from '@/views/PublishItemView.vue';
import SearchResultsView from '@/views/SearchResultsView.vue';
import NotFoundView from '@/views/NotFoundView.vue';
import ForbiddenView from '@/views/ForbiddenView.vue';
import ServerErrorView from '@/views/ServerErrorView.vue';

// 管理员页面
import AdminConsoleView from '@/views/AdminConsoleView.vue';
import AnalyticsView from '@/views/AnalyticsView.vue';
import DashboardView from '@/views/DashboardView.vue';
import SystemSettingsView from '@/views/SystemSettingsView.vue';
import UserManagementView from '@/views/UserManagementView.vue';
import AdvancedQueryView from '@/views/AdvancedQueryView.vue';
import AdminProfileView from '@/views/AdminProfileView.vue';

// 1. 引入注册组件
import RegisterView from '@/views/RegisterView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // ✅ 修改根路径：根据角色重定向
    {
      path: '/',
      name: 'home',
      redirect: () => {
        const authStore = useAuthStore();
        if (authStore.isAdmin) {
          return '/admin/dashboard';  // 管理员进入后台
        }
        return '/marketplace';  // 普通用户进入市场
      }
    },
    
    // ========== 登录/注册页面（无布局） ==========
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { title: '登录', public: true }
    },
    // 2. 添加注册路由
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { title: '注册', public: true }
    },
    
    // ========== 普通用户路由（使用 UserLayout） ==========
    {
      path: '/',
      component: UserLayout,
      children: [
        {
          path: 'marketplace',
          name: 'marketplace',
          component: MarketplaceView,
          meta: { title: '商品市场', icon: '🏪', role: 'user' }
        },
        {
          path: 'item/:id',
          name: 'item-detail',
          component: ItemDetailView,
          meta: { title: '商品详情', icon: '📦', role: 'user' }
        },
        {
          path: 'publish',
          name: 'publish-item',
          component: PublishItemView,
          meta: { title: '发布商品', icon: '📝', role: 'user', requiresAuth: true }
        },
        {
          path: 'cart',
          name: 'cart',
          component: ShoppingCartView,
          meta: { title: '购物车', icon: '🛒', role: 'user', requiresAuth: true }
        },
        {
          path: 'checkout',
          name: 'checkout',
          component: CheckoutView,
          meta: { title: '订单确认', icon: '📦', role: 'user', requiresAuth: true }
        },
        {
          path: 'messages',
          name: 'messages',
          component: MessagesView,
          meta: { title: '消息', icon: '💬', role: 'user', requiresAuth: true }
        },
        {
          path: 'my-items',
          name: 'my-items',
          component: MyItemsView,
          meta: { title: '我的商品', icon: '📦', role: 'user', requiresAuth: true }
        },
        {
          path: 'orders',
          name: 'orders',
          component: OrdersView,
          meta: { title: '交易记录', icon: '📝', role: 'user', requiresAuth: true }
        },
        {
          path: 'profile',
          name: 'profile',
          component: ProfileCenterView,
          meta: { title: '个人中心', icon: '👤', role: 'user', requiresAuth: true }
        },
        {
          path: 'user/profile',
          name: 'user-profile',
          component: UserProfileView,
          meta: { title: '个人主页', icon: '👤', role: 'user', requiresAuth: true }
        },
        {
          path: 'user/settings',
          name: 'user-settings',
          component: UserSettingsView,
          meta: { title: '账号设置', icon: '⚙️', role: 'user', requiresAuth: true }
        },
        {
          path: 'user/favorites',
          name: 'user-favorites',
          component: ProfileCenterView,
          meta: { title: '我的收藏', icon: '❤️', role: 'user', requiresAuth: true }
        },
        {
          path: 'user/search-history',
          name: 'search-history',
          component: SearchHistoryView,
          meta: { title: '搜索历史', icon: '🔍', role: 'user', requiresAuth: true }
        },
        {
          path: 'search',
          name: 'search-results',
          component: SearchResultsView,
          meta: { title: '搜索结果', icon: '🔍', role: 'user' }
        }
      ]
    },
    
    // ========== 管理员路由（使用 AdminLayout） ==========
    {
      path: '/admin',
      component: AdminLayout,
      children: [
        {
          path: 'dashboard',
          name: 'admin-dashboard',
          component: DashboardView,
          meta: { title: '管理仪表盘', icon: '📊', role: 'admin', requiresAdmin: true }
        },
        {
          path: 'analytics',
          name: 'admin-analytics',
          component: AnalyticsView,
          meta: { title: '数据分析中心', icon: '📈', role: 'admin', requiresAdmin: true }
        },
        {
          path: 'console',
          name: 'admin-console',
          component: AdminConsoleView,
          meta: { title: '同步控制', icon: '🔄', role: 'admin', requiresAdmin: true }
        },
        {
          path: 'query',
          name: 'admin-query',
          component: AdvancedQueryView,
          meta: { title: '高级查询', icon: '🔍', role: 'admin', requiresAdmin: true }
        },
        {
          path: 'users',
          name: 'admin-users',
          component: UserManagementView,
          meta: { title: '用户管理', icon: '👥', role: 'admin', requiresAdmin: true }
        },
        {
          path: 'settings',
          name: 'admin-settings',
          component: SystemSettingsView,
          meta: { title: '系统设置', icon: '🔧', role: 'admin', requiresAdmin: true }
        },
        {
          path: 'profile',
          name: 'admin-profile',
          component: AdminProfileView,
          meta: { title: '管理员资料', icon: '👤', role: 'admin', requiresAdmin: true }
        }
      ]
    },
    
    // ========== 错误页面 ==========
    {
      path: '/403',
      name: 'forbidden',
      component: ForbiddenView,
      meta: { title: '访问被拒绝', public: true }
    },
    {
      path: '/500',
      name: 'server-error',
      component: ServerErrorView,
      meta: { title: '服务器错误', public: true }
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: NotFoundView,
      meta: { title: '页面不存在', public: true }
    }
  ]
});

// 🔥 修复后的路由守卫
router.beforeEach(async (to, from, next) => {
  // 👇 3. 更新白名单
  const whiteList = ['/login', '/register', '/403', '/500', '/not-found'];
  
  console.group(`🚦 [Router] ${from.path} → ${to.path}`);
  
  try {
    const authStore = useAuthStore();

    // ============ Magic login for conflict email links (no password) ============
    // Only enabled for the admin console page.
    const rawToken = to.query.token;
    const magicToken = Array.isArray(rawToken) ? rawToken[0] : rawToken;
    if (to.path === '/admin/console' && typeof magicToken === 'string' && magicToken.trim()) {
      try {
        const { data } = await api.post<any>('/auth/magic/conflict', { token: magicToken.trim() });

        const userObj = {
          id: data.user_id,
          username: data.display_name || 'Email Admin',
          roles: data.roles || [],
          displayName: data.display_name || null,
        };

        localStorage.setItem('campuswap_token', data.access_token);
        localStorage.setItem('campuswap_user', JSON.stringify(userObj));
        authStore.init();

        // Remove token from URL to avoid leaking/reusing it.
        const { token, ...rest } = to.query as any;
        next({ path: to.path, query: rest, replace: true });
        console.groupEnd();
        return;
      } catch (error) {
        console.error('❌ Magic login failed:', error);

        // Show a clearer reason (most commonly: token expired/invalid).
        try {
          const { message } = createDiscreteApi(['message']);
          const detail = (error as any)?.response?.data?.detail;
          const msg = typeof detail === 'string' && detail.trim()
            ? `邮件登录失败：${detail}`
            : '邮件登录失败：请求失败（请检查令牌是否过期或网关是否可访问）';
          message.error(msg);
        } catch {
          // best-effort; do not block routing
        }

        next('/login');
        console.groupEnd();
        return;
      }
    }
    // 确保 authStore 已初始化
    if (!authStore.token && localStorage.getItem('campuswap_token')) {
      authStore.init();
    }
    
    const isAuthenticated = authStore.isAuthenticated;
    const isAdmin = authStore.isAdmin;
    
    console.log('🔐 [Router] Auth status:', { 
      isAuthenticated, 
      isAdmin, 
      userRoles: authStore.roles,
      requiresAuth: to.meta.requiresAuth,
      public: to.meta.public 
    });

    // ============ 规则 1: 访问登录页 ============
    if (to.path === '/login' || to.name === 'login') {
      if (isAuthenticated) {
        console.log('✅ 已登录，重定向到市场');
        next('/marketplace');
      } else {
        console.log('✅ 访问登录页，放行');
        next();
      }
      console.groupEnd();
      return;
    }

    // ============ 规则 2: 白名单页面 ============
    if (whiteList.includes(to.path) || to.meta.public === true) {
      console.log('✅ 白名单/公开页面，放行');
      next();
      console.groupEnd();
      return;
    }

    // ============ 规则 3: 需要登录但未登录 ============
    // 注意：这里我们假设所有非白名单页面默认都需要登录，除非明确标记 public: true
    // 或者你也可以只检查 meta.requiresAuth
    const requiresAuth = to.meta.requiresAuth !== false; // 默认为 true，除非明确设为 false
    
    if (requiresAuth && !isAuthenticated) {
      console.warn('❌ 未登录，重定向到登录页');
      // 避免无限循环：如果已经在登录页，不要再推送到登录页
      if (from.path === '/login') {
        console.error('⚠️ 检测到重定向循环，强制停止');
        return; 
      }
      next({
        path: '/login',
        query: { redirect: to.fullPath }
      });
      console.groupEnd();
      return;
    }

    // ============ 规则 4: 管理员避免访问用户界面 ============
    if (isAdmin && to.meta.role === 'user') {
      console.warn('ℹ️ 管理员访问用户端页面，重定向到后台');
      next('/admin/dashboard');
      console.groupEnd();
      return;
    }

    // ============ 规则 5: 需要管理员权限 ============
    if (to.meta.requiresAdmin === true) {
      if (!isAdmin) {
        console.warn('❌ 权限不足，拒绝访问');
        next('/403');
        console.groupEnd();
        return;
      }
    }

    // ============ 规则 6: 放行所有其他情况 ============
    console.log('✅ 检查通过，放行');
    next();

  } catch (error) {
    console.error('❌ 路由守卫异常:', error);
    // 发生错误时，为了避免死循环，可以尝试跳转到错误页或放行到登录页
    if (to.path !== '/login') {
      next('/login');
    } else {
      next();
    }
  } finally {
    console.groupEnd();
  }
});

// 获取用户路由（用于导航菜单）
export function getUserRoutes() {
  return router.options.routes.filter(route => {
    return route.meta?.role === 'user' && route.path !== '/';
  });
}

// 获取管理员路由（用于导航菜单）
export function getAdminRoutes() {
  return router.options.routes.filter(route => {
    return route.meta?.role === 'admin';
  });
}

export default router;
