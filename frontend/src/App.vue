<template>
  <!-- 1. 最外层：配置提供者 -->
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN">
    
    <!-- 2. 第二层：消息提供者 (必须包裹在 router-view 外面) -->
    <n-message-provider>
      <n-dialog-provider>
        <n-loading-bar-provider>
          
          <!-- 3. 应用布局 -->
          <div class="min-h-screen bg-slate-50 text-slate-900">
            
            <!-- 顶部导航栏：只有登录后才显示详细菜单 -->
            <header v-if="!isLoginPage && !isAdminPage" class="border-b bg-white/80 backdrop-blur sticky top-0 z-50">
              <div class="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
                
                <!-- Logo -->
                <div class="flex items-center gap-4">
                  <RouterLink class="text-2xl font-semibold text-orange-600" to="/">
                    🎓 CampuSwap
                  </RouterLink>
                  
                  <!-- 角色标签 (仅展示用) -->
                  <div v-if="isAuthenticated" class="flex items-center gap-2 bg-gray-100 rounded-full px-3 py-1">
                    <span :class="isAdmin ? 'text-orange-600 font-bold' : 'text-gray-500'">
                      {{ isAdmin ? '管理员' : '普通用户' }}
                    </span>
                  </div>
                </div>
                
                <!-- 导航链接 (仅登录可见) -->
                <nav v-if="isAuthenticated" class="flex flex-wrap items-center gap-2 text-sm text-slate-600">
                  <RouterLink
                    v-for="item in visibleLinks"
                    :key="item.to"
                    :to="item.to"
                    class="rounded-full px-4 py-2 transition-all"
                    :class="isActive(item.to) ? 'bg-orange-500 text-white' : 'hover:bg-orange-50 hover:text-orange-600'"
                  >
                    {{ item.icon }} {{ item.label }}
                  </RouterLink>
                </nav>
                
                <!-- 右侧用户信息/登录按钮 -->
                <div class="flex items-center gap-3 text-sm">
                  <template v-if="isAuthenticated">
                    <span class="text-slate-500">{{ currentUserName }}</span>
                    <button
                      class="rounded-full bg-gray-200 text-gray-700 px-4 py-2 hover:bg-gray-300 transition-colors"
                      type="button"
                      @click="logout"
                    >
                      退出
                    </button>
                  </template>
                  <template v-else>
                    <RouterLink 
                      to="/login"
                      class="rounded-full bg-orange-500 text-white px-6 py-2 hover:bg-orange-600 transition-colors"
                    >
                      去登录
                    </RouterLink>
                  </template>
                </div>
              </div>
            </header>

            <!-- 4. 核心：路由视图 (页面内容在这里显示) -->
            <main>
              <router-view />
            </main>

            <!-- AI 聊天助手 (悬浮按钮) -->
            <AIChatBox v-if="isAuthenticated && !isAdminPage" />

            <footer v-if="!isLoginPage && !isAdminPage" class="border-t bg-white mt-12">
              <div class="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-xs text-slate-500">
                <p>© {{ currentYear }} CampuSwap · 校园二手交易平台</p>
              </div>
            </footer>
          </div>

        </n-loading-bar-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth' // 🔥 引入 Store
import { 
  NConfigProvider, 
  NMessageProvider, 
  NDialogProvider,
  NLoadingBarProvider,
  zhCN,
  dateZhCN
} from 'naive-ui'
import AIChatBox from '@/components/AIChatBox.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore() // 🔥 初始化 Store

const currentYear = new Date().getFullYear()

// 🔥 从 Store 获取真实状态
const isAuthenticated = computed(() => authStore.isAuthenticated)
const isAdmin = computed(() => authStore.isAdmin)
const currentUserName = computed(() => authStore.user?.username || '未登录用户')

// 判断是否在登录页 (登录页通常不显示复杂的 Header)
const isLoginPage = computed(() => route.path === '/login')
// 判断是否在管理员页面
const isAdminPage = computed(() => route.path.startsWith('/admin'))

// 普通用户导航
const userLinks = [
  { label: '商品市场', to: '/marketplace', icon: '🏪' },
   { label: '购物车', to: '/cart', icon: '🛒' }, 
  { label: '消息', to: '/messages', icon: '💬' },
  { label: '我的商品', to: '/my-items', icon: '📦' },
  { label: '我的订单', to: '/orders', icon: '📝' },
  { label: '个人中心', to: '/user/profile', icon: '👤' }
]

// 管理员导航
const adminLinks = [
  { label: '数据仪表盘', to: '/admin/dashboard', icon: '📊' },
  { label: '数据分析', to: '/admin/analytics', icon: '📈' },
  { label: '四库同步', to: '/admin/console', icon: '🔄' },
  { label: '用户管理', to: '/admin/users', icon: '👥' },
  { label: '系统设置', to: '/admin/settings', icon: '🔧' }
]

const visibleLinks = computed(() => isAdmin.value ? adminLinks : userLinks)

function isActive(path: string) {
  return route.path === path || route.path.startsWith(path + '/')
}

function logout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

#app {
  width: 100%;
  min-height: 100vh;
}
</style>