<template>
  <div class="space-y-6">
    <section class="rounded-3xl bg-white p-6 shadow">
      <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p class="text-xs uppercase tracking-widest text-slate-400">Admin Dashboard</p>
          <h1 class="text-3xl font-semibold text-slate-900">管理仪表盘</h1>
          <p class="mt-2 text-sm text-slate-500">
            快速概览系统状态、关键指标和最新动态。点击下方卡片进入详细管理。
          </p>
        </div>
        <div class="text-sm text-slate-400">
          最后更新: {{ currentTime }}
        </div>
      </div>
    </section>

    <!-- 核心功能导航 -->
    <section class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <RouterLink
        to="/admin/console"
        class="group rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 p-6 text-white shadow-lg transition-all hover:scale-105 hover:shadow-xl"
      >
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm opacity-90">数据库同步</p>
            <p class="mt-2 text-2xl font-bold">控制台</p>
            <p class="mt-1 text-xs opacity-75">管理同步状态</p>
          </div>
          <span class="text-4xl opacity-80">🔄</span>
        </div>
      </RouterLink>

      <RouterLink
        to="/admin/analytics"
        class="group rounded-2xl bg-gradient-to-br from-green-500 to-green-600 p-6 text-white shadow-lg transition-all hover:scale-105 hover:shadow-xl"
      >
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm opacity-90">数据分析</p>
            <p class="mt-2 text-2xl font-bold">报表中心</p>
            <p class="mt-1 text-xs opacity-75">查看统计图表</p>
          </div>
          <span class="text-4xl opacity-80">📊</span>
        </div>
      </RouterLink>

      <RouterLink
        to="/admin/query"
        class="group rounded-2xl bg-gradient-to-br from-purple-500 to-purple-600 p-6 text-white shadow-lg transition-all hover:scale-105 hover:shadow-xl"
      >
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm opacity-90">高级查询</p>
            <p class="mt-2 text-2xl font-bold">SQL 演示</p>
            <p class="mt-1 text-xs opacity-75">复杂查询优化</p>
          </div>
          <span class="text-4xl opacity-80">🔍</span>
        </div>
      </RouterLink>

      <RouterLink
        to="/admin/users"
        class="group rounded-2xl bg-gradient-to-br from-orange-500 to-red-500 p-6 text-white shadow-lg transition-all hover:scale-105 hover:shadow-xl"
      >
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm opacity-90">用户管理</p>
            <p class="mt-2 text-2xl font-bold">权限控制</p>
            <p class="mt-1 text-xs opacity-75">账户与角色</p>
          </div>
          <span class="text-4xl opacity-80">👥</span>
        </div>
      </RouterLink>

      <RouterLink
        to="/admin/settings"
        class="group rounded-2xl bg-gradient-to-br from-indigo-500 to-indigo-600 p-6 text-white shadow-lg transition-all hover:scale-105 hover:shadow-xl"
      >
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm opacity-90">系统设置</p>
            <p class="mt-2 text-2xl font-bold">配置管理</p>
            <p class="mt-1 text-xs opacity-75">参数与选项</p>
          </div>
          <span class="text-4xl opacity-80">⚙️</span>
        </div>
      </RouterLink>

      <RouterLink
        to="/admin/profile"
        class="group rounded-2xl bg-gradient-to-br from-gray-500 to-gray-600 p-6 text-white shadow-lg transition-all hover:scale-105 hover:shadow-xl"
      >
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm opacity-90">个人中心</p>
            <p class="mt-2 text-2xl font-bold">账户信息</p>
            <p class="mt-1 text-xs opacity-75">资料与偏好</p>
          </div>
          <span class="text-4xl opacity-80">👤</span>
        </div>
      </RouterLink>
    </section>

    <!-- 系统状态概览 -->
    <section class="grid gap-4 lg:grid-cols-3">
      <!-- 快速开始 (占 2 列) -->
      <article class="lg:col-span-2 rounded-2xl bg-white p-6 shadow">
        <header class="flex items-center gap-2 mb-4">
          <span class="text-lg">🚀</span>
          <h2 class="text-lg font-semibold text-slate-900">快速开始</h2>
        </header>
        <div class="grid gap-4 md:grid-cols-2">
          <div class="rounded-xl border border-slate-100 bg-slate-50 p-4 transition-colors hover:border-blue-200 hover:bg-blue-50">
            <h3 class="font-medium text-slate-900 mb-2">数据库同步管理</h3>
            <p class="text-sm text-slate-600 mb-3">监控四库同步状态，处理数据冲突，手动触发同步操作。</p>
            <RouterLink to="/admin/console" class="inline-flex items-center text-sm font-medium text-blue-600 hover:text-blue-800">
              进入同步控制台 <span class="ml-1">→</span>
            </RouterLink>
          </div>
          <div class="rounded-xl border border-slate-100 bg-slate-50 p-4 transition-colors hover:border-green-200 hover:bg-green-50">
            <h3 class="font-medium text-slate-900 mb-2">数据分析与报表</h3>
            <p class="text-sm text-slate-600 mb-3">查看每日同步分析报表，了解系统运行状况和趋势。</p>
            <RouterLink to="/admin/analytics" class="inline-flex items-center text-sm font-medium text-green-600 hover:text-green-800">
              进入数据分析中心 <span class="ml-1">→</span>
            </RouterLink>
          </div>
        </div>
      </article>

      <!-- 系统运行状态 (占 1 列) -->
      <article class="rounded-2xl bg-white p-6 shadow">
        <header class="flex items-center gap-2 mb-4">
          <span class="text-lg">📡</span>
          <h2 class="text-lg font-semibold text-slate-900">系统运行状态</h2>
        </header>
        <div class="space-y-4">
          <div class="flex items-center justify-between">
            <span class="text-sm text-slate-600">API 网关</span>
            <span class="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
              <span class="mr-1.5 h-2 w-2 rounded-full bg-green-500"></span>
              运行中
            </span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-slate-600">同步服务</span>
            <span class="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
              <span class="mr-1.5 h-2 w-2 rounded-full bg-green-500"></span>
              正常
            </span>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-sm text-slate-600">数据库集群</span>
            <span class="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
              <span class="mr-1.5 h-2 w-2 rounded-full bg-green-500"></span>
              已连接 (4/4)
            </span>
          </div>
          <div class="pt-4 border-t border-slate-100">
            <p class="text-xs text-slate-400 text-center">系统负载正常，所有服务响应迅速</p>
          </div>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue';

const currentTime = ref('');

function updateTime() {
  currentTime.value = new Date().toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
}

onMounted(() => {
  updateTime();
  // 每分钟更新一次时间
  setInterval(updateTime, 60000);
});
</script>
