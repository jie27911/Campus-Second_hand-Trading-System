<template>
  <div class="admin-performance-container">
    <!-- 顶部标题栏 -->
    <div class="header-bar">
      <h1>📊 数据库性能监控中心</h1>
      <n-space>
        <n-button type="primary" @click="refreshAllData">
          🔄 刷新所有数据
        </n-button>
        <n-button @click="toggleAutoRefresh">
          {{ autoRefresh ? '⏸️ 暂停自动刷新' : '▶️ 启动自动刷新' }}
        </n-button>
      </n-space>
    </div>

    <!-- 实时性能指标卡片 -->
    <div class="metrics-grid">
      <n-card title="🔥 系统实时状态" :bordered="false" class="metric-card">
        <n-statistic label="总用户数" :value="stats.totalUsers">
          <template #suffix>人</template>
        </n-statistic>
        <n-divider />
        <n-statistic label="在线用户" :value="stats.onlineUsers" class="text-success">
          <template #suffix>人</template>
        </n-statistic>
      </n-card>

      <n-card title="📦 商品统计" :bordered="false" class="metric-card">
        <n-statistic label="在售商品" :value="stats.availableItems">
          <template #suffix>件</template>
        </n-statistic>
        <n-divider />
        <n-statistic label="今日新增" :value="stats.todayNewItems" class="text-primary">
          <template #suffix>件</template>
        </n-statistic>
      </n-card>

      <n-card title="💰 交易数据" :bordered="false" class="metric-card">
        <n-statistic label="总交易额" :value="stats.totalTransactionAmount">
          <template #prefix>¥</template>
        </n-statistic>
        <n-divider />
        <n-statistic label="今日成交" :value="stats.todayCompletedTransactions" class="text-success">
          <template #suffix>笔</template>
        </n-statistic>
      </n-card>

      <n-card title="⚡ 数据库性能" :bordered="false" class="metric-card">
        <n-statistic label="平均查询时间" :value="stats.avgQueryTime">
          <template #suffix>ms</template>
        </n-statistic>
        <n-divider />
        <n-statistic label="QPS" :value="stats.qps" class="text-warning">
          <template #suffix>次/秒</template>
        </n-statistic>
      </n-card>
    </div>

    <!-- 四库同步状态 -->
    <n-card title="🔄 四数据库同步状态" class="sync-status-card">
      <n-table :bordered="false" :single-line="false">
        <thead>
          <tr>
            <th>数据库</th>
            <th>连接状态</th>
            <th>延迟</th>
            <th>记录数</th>
            <th>同步版本</th>
            <th>最后同步</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="db in databases" :key="db.key">
            <td><strong>{{ db.name }}</strong></td>
            <td>
              <n-tag :type="db.status === 'online' ? 'success' : 'error'" size="small">
                {{ db.status === 'online' ? '✅ 在线' : '❌ 离线' }}
              </n-tag>
            </td>
            <td>{{ db.latency }}ms</td>
            <td>{{ db.recordCount.toLocaleString() }}</td>
            <td>v{{ db.syncVersion }}</td>
            <td>{{ db.lastSync }}</td>
            <td>
              <n-space>
                <n-button size="small" @click="syncDatabase(db)">同步</n-button>
                <n-button size="small" type="primary" @click="viewDbDetails(db)">详情</n-button>
              </n-space>
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <!-- 查询性能分析 -->
    <n-card title="📈 慢查询分析 (Top 10)" class="query-analysis-card">
      <n-table :bordered="false" :single-line="false">
        <thead>
          <tr>
            <th>查询ID</th>
            <th>SQL语句</th>
            <th>执行次数</th>
            <th>平均耗时</th>
            <th>最大耗时</th>
            <th>影响行数</th>
            <th>优化建议</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(query, idx) in slowQueries" :key="idx">
            <td>{{ query.id }}</td>
            <td class="sql-query">{{ query.sql }}</td>
            <td>{{ query.count }}</td>
            <td>
              <n-tag :type="query.avgTime > 100 ? 'error' : 'warning'" size="small">
                {{ query.avgTime }}ms
              </n-tag>
            </td>
            <td>{{ query.maxTime }}ms</td>
            <td>{{ query.rows }}</td>
            <td>
              <n-tooltip trigger="hover">
                <template #trigger>
                  <n-button size="tiny" type="info">💡 查看</n-button>
                </template>
                {{ query.suggestion }}
              </n-tooltip>
            </td>
          </tr>
        </tbody>
      </n-table>
    </n-card>

    <!-- 数据库连接池状态 -->
    <div class="pool-grid">
      <n-card title="🏊 MySQL 连接池" size="small">
        <n-progress type="line" :percentage="mysqlPool.usage" :color="getPoolColor(mysqlPool.usage)" />
        <n-descriptions :column="2" size="small" style="margin-top: 10px;">
          <n-descriptions-item label="活跃连接">{{ mysqlPool.active }}/{{ mysqlPool.max }}</n-descriptions-item>
          <n-descriptions-item label="空闲连接">{{ mysqlPool.idle }}</n-descriptions-item>
          <n-descriptions-item label="等待队列">{{ mysqlPool.waiting }}</n-descriptions-item>
          <n-descriptions-item label="超时次数">{{ mysqlPool.timeouts }}</n-descriptions-item>
        </n-descriptions>
      </n-card>
      
        <n-card title="🏊 PostgreSQL 连接池" size="small">
          <n-progress type="line" :percentage="postgresPool.usage" :color="getPoolColor(postgresPool.usage)" />
          <n-descriptions :column="2" size="small" style="margin-top: 10px;">
            <n-descriptions-item label="活跃连接">{{ postgresPool.active }}/{{ postgresPool.max }}</n-descriptions-item>
            <n-descriptions-item label="空闲连接">{{ postgresPool.idle }}</n-descriptions-item>
            <n-descriptions-item label="等待队列">{{ postgresPool.waiting }}</n-descriptions-item>
            <n-descriptions-item label="超时次数">{{ postgresPool.timeouts }}</n-descriptions-item>
          </n-descriptions>
        </n-card>

      <n-card title="🏊 MariaDB 连接池" size="small">
        <n-progress type="line" :percentage="mariadbPool.usage" :color="getPoolColor(mariadbPool.usage)" />
        <n-descriptions :column="2" size="small" style="margin-top: 10px;">
          <n-descriptions-item label="活跃连接">{{ mariadbPool.active }}/{{ mariadbPool.max }}</n-descriptions-item>
          <n-descriptions-item label="空闲连接">{{ mariadbPool.idle }}</n-descriptions-item>
          <n-descriptions-item label="等待队列">{{ mariadbPool.waiting }}</n-descriptions-item>
          <n-descriptions-item label="超时次数">{{ mariadbPool.timeouts }}</n-descriptions-item>
        </n-descriptions>
      </n-card>
    </div>

    <!-- 实时查询监控 -->
    <n-card title="🔍 实时查询监控" class="realtime-queries-card">
      <n-space vertical>
        <n-alert type="info" title="正在执行的查询" :bordered="false">
          当前有 <strong>{{ runningQueries.length }}</strong> 个查询正在执行
        </n-alert>
        <n-table :bordered="false" size="small" max-height="300px">
          <thead>
            <tr>
              <th>数据库</th>
              <th>查询</th>
              <th>状态</th>
              <th>耗时</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="q in runningQueries" :key="q.id">
              <td><n-tag size="small">{{ q.database }}</n-tag></td>
              <td class="sql-query">{{ q.query }}</td>
              <td>
                <n-spin size="small" v-if="q.status === 'running'" />
                <span v-else>{{ q.status }}</span>
              </td>
              <td>{{ q.duration }}ms</td>
              <td>
                <n-button size="tiny" type="error" @click="killQuery(q.id)">终止</n-button>
              </td>
            </tr>
          </tbody>
        </n-table>
      </n-space>
    </n-card>

    <!-- 系统健康度仪表盘 -->
    <div class="health-dashboard">
      <n-card title="🏥 系统健康度评分">
        <div class="health-score">
          <n-progress
            type="dashboard"
            :percentage="systemHealth"
            :color="systemHealth > 80 ? '#18a058' : systemHealth > 60 ? '#f0a020' : '#d03050'"
            :rail-color="'rgba(128, 128, 128, 0.2)'"
          >
            <div class="health-label">
              <div class="score">{{ systemHealth }}</div>
              <div class="text">{{ getHealthLabel(systemHealth) }}</div>
            </div>
          </n-progress>
          <n-alert type="info" style="margin-top: 12px;" :bordered="false">
            评分基于：数据库连接(30%) + 查询速度(30%) + 同步一致性(30%) + 资源使用(10%)
          </n-alert>
        </div>
        <n-divider />
        <n-space vertical>
          <div class="health-item">
            <span>数据库连接状态</span>
            <n-tag :type="healthMetrics.dbConnection > 90 ? 'success' : 'warning'">
              {{ healthMetrics.dbConnection }}%
            </n-tag>
          </div>
          <div class="health-item">
            <span>查询响应速度</span>
            <n-tag :type="healthMetrics.querySpeed > 90 ? 'success' : 'warning'">
              {{ healthMetrics.querySpeed }}%
            </n-tag>
          </div>
          <div class="health-item">
            <span>同步一致性</span>
            <n-tag :type="healthMetrics.syncConsistency > 95 ? 'success' : 'error'">
              {{ healthMetrics.syncConsistency }}%
            </n-tag>
          </div>
          <div class="health-item">
            <span>系统资源使用</span>
            <n-tag :type="healthMetrics.resourceUsage < 80 ? 'success' : 'warning'">
              {{ healthMetrics.resourceUsage }}%
            </n-tag>
          </div>
        </n-space>
      </n-card>
    </div>

    <n-modal
      v-model:show="dbLogsModalVisible"
      preset="card"
      :title="`${currentDbTitle} 同步日志`"
      style="width: 640px"
    >
      <n-table v-if="currentDbLogs.length" size="small">
        <thead>
          <tr>
            <th>ID</th>
            <th>状态</th>
            <th>开始时间</th>
            <th>完成时间</th>
            <th>模式</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in currentDbLogs" :key="log.id">
            <td>{{ log.id }}</td>
            <td>
              <n-tag :type="log.status === 'failed' ? 'error' : 'success'" size="small">
                {{ log.status }}
              </n-tag>
            </td>
            <td>{{ formatDateTime(log.started_at) }}</td>
            <td>{{ formatDateTime(log.completed_at) }}</td>
            <td>{{ log.mode || '-' }}</td>
          </tr>
        </tbody>
      </n-table>
      <n-empty v-else description="暂无日志数据" />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useMessage } from 'naive-ui'

import { http as api } from '@/lib/http'

interface PoolSnapshot {
  active: number
  idle: number
  max: number
  waiting: number
  timeouts: number
  usage: number
  writeQueue?: number
  walSize?: number
}

interface DatabaseRow {
  key: string
  name: string
  status: 'online' | 'offline'
  latency: number
  recordCount: number
  syncVersion: number
  lastSync: string
}

interface SlowQueryRow {
  id: string
  sql: string
  count: number
  avgTime: number
  maxTime: number
  rows: number
  suggestion: string
}

interface RunningQueryRow {
  id: string
  database: string
  query: string
  status: string
  duration: number
}

interface DbLogRow {
  id: number
  status: string
  started_at: string | null
  completed_at: string | null
  mode?: string | null
}

const message = useMessage()

const DATABASES = [
  { key: 'mysql', label: 'MySQL' },
  { key: 'postgres', label: 'PostgreSQL' },
  { key: 'mariadb', label: 'MariaDB' }
]

const makeEmptyPool = (): PoolSnapshot => ({ active: 0, idle: 0, max: 0, waiting: 0, timeouts: 0, usage: 0 })

const stats = ref({
  totalUsers: 0,
  onlineUsers: 0,
  availableItems: 0,
  todayNewItems: 0,
  totalTransactionAmount: 0,
  todayCompletedTransactions: 0,
  avgQueryTime: 0,
  qps: 0
})

const databases = ref<DatabaseRow[]>([])
const slowQueries = ref<SlowQueryRow[]>([])
const runningQueries = ref<RunningQueryRow[]>([])

const mysqlPool = ref<PoolSnapshot>(makeEmptyPool())
const postgresPool = ref<PoolSnapshot>(makeEmptyPool())
const mariadbPool = ref<PoolSnapshot>(makeEmptyPool())

const healthMetrics = ref({
  dbConnection: 0,
  querySpeed: 0,
  syncConsistency: 0,
  resourceUsage: 0,
  score: 0
})

const systemHealth = computed(() => {
  const metrics = healthMetrics.value
  if (metrics.score) return Math.round(metrics.score)
  return Math.round(
    metrics.dbConnection * 0.3 +
    metrics.querySpeed * 0.3 +
    metrics.syncConsistency * 0.3 +
    (100 - metrics.resourceUsage) * 0.1
  )
})

const autoRefresh = ref(false)
const isLoading = ref(false)
const dbLogsModalVisible = ref(false)
const currentDbLogs = ref<DbLogRow[]>([])
const currentDbTitle = ref('')
let refreshInterval: number | undefined

const handleError = (error: unknown, fallback: string) => {
  console.error(error)
  const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
  message.error(detail || fallback)
}

const formatDateTime = (value?: string | null) => {
  if (!value) return '未完成'
  return new Date(value).toLocaleString()
}

const applyConnectionPools = (poolData: Record<string, PoolSnapshot>) => {
  mysqlPool.value = poolData.mysql ?? makeEmptyPool()
  postgresPool.value = poolData.postgres ?? makeEmptyPool()
  mariadbPool.value = poolData.mariadb ?? makeEmptyPool()
}

const estimateLatency = (pool: PoolSnapshot) => {
  if (!pool.max) return 0
  return Math.max(1, Math.round((pool.active / pool.max) * 20))
}

const fetchLatestLogsByTarget = async () => {
  try {
    const { data } = await api.get('/sync/logs', { params: { page: 1, page_size: 40 } })
    const map = new Map<string, any>()
    for (const log of data.logs || []) {
      const target = log.stats?.target
      if (target && !map.has(target)) {
        map.set(target, log)
      }
    }
    return map
  } catch (error) {
    handleError(error, '无法获取同步日志')
    return new Map<string, any>()
  }
}

const refreshDatabases = async (
  statusPayload: any,
  poolData: Record<string, PoolSnapshot>
) => {
  const logsMap = await fetchLatestLogsByTarget()
  const dbList: any[] = statusPayload?.databases || []
  databases.value = DATABASES.map((descriptor) => {
    const statusItem = dbList.find((item) => (item.name || '').includes(descriptor.key))
    const pool = poolData[descriptor.key] ?? makeEmptyPool()
    const latestLog = logsMap.get(descriptor.key)
    const recordCount = Number(latestLog?.stats?.records || latestLog?.stats?.record_count || 0)
    const syncVersion = Number(latestLog?.stats?.version || latestLog?.stats?.sync_version || 0)
    const lastSync = latestLog
      ? formatDateTime(latestLog.completed_at || latestLog.started_at)
      : (statusItem?.last_sync ? formatDateTime(statusItem.last_sync) : '未知')
    return {
      key: descriptor.key,
      name: statusItem?.label || descriptor.label,
      status: statusItem?.status === 'error' ? 'offline' : 'online',
      latency: statusItem?.latency ?? estimateLatency(pool),
      recordCount,
      syncVersion,
      lastSync
    }
  })
}

const refreshAllData = async () => {
  isLoading.value = true
  try {
    const [dashboardRes, databaseRes, performanceRes] = await Promise.allSettled([
      api.get('/dashboard/stats'),
      api.get('/sync/databases/status'),
      api.get('/admin/operations/performance/insights')
    ])

    if (dashboardRes.status === 'fulfilled') {
      const data = dashboardRes.value.data
      stats.value.totalUsers = Number(data.users?.total ?? stats.value.totalUsers)
      stats.value.availableItems = Number(data.items?.available ?? stats.value.availableItems)
      stats.value.todayNewItems = Number(data.items?.today_new ?? stats.value.todayNewItems)
      stats.value.totalTransactionAmount = Number(data.transactions?.total_amount ?? stats.value.totalTransactionAmount)
      stats.value.todayCompletedTransactions = Number(data.transactions?.today_completed ?? stats.value.todayCompletedTransactions)
      stats.value.onlineUsers = Number(data.users?.online ?? Math.max(1, Math.round((stats.value.totalUsers || 0) * 0.2)))
    }

    let poolData: Record<string, PoolSnapshot> = {}
    if (performanceRes.status === 'fulfilled') {
      const perf = performanceRes.value.data
      slowQueries.value = perf.slow_queries || []
      runningQueries.value = perf.running_queries || []
      stats.value.avgQueryTime = perf.stats?.avg_query_time ?? stats.value.avgQueryTime
      stats.value.qps = perf.stats?.qps ?? stats.value.qps
      poolData = perf.connection_pools || {}
      applyConnectionPools(poolData)
      if (perf.health) {
        healthMetrics.value = {
          dbConnection: perf.health.dbConnection ?? healthMetrics.value.dbConnection,
          querySpeed: perf.health.querySpeed ?? healthMetrics.value.querySpeed,
          syncConsistency: perf.health.syncConsistency ?? healthMetrics.value.syncConsistency,
          resourceUsage: perf.health.resourceUsage ?? healthMetrics.value.resourceUsage,
          score: perf.health.score ?? systemHealth.value
        }
      }
    } else {
      slowQueries.value = []
      runningQueries.value = []
    }

    if (databaseRes.status === 'fulfilled') {
      await refreshDatabases(databaseRes.value.data, poolData)
    }

    message.success('性能数据已刷新')
  } catch (error) {
    handleError(error, '刷新性能数据失败')
  } finally {
    isLoading.value = false
  }
}

const toggleAutoRefresh = () => {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    refreshAllData()
    refreshInterval = window.setInterval(refreshAllData, 5000)
    message.info('已启动自动刷新（每5秒）')
  } else if (refreshInterval) {
    window.clearInterval(refreshInterval)
    refreshInterval = undefined
    message.info('已停止自动刷新')
  }
}

const getPoolColor = (usage: number) => {
  if (usage < 60) return '#18a058'
  if (usage < 80) return '#f0a020'
  return '#d03050'
}

const getHealthLabel = (score: number) => {
  if (score >= 90) return '优秀'
  if (score >= 80) return '良好'
  if (score >= 70) return '一般'
  if (score >= 60) return '较差'
  return '危险'
}

const syncDatabase = async (db: DatabaseRow) => {
  try {
    await api.post(`/admin/operations/databases/${db.key}/sync`)
    message.success(`${db.name} 同步任务已触发`)
  } catch (error) {
    handleError(error, `${db.name} 同步失败`)
  }
}

const viewDbDetails = async (db: DatabaseRow) => {
  try {
    const { data } = await api.get(`/admin/operations/databases/${db.key}`)
    currentDbLogs.value = (data.logs || []).map((log: any) => ({
      id: log.id,
      status: log.status,
      started_at: log.started_at,
      completed_at: log.completed_at,
      mode: log.mode || null
    }))
    currentDbTitle.value = db.name
    dbLogsModalVisible.value = true
  } catch (error) {
    handleError(error, `无法获取 ${db.name} 的日志`)
  }
}

const killQuery = async (queryId: string) => {
  try {
    await api.post(`/admin/operations/queries/${queryId}/kill`)
    runningQueries.value = runningQueries.value.filter((query) => String(query.id) !== String(queryId))
    message.success(`查询 ${queryId} 已终止`)
  } catch (error) {
    handleError(error, '终止查询失败')
  }
}

onMounted(() => {
  refreshAllData()
})

onUnmounted(() => {
  if (refreshInterval) {
    window.clearInterval(refreshInterval)
    refreshInterval = undefined
  }
})
</script>

<style scoped>
.admin-performance-container {
  padding: 20px;
  background: #f5f5f5;
}

.header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 20px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.header-bar h1 {
  margin: 0;
  font-size: 24px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 20px;
  margin-bottom: 20px;
}

.metric-card {
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.text-success {
  color: #18a058;
}

.text-primary {
  color: #2080f0;
}

.text-warning {
  color: #f0a020;
}

.sync-status-card,
.query-analysis-card,
.realtime-queries-card {
  margin-bottom: 20px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.sql-query {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  max-width: 400px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pool-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 15px;
  margin-bottom: 20px;
}

.health-dashboard {
  margin-top: 20px;
}

.health-score {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

.health-label {
  text-align: center;
}

.health-label .score {
  font-size: 32px;
  font-weight: bold;
}

.health-label .text {
  font-size: 14px;
  color: #999;
  margin-top: 5px;
}

.health-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
}
</style>
