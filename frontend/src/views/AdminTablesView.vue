<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NTabs, NTabPane, NSelect, useMessage } from 'naive-ui'
import AdminTableManager from '../components/AdminTableManager.vue'
import ComplexQuery from '../components/ComplexQuery.vue'

const message = useMessage()
const route = useRoute()
const router = useRouter()

const activeTab = ref('tables')
const selectedTable = ref('users')

// 与后端 /admin/tables 白名单对齐
const tables = [
  // 核心业务表
  { key: 'users', label: '用户管理', endpoint: '/admin/tables/users' },
  { key: 'user_profiles', label: '用户档案', endpoint: '/admin/tables/user_profiles' },
  { key: 'categories', label: '分类管理', endpoint: '/admin/tables/categories' },
  { key: 'items', label: '商品管理', endpoint: '/admin/tables/items' },
  { key: 'item_images', label: '商品图片', endpoint: '/admin/tables/item_images' },
  { key: 'transactions', label: '交易管理', endpoint: '/admin/tables/transactions' },
  { key: 'messages', label: '消息管理', endpoint: '/admin/tables/messages' },
  { key: 'favorites', label: '收藏管理', endpoint: '/admin/tables/favorites' },
  
  // 系统管理表
  { key: 'conflict_records', label: '冲突记录', endpoint: '/admin/tables/conflict_records' },
  { key: 'daily_stats', label: '每日统计', endpoint: '/admin/tables/daily_stats' },
  { key: 'system_configs', label: '系统配置', endpoint: '/admin/tables/system_configs' },
  { key: 'roles', label: '角色管理', endpoint: '/admin/tables/roles' },
  { key: 'permissions', label: '权限管理', endpoint: '/admin/tables/permissions' },
  { key: 'role_permissions', label: '角色权限关联', endpoint: '/admin/tables/role_permissions' },
  
  // 扩展关联表
  { key: 'user_follows', label: '用户关注', endpoint: '/admin/tables/user_follows' },
  { key: 'item_view_history', label: '浏览历史', endpoint: '/admin/tables/item_view_history' },
  { key: 'user_addresses', label: '用户地址', endpoint: '/admin/tables/user_addresses' },
  { key: 'item_price_history', label: '价格历史', endpoint: '/admin/tables/item_price_history' },
  { key: 'message_attachments', label: '消息附件', endpoint: '/admin/tables/message_attachments' },
  { key: 'transaction_review_images', label: '评价图片', endpoint: '/admin/tables/transaction_review_images' },
  { key: 'notifications', label: '通知管理', endpoint: '/admin/tables/notifications' },
  { key: 'search_history', label: '搜索历史', endpoint: '/admin/tables/search_history' },
  { key: 'sync_tasks', label: '同步任务', endpoint: '/admin/tables/sync_tasks' },
  { key: 'performance_metrics', label: '性能指标', endpoint: '/admin/tables/performance_metrics' },
]

const tableOptions = tables.map(t => ({ label: t.label, value: t.key }))

const getCurrentTable = () => {
  return tables.find(t => t.key === activeTab.value)
}

const syncQueryToTab = (value: string | undefined) => {
  if (!value) return
  const exists = tables.find(t => t.key === value)
  if (exists && activeTab.value !== value) {
    activeTab.value = value
  }
}

onMounted(() => {
  syncQueryToTab(route.query.table as string | undefined)
})

watch(() => route.query.table, (val) => {
  if (val && tables.find(t => t.key === val)) {
    selectedTable.value = val
    activeTab.value = 'tables'
  }
})

watch(selectedTable, (value) => {
  if (activeTab.value === 'tables') {
    router.replace({ query: { ...route.query, table: value } })
  }
})
</script>

<template>
  <div class="admin-tables-page">
    <n-card title="数据表管理与查询">
      <n-tabs v-model:value="activeTab" type="line">
        <n-tab-pane name="tables" tab="表管理">
          <template #header-extra>
            <n-select
              v-model:value="selectedTable"
              :options="tableOptions"
              style="width: 200px"
              placeholder="选择数据表"
            />
          </template>

          <AdminTableManager
            v-if="getCurrentTable()"
            :key="selectedTable"
            :table-name="selectedTable"
            :api-endpoint="getCurrentTable()!.endpoint"
          />
        </n-tab-pane>

        <n-tab-pane name="query" tab="复杂查询">
          <ComplexQuery />
        </n-tab-pane>
      </n-tabs>
    </n-card>
  </div>
</template>

<style scoped>
.admin-tables-page {
  padding: 24px;
  height: 100%;
}
</style>
