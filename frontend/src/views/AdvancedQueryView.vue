<template>
  <div class="space-y-6">
    <header class="rounded-3xl bg-white p-6 shadow-sm border border-slate-100">
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold text-slate-900">🔍 高级数据查询</h1>
          <p class="mt-2 text-sm text-slate-600">
            执行复杂的多表关联查询和嵌套子查询，分析系统深层数据。
          </p>
        </div>
        <div class="flex gap-3">
          <button
            class="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white shadow hover:bg-slate-800 transition-colors flex items-center gap-2"
            @click="runSingle('baseline')"
            :disabled="loading"
          >
            <span v-if="loading" class="animate-spin">⏳</span>
            <span>{{ loading ? '查询中...' : '执行(优化前)' }}</span>
          </button>
          <button
            class="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white shadow hover:bg-indigo-700 transition-colors flex items-center gap-2"
            @click="runSingle('optimized')"
            :disabled="loading"
          >
            <span v-if="loading" class="animate-spin">⏳</span>
            <span>{{ loading ? '查询中...' : '执行(优化后)' }}</span>
          </button>
          <button
            class="rounded-lg bg-emerald-600 px-4 py-2 text-sm text-white shadow hover:bg-emerald-700 transition-colors flex items-center gap-2"
            @click="benchmark"
            :disabled="loading"
          >
            <span v-if="loading" class="animate-spin">⏳</span>
            <span>{{ loading ? '对比中...' : '对比性能' }}</span>
          </button>
        </div>
      </div>
    </header>

    <div class="grid gap-6 lg:grid-cols-3">
      <!-- 左侧：查询配置与SQL展示 -->
      <div class="lg:col-span-1 space-y-6">
        <section class="rounded-2xl bg-white p-5 shadow-sm border border-slate-100">
          <h3 class="font-semibold text-slate-900 mb-4">查询预设</h3>
          <div class="space-y-3">
            <div 
              v-for="(query, index) in predefinedQueries" 
              :key="index"
              class="p-3 rounded-lg border cursor-pointer transition-all"
              :class="selectedQuery === index ? 'border-indigo-500 bg-indigo-50' : 'border-slate-200 hover:border-indigo-300'"
              @click="selectedQuery = index"
            >
              <div class="font-medium text-slate-800">{{ query.name }}</div>
              <div class="text-xs text-slate-500 mt-1">{{ query.description }}</div>
            </div>
          </div>
        </section>

        <section class="rounded-2xl bg-slate-900 p-5 shadow-lg text-slate-300">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold text-white">SQL 预览</h3>
            <span class="text-xs bg-slate-700 px-2 py-1 rounded">Read Only</span>
          </div>
          <div class="flex gap-2 mb-3">
            <button
              class="text-xs px-2 py-1 rounded border transition-colors"
              :class="sqlVariant === 'baseline' ? 'bg-slate-700 border-slate-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-300 hover:border-slate-500'"
              @click="sqlVariant = 'baseline'"
            >
              优化前
            </button>
            <button
              class="text-xs px-2 py-1 rounded border transition-colors"
              :class="sqlVariant === 'optimized' ? 'bg-slate-700 border-slate-500 text-white' : 'bg-slate-800 border-slate-700 text-slate-300 hover:border-slate-500'"
              @click="sqlVariant = 'optimized'"
            >
              优化后
            </button>
            <select v-model="mode" class="ml-auto text-xs bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-200">
              <option value="run">run</option>
              <option value="explain">explain</option>
              <option value="explain_analyze">explain_analyze</option>
            </select>
          </div>
          <pre class="text-xs font-mono overflow-x-auto p-2 bg-slate-800 rounded-lg border border-slate-700"><code>{{ currentSQL }}</code></pre>
          
          <div class="mt-4 pt-4 border-t border-slate-700">
            <h4 class="text-xs font-semibold text-indigo-400 mb-2">性能对比</h4>
            <div v-if="benchmarkResult" class="text-xs text-slate-300 space-y-1">
              <div class="flex justify-between">
                <span class="text-slate-400">优化前 avg/ms</span>
                <span>{{ benchmarkResult.results.baseline.summary.avg_ms }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">优化后 avg/ms</span>
                <span>{{ benchmarkResult.results.optimized.summary.avg_ms }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">runs</span>
                <span>{{ benchmarkResult.runs }}</span>
              </div>
            </div>
            <div v-else class="text-xs text-slate-400">点击“对比性能”生成结果。</div>
          </div>
        </section>
      </div>

      <!-- 右侧：查询结果 -->
      <div class="lg:col-span-2">
        <section class="rounded-2xl bg-white shadow-sm border border-slate-100 h-full flex flex-col">
          <div class="p-5 border-b border-slate-100 flex justify-between items-center">
            <h3 class="font-semibold text-slate-900">查询结果</h3>
            <span v-if="lastRunTime" class="text-xs text-slate-500">耗时: {{ executionTime }}ms</span>
          </div>
          
          <div class="flex-1 p-5 overflow-auto">
            <div v-if="!hasRun" class="h-full flex flex-col items-center justify-center text-slate-400 min-h-[300px]">
              <span class="text-4xl mb-3">🔍</span>
              <p>点击"执行查询"获取数据</p>
            </div>

            <table v-else class="w-full text-sm text-left">
              <thead class="text-xs text-slate-500 uppercase bg-slate-50">
                <tr>
                  <th v-for="col in columns" :key="col" class="px-4 py-3">{{ col }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, idx) in results" :key="idx" class="border-b border-slate-100 hover:bg-slate-50">
                  <td v-for="col in columns" :key="col" class="px-4 py-3 font-medium text-slate-900">
                    {{ row[col] }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <div v-if="hasRun" class="p-4 border-t border-slate-100 bg-slate-50 rounded-b-2xl flex justify-between items-center text-xs text-slate-500">
            <span>共 {{ results.length }} 条记录</span>
            <div class="flex gap-2">
              <button class="px-3 py-1 bg-white border rounded hover:bg-slate-100">上一页</button>
              <button class="px-3 py-1 bg-white border rounded hover:bg-slate-100">下一页</button>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { http as api } from '@/lib/http'

const loading = ref(false)
const hasRun = ref(false)
const lastRunTime = ref<Date | null>(null)
const executionTime = ref(0)
const selectedQuery = ref(0)
const sqlVariant = ref<'baseline' | 'optimized'>('optimized')
const mode = ref<'run' | 'explain' | 'explain_analyze'>('run')
const benchmarkResult = ref<any | null>(null)

const predefinedQueries = [
  {
    name: '卖家成交额 + 冲突统计（含嵌套子查询）',
    description: '多表关联(users/items/transactions) + 嵌套子查询(conflict_records)，用于展示优化前后差异。',
    baseline: `SELECT
  u.id AS user_id,
  u.username AS username,
  (SELECT COUNT(*) FROM items i WHERE i.seller_id = u.id) AS item_count,
  (SELECT COALESCE(SUM(t.final_amount), 0) FROM transactions t WHERE t.seller_id = u.id AND t.status = 'completed') AS total_sales,
  (SELECT COUNT(*)
     FROM conflict_records cr
     JOIN items i2 ON i2.id = CAST(cr.record_id AS UNSIGNED)
    WHERE cr.table_name = 'items'
      AND i2.seller_id = u.id
  ) AS item_conflicts
FROM users u
WHERE u.is_active = 1
ORDER BY total_sales DESC
LIMIT 20;`,
    optimized: `WITH
seller_items AS (
  SELECT seller_id, COUNT(*) AS item_count
  FROM items
  GROUP BY seller_id
),
seller_sales AS (
  SELECT seller_id, COALESCE(SUM(final_amount), 0) AS total_sales
  FROM transactions
  WHERE status = 'completed'
  GROUP BY seller_id
),
seller_conflicts AS (
  SELECT i.seller_id, COUNT(*) AS item_conflicts
  FROM conflict_records cr
  JOIN items i ON i.id = CAST(cr.record_id AS UNSIGNED)
  WHERE cr.table_name = 'items'
  GROUP BY i.seller_id
)
SELECT
  u.id AS user_id,
  u.username AS username,
  COALESCE(si.item_count, 0) AS item_count,
  COALESCE(ss.total_sales, 0) AS total_sales,
  COALESCE(sc.item_conflicts, 0) AS item_conflicts
FROM users u
LEFT JOIN seller_items si ON si.seller_id = u.id
LEFT JOIN seller_sales ss ON ss.seller_id = u.id
LEFT JOIN seller_conflicts sc ON sc.seller_id = u.id
WHERE u.is_active = 1
ORDER BY total_sales DESC
LIMIT 20;`
  },
  {
    name: '校区 x 分类商品统计（多表 JOIN + 聚合）',
    description: 'categories/items/campuses 多表连接与聚合',
    baseline: `SELECT
  c.name AS category_name,
  ca.name AS campus_name,
  COUNT(*) AS item_count,
  ROUND(AVG(i.price), 2) AS avg_price
FROM items i
JOIN categories c ON c.id = i.category_id
JOIN campuses ca ON ca.id = i.campus_id
WHERE i.status = 'available'
GROUP BY c.id, ca.id, c.name, ca.name
ORDER BY item_count DESC
LIMIT 50;`,
    optimized: `SELECT
  c.name AS category_name,
  ca.name AS campus_name,
  s.item_count,
  s.avg_price
FROM (
  SELECT
    i.category_id,
    i.campus_id,
    COUNT(*) AS item_count,
    ROUND(AVG(i.price), 2) AS avg_price
  FROM items i
  WHERE i.status = 'available'
  GROUP BY i.category_id, i.campus_id
) s
JOIN categories c ON c.id = s.category_id
JOIN campuses ca ON ca.id = s.campus_id
ORDER BY s.item_count DESC
LIMIT 50;`
  }
]

const currentSQL = computed(() => {
  const q = predefinedQueries[selectedQuery.value]
  return sqlVariant.value === 'baseline' ? q.baseline : q.optimized
})

const columns = ref<string[]>([])
const results = ref<any[]>([])

function hydrateTable(rows: any[]) {
  results.value = rows || []
  columns.value = rows && rows.length ? Object.keys(rows[0]) : []
}

async function runSingle(which: 'baseline' | 'optimized') {
  loading.value = true
  benchmarkResult.value = null
  try {
    const q = predefinedQueries[selectedQuery.value]
    const query = which === 'baseline' ? q.baseline : q.optimized
    const isExplain = mode.value !== 'run'
    const payload = {
      database: 'mysql',
      query,
      mode: isExplain ? 'explain' : 'run'
    }
    const started = performance.now()
    const { data } = await api.post('/admin/operations/sql', payload)
    const ended = performance.now()
    hasRun.value = true
    lastRunTime.value = new Date()
    executionTime.value = Math.round(data?.duration_ms ?? (ended - started))
    hydrateTable(data?.rows ?? [])
  } finally {
    loading.value = false
  }
}

async function benchmark() {
  loading.value = true
  try {
    const q = predefinedQueries[selectedQuery.value]
    const payload = {
      database: 'mysql',
      baseline_query: q.baseline,
      optimized_query: q.optimized,
      runs: 5,
      mode: mode.value,
      fetch_rows: 200
    }
    const { data } = await api.post('/admin/operations/sql/benchmark', payload)
    benchmarkResult.value = data
    // Show optimized query sample rows by default
    const sample = data?.results?.optimized?.rows ?? []
    hasRun.value = true
    lastRunTime.value = new Date()
    executionTime.value = Math.round(data?.results?.optimized?.summary?.avg_ms ?? 0)
    hydrateTable(sample)
  } finally {
    loading.value = false
  }
}
</script>
