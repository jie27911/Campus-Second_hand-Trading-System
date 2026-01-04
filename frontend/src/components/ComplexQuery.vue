<template>
  <div class="complex-query-container">
    <h2>🔍 复杂数据库查询</h2>
    <p class="description">执行包含多表连接、嵌套子查询的复杂SQL查询，验证数据库性能优化</p>

    <n-card title="查询配置" class="query-config-card">
      <n-space vertical size="large">
        <n-form :model="queryForm" label-placement="top">
          <n-grid :cols="24" :x-gap="12">
            <n-grid-item :span="12">
              <n-form-item label="查询类型" path="queryType">
                <n-select
                  v-model:value="queryForm.queryType"
                  :options="queryTypeOptions"
                  placeholder="选择查询类型"
                />
              </n-form-item>
            </n-grid-item>
            <n-grid-item :span="12">
              <n-form-item label="数据库" path="database">
                <n-select
                  v-model:value="queryForm.database"
                  :options="databaseOptions"
                  placeholder="选择数据库"
                />
              </n-form-item>
            </n-grid-item>
          </n-grid>

          <n-form-item label="自定义SQL查询" path="customSql">
            <n-input
              v-model:value="queryForm.customSql"
              type="textarea"
              :rows="6"
              placeholder="输入SQL查询语句..."
            />
          </n-form-item>

          <n-space>
            <n-button type="primary" :loading="executing" @click="executeQuery">
              执行查询
            </n-button>
            <n-button @click="loadPresetQuery">
              加载预设查询
            </n-button>
            <n-button type="info" @click="showPerformanceTips">
              性能优化提示
            </n-button>
          </n-space>
        </n-form>
      </n-space>
    </n-card>

    <n-card v-if="queryResult" title="查询结果" class="result-card">
      <n-space vertical size="large">
        <div class="result-meta">
          <n-statistic label="执行时间" :value="queryResult.executionTime + 'ms'" />
          <n-statistic label="结果行数" :value="queryResult.rowCount" />
          <n-statistic label="影响行数" :value="queryResult.affectedRows || 0" />
        </div>

        <n-data-table
          :columns="resultColumns"
          :data="queryResult.data"
          :pagination="pagination"
          max-height="400"
        />
      </n-space>
    </n-card>

    <n-card title="预设查询示例" class="preset-card">
      <n-space vertical>
        <n-collapse>
          <n-collapse-item title="多表连接查询 - 用户商品统计" name="1">
            <pre class="sql-code">{{ presetQueries.userItemStats }}</pre>
            <n-button size="small" @click="usePresetQuery('userItemStats')">
              使用此查询
            </n-button>
          </n-collapse-item>

          <n-collapse-item title="嵌套子查询 - 高价值用户" name="2">
            <pre class="sql-code">{{ presetQueries.highValueUsers }}</pre>
            <n-button size="small" @click="usePresetQuery('highValueUsers')">
              使用此查询
            </n-button>
          </n-collapse-item>

          <n-collapse-item title="聚合查询 - 分类销售统计" name="3">
            <pre class="sql-code">{{ presetQueries.categorySales }}</pre>
            <n-button size="small" @click="usePresetQuery('categorySales')">
              使用此查询
            </n-button>
          </n-collapse-item>

          <n-collapse-item title="跨库同步状态查询" name="4">
            <pre class="sql-code">{{ presetQueries.syncStatus }}</pre>
            <n-button size="small" @click="usePresetQuery('syncStatus')">
              使用此查询
            </n-button>
          </n-collapse-item>
        </n-collapse>
      </n-space>
    </n-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useMessage } from 'naive-ui'
import { http as api } from '@/lib/http'

const message = useMessage()

const queryForm = reactive({
  queryType: 'select',
  database: 'mysql',
  customSql: ''
})

const queryTypeOptions = [
  { label: 'SELECT 查询', value: 'select' },
  { label: '统计查询', value: 'stats' },
  { label: '性能测试', value: 'performance' }
]

const databaseOptions = [
  { label: 'MySQL (中央Hub)', value: 'mysql' },
  { label: 'MariaDB (本部)', value: 'mariadb' },
  { label: 'PostgreSQL (南校区)', value: 'postgres' }
]

const executing = ref(false)
const queryResult = ref(null)
const pagination = { pageSize: 20 }

const resultColumns = computed(() => {
  if (!queryResult.value?.data?.length) return []
  return Object.keys(queryResult.value.data[0]).map(key => ({
    title: key,
    key,
    width: 150
  }))
})

const presetQueries = {
  userItemStats: `
SELECT
  u.username,
  u.email,
  COUNT(i.id) as item_count,
  SUM(i.price) as total_value,
  AVG(i.price) as avg_price,
  MAX(i.created_at) as last_publish
FROM users u
LEFT JOIN items i ON u.id = i.seller_id
WHERE u.is_active = 1
GROUP BY u.id, u.username, u.email
HAVING COUNT(i.id) > 0
ORDER BY total_value DESC
LIMIT 10;
  `.trim(),

  highValueUsers: `
SELECT *
FROM users
WHERE id IN (
  SELECT seller_id
  FROM items
  WHERE price > (
    SELECT AVG(price) FROM items
  )
  GROUP BY seller_id
  HAVING COUNT(*) > 2
)
ORDER BY created_at DESC;
  `.trim(),

  categorySales: `
SELECT
  c.name as category_name,
  COUNT(i.id) as item_count,
  SUM(i.price) as total_value,
  AVG(i.price) as avg_price,
  COUNT(CASE WHEN i.status = 'sold' THEN 1 END) as sold_count
FROM categories c
LEFT JOIN items i ON c.id = i.category_id
GROUP BY c.id, c.name
ORDER BY total_value DESC;
  `.trim(),

  syncStatus: `
SELECT
  'items' as table_name,
  COUNT(*) as total_records,
  COUNT(sync_version) as synced_records,
  MAX(updated_at) as last_update
FROM items
UNION ALL
SELECT
  'users' as table_name,
  COUNT(*) as total_records,
  COUNT(sync_version) as synced_records,
  MAX(updated_at) as last_update
FROM users;
  `.trim()
}

async function executeQuery() {
  if (!queryForm.customSql.trim()) {
    message.warning('请输入SQL查询语句')
    return
  }

  executing.value = true
  try {
    const response = await api.post('/admin/tables/complex-query', {
      sql: queryForm.customSql,
      database: queryForm.database
    })
    queryResult.value = response.data
    message.success('查询执行成功')
  } catch (error) {
    console.error('查询执行失败:', error)
    message.error('查询执行失败，请检查SQL语法')
  } finally {
    executing.value = false
  }
}

function loadPresetQuery() {
  // 加载预设查询的逻辑
  message.info('请选择一个预设查询')
}

function usePresetQuery(key: string) {
  queryForm.customSql = presetQueries[key]
  message.success('已加载预设查询')
}

function showPerformanceTips() {
  message.info('性能优化提示：使用索引、避免全表扫描、合理分页')
}
</script>

<style scoped>
.complex-query-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.description {
  color: #666;
  margin-bottom: 20px;
}

.query-config-card,
.result-card,
.preset-card {
  margin-bottom: 20px;
}

.sql-code {
  background: #f5f5f5;
  padding: 10px;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.result-meta {
  display: flex;
  gap: 20px;
}
</style>