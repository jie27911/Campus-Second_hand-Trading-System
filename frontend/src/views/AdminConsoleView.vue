<template>
  <div class="space-y-6">
    <section class="rounded-3xl border border-amber-200 bg-amber-50 p-6 text-amber-900">
      <p class="text-xs uppercase tracking-widest">Sync Control</p>
      <h1 class="mt-2 text-3xl font-semibold">数据库同步控制</h1>
      <p class="mt-2 text-sm text-amber-800/80">
        专业的数据库同步管理平台。监控同步状态、执行同步操作、管理数据库连接。
      </p>
    </section>

    <section v-if="!isAdmin" class="rounded-2xl border border-dashed border-slate-200 bg-white p-6 text-center">
      <h2 class="text-xl font-semibold text-slate-800">你当前没有管理员权限</h2>
      <p class="mt-2 text-sm text-slate-500">请联系平台负责人开通 market_admin 角色，或者前往市场页继续浏览。</p>
      <RouterLink class="mt-4 inline-flex items-center rounded-full bg-orange-500 px-4 py-2 text-white" to="/market">
        返回市场中心
      </RouterLink>
    </section>

    <template v-else>
      <!-- 顶部统计卡片 -->
      <section class="grid gap-4 md:grid-cols-4">
        <div class="rounded-2xl bg-white p-4 shadow">
          <div class="text-center">
            <div class="text-2xl font-bold text-green-600">{{ syncStats.success_count || 0 }}</div>
            <div class="text-sm text-slate-500">同步成功</div>
          </div>
        </div>
        <div class="rounded-2xl bg-white p-4 shadow">
          <div class="text-center">
            <div class="text-2xl font-bold text-red-600">{{ syncStats.failure_count || 0 }}</div>
            <div class="text-sm text-slate-500">今日冲突</div>
          </div>
        </div>
        <div class="rounded-2xl bg-white p-4 shadow">
          <div class="text-center">
            <div class="text-2xl font-bold text-orange-600">{{ syncStats.conflict_count || 0 }}</div>
            <div class="text-sm text-slate-500">冲突记录</div>
          </div>
        </div>
        <div class="rounded-2xl bg-white p-4 shadow">
          <div class="text-center">
            <div class="text-2xl font-bold text-blue-600">{{ syncStats.success_rate ? (syncStats.success_rate * 100).toFixed(1) : 0 }}%</div>
            <div class="text-sm text-slate-500">今日成功率（统计）</div>
          </div>
        </div>
      </section>

      <!-- 标签页导航 -->
      <n-tabs type="segment" animated class="bg-white rounded-2xl p-4 shadow">
        <!-- 1. 概览与监控 -->
        <n-tab-pane name="overview" tab="📊 概览与监控">
          <div class="space-y-6 mt-4">
            <!-- 数据库状态监控 -->
            <section class="rounded-xl border border-slate-100 p-4">
              <header class="flex items-center justify-between mb-4">
                <div>
                  <h3 class="text-lg font-semibold text-slate-900">数据库连接状态</h3>
                  <p class="text-xs text-slate-500">实时监控各节点连通性与延迟</p>
                </div>
                <n-button size="small" secondary :loading="refreshing" @click="refreshAll">
                  刷新状态
                </n-button>
              </header>
              <div class="grid gap-4 md:grid-cols-3">
                <div v-for="db in databases" :key="db.name" class="flex items-center justify-between p-4 border rounded-lg bg-slate-50">
                  <div class="flex items-center gap-3">
                    <div :class="['w-3 h-3 rounded-full', db.status === 'online' ? 'bg-green-500' : 'bg-red-500']"></div>
                    <div>
                      <div class="font-medium">{{ db.label }}</div>
                      <div class="text-sm text-slate-500">{{ db.type }}</div>
                    </div>
                  </div>
                  <div class="text-right">
                    <div class="text-sm font-mono">{{ db.latency || 'N/A' }}ms</div>
                    <div class="text-xs text-slate-400">{{ db.last_sync ? '已同步' : '未同步' }}</div>
                  </div>
                </div>
              </div>
            </section>

            <div class="grid gap-6 lg:grid-cols-2">
              <SyncStatusCard />
              
              <article class="rounded-xl border border-slate-100 p-4">
                <header>
                  <h3 class="text-lg font-semibold text-slate-900">系统运行概览</h3>
                </header>
                <ul class="mt-4 space-y-3 text-sm text-slate-600">
                  <li class="flex items-center justify-between p-2 bg-slate-50 rounded">
                    <span>实时同步监听器</span>
                    <span class="px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">运行中</span>
                  </li>
                  <li class="flex items-center justify-between p-2 bg-slate-50 rounded">
                    <span>定时同步链路</span>
                    <span :class="['px-2 py-1 text-xs font-medium rounded-full', scheduledConfigEnabledCount > 0 ? 'text-green-700 bg-green-100' : 'text-amber-700 bg-amber-100']">
                      {{ scheduledConfigEnabledCount > 0 ? `已启用 ${scheduledConfigEnabledCount} 条` : '未启用' }}
                    </span>
                  </li>
                  <li class="flex items-center justify-between p-2 bg-slate-50 rounded">
                    <span>邮件通知服务</span>
                    <span class="px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">正常</span>
                  </li>
                  <li class="flex items-center justify-between p-2 bg-slate-50 rounded">
                    <span>冲突检测引擎</span>
                    <span class="px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">活跃</span>
                  </li>
                </ul>
              </article>
            </div>
          </div>
        </n-tab-pane>

        <!-- 2. 冲突管理 -->
        <n-tab-pane name="conflicts" tab="⚠️ 冲突管理">
          <div class="space-y-4 mt-4">
            <div class="flex justify-end">
              <n-button size="small" ghost :loading="exportingConflicts" @click="exportConflicts">
                📥 导出冲突报告 (CSV)
              </n-button>
            </div>
            <ConflictTable />
          </div>
        </n-tab-pane>

        <!-- 3. 同步配置 -->
        <n-tab-pane name="configs" tab="⚙️ 同步配置">
          <div class="space-y-4 mt-4">
            <div class="flex justify-between items-center">
              <div>
                <h3 class="text-lg font-semibold">同步策略配置</h3>
                <p class="text-sm text-slate-500">管理实时与定时同步任务</p>
              </div>
              <n-button type="primary" @click="showCreateConfigModal = true">
                ➕ 添加配置
              </n-button>
            </div>
            <n-data-table
              :columns="configColumns"
              :data="syncConfigs"
              :loading="loadingConfigs"
              :pagination="false"
              size="small"
              class="mt-4"
            />
          </div>
        </n-tab-pane>

        <!-- 4. 数据迁移 -->
        <n-tab-pane name="migration" tab="📦 数据迁移">
          <div class="mt-4">
            <header class="mb-6">
              <h3 class="text-lg font-semibold text-slate-900">表迁移 / 整库迁移</h3>
              <p class="mt-1 text-sm text-slate-500">
                支持导出 ZIP（单表/多表）与导入（单表文件或整库 ZIP）。
              </p>
            </header>

            <div class="grid gap-6 lg:grid-cols-2">
              <!-- 导出区域 -->
              <div class="rounded-xl border border-slate-200 p-5 bg-slate-50">
                <div class="flex items-center justify-between mb-4">
                  <div class="font-medium text-slate-900 flex items-center gap-2">
                    📤 导出（迁移出）
                  </div>
                  <n-button size="small" secondary :loading="exportingTables" @click="exportPresetDatabase">
                    一键整库导出
                  </n-button>
                </div>

                <div class="space-y-4">
                  <n-form-item label="选择数据表">
                    <n-select
                      v-model:value="exportTables"
                      :options="tableOptions"
                      multiple
                      placeholder="选择要导出的表"
                    />
                  </n-form-item>
                  <n-form-item label="导出格式">
                    <n-select
                      v-model:value="exportFormat"
                      :options="formatOptions"
                      placeholder="选择格式"
                    />
                  </n-form-item>
                  
                  <div class="flex justify-end pt-2">
                    <n-button type="primary" ghost :loading="exportingTables" :disabled="!exportTables.length" @click="exportSelectedTables">
                      导出所选表
                    </n-button>
                  </div>
                </div>
              </div>

              <!-- 导入区域 -->
              <div class="rounded-xl border border-slate-200 p-5 bg-slate-50">
                <div class="font-medium text-slate-900 mb-4 flex items-center gap-2">
                  📥 导入（迁移入）
                </div>

                <div class="space-y-4">
                  <div class="grid grid-cols-2 gap-4">
                    <n-form-item label="导入模式">
                      <n-select
                        v-model:value="importMode"
                        :options="importModeOptions"
                        placeholder="模式"
                      />
                    </n-form-item>
                    <n-form-item label="单表目标">
                      <n-select
                        v-model:value="importTable"
                        :options="singleImportTableOptions"
                        placeholder="选择表"
                      />
                    </n-form-item>
                  </div>

                  <n-tabs type="segment" size="small">
                    <n-tab-pane name="single" tab="单表文件">
                      <div class="mt-2 space-y-3">
                        <div class="p-4 border-2 border-dashed border-slate-300 rounded-lg text-center hover:bg-slate-100 transition-colors relative">
                          <input
                            type="file"
                            accept=".json,.csv"
                            @change="onPickSingleFile"
                            class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                          />
                          <div class="text-sm text-slate-500">
                            <span v-if="singleFile">📄 {{ singleFile.name }}</span>
                            <span v-else>点击或拖拽 JSON/CSV 文件到此处</span>
                          </div>
                        </div>
                        <n-button
                          block
                          type="primary"
                          :loading="importingSingle"
                          :disabled="!importTable || !singleFile"
                          @click="importSingleTable"
                        >
                          开始单表导入
                        </n-button>
                      </div>
                    </n-tab-pane>
                    <n-tab-pane name="archive" tab="整库 ZIP">
                      <div class="mt-2 space-y-3">
                        <div class="p-4 border-2 border-dashed border-slate-300 rounded-lg text-center hover:bg-slate-100 transition-colors relative">
                          <input
                            type="file"
                            accept=".zip"
                            @change="onPickArchiveFile"
                            class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                          />
                          <div class="text-sm text-slate-500">
                            <span v-if="archiveFile">📦 {{ archiveFile.name }}</span>
                            <span v-else>点击或拖拽 ZIP 归档文件到此处</span>
                          </div>
                        </div>
                        <n-button
                          block
                          type="warning"
                          :loading="importingArchive"
                          :disabled="!archiveFile"
                          @click="importArchive"
                        >
                          开始整库导入
                        </n-button>
                      </div>
                    </n-tab-pane>
                  </n-tabs>
                </div>
              </div>
            </div>
          </div>
        </n-tab-pane>
      </n-tabs>
    </template>

    <!-- 创建同步配置模态框 -->
    <n-modal
      v-model:show="showCreateConfigModal"
      preset="card"
      title="创建同步配置"
      size="huge"
      :bordered="false"
      :segmented="false"
    >
      <n-form :model="configForm" :rules="configRules" ref="configFormRef" label-placement="top">
        <n-grid :cols="2" :x-gap="12" :y-gap="12">
          <n-gi>
            <n-form-item label="源数据库" path="source">
              <n-select
                v-model:value="configForm.source"
                :options="sourceDatabaseOptions"
                placeholder="选择源数据库"
              />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="目标数据库" path="target">
              <n-select
                v-model:value="configForm.target"
                :options="targetDatabaseOptions"
                placeholder="选择目标数据库"
              />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="同步模式" path="mode">
              <n-select
                v-model:value="configForm.mode"
                :options="modeOptions"
                placeholder="选择同步模式"
              />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="同步间隔(秒)" path="interval_seconds">
              <n-input-number
                v-model:value="configForm.interval_seconds"
                :min="1"
                :max="3600"
                placeholder="输入同步间隔"
              />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="启用" path="enabled">
              <n-switch v-model:value="configForm.enabled" />
            </n-form-item>
          </n-gi>
        </n-grid>
      </n-form>
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showCreateConfigModal = false">取消</n-button>
          <n-button type="primary" :loading="creatingConfig" @click="createConfig">创建</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, h, reactive } from 'vue';
import { storeToRefs } from 'pinia';
import { useMessage, NSelect, NInputNumber, NSwitch, NButton, NFormItem, NTabs, NTabPane, NModal, NForm, NGrid, NGi, NDataTable } from 'naive-ui';

import ConflictTable from '@/components/ConflictTable.vue';
import SyncStatusCard from '@/components/SyncStatusCard.vue';
import { useAuthStore } from '@/stores/auth';
import { useSyncStore } from '@/stores/sync';
import { http as api } from '@/lib/http';

const authStore = useAuthStore();
const syncStore = useSyncStore();
const isAdmin = computed(() => authStore.isAdmin);
const message = useMessage();

const refreshing = ref(false);

const tableOptions = [
  { label: 'users', value: 'users' },
  { label: 'user_profiles', value: 'user_profiles' },
  { label: 'user_preferences', value: 'user_preferences' },
  { label: 'categories', value: 'categories' },
  { label: 'campuses', value: 'campuses' },
  { label: 'items', value: 'items' },
  { label: 'item_images', value: 'item_images' },
  { label: 'transactions', value: 'transactions' },
  { label: 'messages', value: 'messages' }
]

const singleImportTableOptions = [
  { label: 'users', value: 'users' },
  { label: 'items', value: 'items' },
  { label: 'transactions', value: 'transactions' },
  { label: 'messages', value: 'messages' }
]

const formatOptions = [
  { label: 'json', value: 'json' },
  { label: 'csv', value: 'csv' }
]

const importModeOptions = [
  { label: 'append', value: 'append' },
  { label: 'replace', value: 'replace' },
  { label: 'update', value: 'update' }
]

const exportTables = ref<string[]>(['users', 'items', 'transactions', 'messages'])
const exportFormat = ref<'json' | 'csv'>('json')
const exportingTables = ref(false)

const importMode = ref<'append' | 'replace' | 'update'>('append')
const importTable = ref<string | null>('users')
const importingSingle = ref(false)
const importingArchive = ref(false)
const singleFile = ref<File | null>(null)
const archiveFile = ref<File | null>(null)

function onPickSingleFile(e: Event) {
  const input = e.target as HTMLInputElement
  singleFile.value = input.files?.[0] ?? null
}

function onPickArchiveFile(e: Event) {
  const input = e.target as HTMLInputElement
  archiveFile.value = input.files?.[0] ?? null
}

async function exportSelectedTables() {
  if (exportingTables.value) return
  exportingTables.value = true
  try {
    const response = await api.post(
      '/admin/operations/export',
      { tables: exportTables.value, format: exportFormat.value, schedule_only: false },
      { responseType: 'blob' }
    )
    const disposition = response.headers['content-disposition'] as string | undefined
    let filename = `campuswap-export-${Date.now()}.zip`
    if (disposition) {
      const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i)
      const encoded = match?.[1] || match?.[2]
      if (encoded) filename = decodeURIComponent(encoded)
    }
    const blob = new Blob([response.data], { type: 'application/zip' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.setAttribute('download', filename)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(link.href)
    message.success('导出成功')
  } finally {
    exportingTables.value = false
  }
}

async function exportPresetDatabase() {
  exportTables.value = ['campuses', 'categories', 'users', 'user_profiles', 'user_preferences', 'items', 'item_images', 'transactions', 'messages']
  await exportSelectedTables()
}

async function importSingleTable() {
  if (importingSingle.value) return
  if (!importTable.value || !singleFile.value) return
  importingSingle.value = true
  try {
    const fd = new FormData()
    fd.append('table', importTable.value)
    fd.append('mode', importMode.value)
    fd.append('file', singleFile.value)
    const { data } = await api.post('/admin/operations/import', fd)
    message.success(`单表导入完成：${data?.table ?? importTable.value}`)
  } finally {
    importingSingle.value = false
  }
}

async function importArchive() {
  if (importingArchive.value) return
  if (!archiveFile.value) return
  importingArchive.value = true
  try {
    const fd = new FormData()
    fd.append('mode', importMode.value)
    fd.append('file', archiveFile.value)
    const { data } = await api.post('/admin/operations/import-archive', fd)
    message.success(`整库导入完成：${data?.imported ?? 0} 行`)
  } finally {
    importingArchive.value = false
  }
}
const exportingConflicts = ref(false);
const syncStats = ref({
  success_count: 0,
  failure_count: 0,
  conflict_count: 0,
  success_rate: 0
});

type DatabaseHealthItem = {
  name: string;
  label: string;
  type: string;
  status: 'online' | 'offline';
  latency: number | null;
  last_sync: string | null;
};

const databases = ref<DatabaseHealthItem[]>([]);

const scheduledConfigEnabledCount = computed(() =>
  (syncConfigs.value || []).filter((c: any) => c?.enabled && String(c?.mode) === 'scheduled').length
);

// 同步配置相关
const syncConfigs = ref([]);
const loadingConfigs = ref(false);
const showCreateConfigModal = ref(false);
const creatingConfig = ref(false);
const configFormRef = ref(null);

const draftMode = reactive<Record<string, string>>({});
const draftInterval = reactive<Record<string, number>>({});
const draftEnabled = reactive<Record<string, boolean>>({});

// 配置表单
const configForm = ref({
  source: '',
  target: '',
  mode: 'realtime',
  interval_seconds: 30,
  enabled: true
});

// 表单验证规则
const configRules = {
  source: [
    { required: true, message: '请选择源数据库', trigger: 'blur' }
  ],
  target: [
    { required: true, message: '请选择目标数据库', trigger: 'blur' }
  ],
  mode: [
    { required: true, message: '请选择同步模式', trigger: 'blur' }
  ],
  interval_seconds: [
    { required: true, message: '请输入同步间隔', trigger: 'blur' },
    { type: 'number', min: 1, max: 3600, message: '间隔必须在1-3600秒之间', trigger: 'blur' }
  ]
};

// 数据库选项
// 注意：当前 sync-worker 只轮询 edge 的 sync_log（mariadb/postgres），mysql 不能作为源库。
const sourceDatabaseOptions = [
  { label: 'MariaDB Main', value: 'mariadb' },
  { label: 'PostgreSQL South', value: 'postgres' }
];

const targetDatabaseOptions = [
  { label: 'MySQL Hub', value: 'mysql' },
  { label: 'MariaDB Main', value: 'mariadb' },
  { label: 'PostgreSQL South', value: 'postgres' }
];

// 同步模式选项
const modeOptions = [
  { label: '实时同步', value: 'realtime' },
  { label: '定时周期同步', value: 'scheduled' }
];

// 同步配置表格列定义
const configColumns = [
  {
    title: '源数据库',
    key: 'source',
    width: 120
  },
  {
    title: '目标数据库',
    key: 'target',
    width: 120
  },
  {
    title: '模式',
    key: 'mode',
    width: 120,
    render: (row: any) => {
      const rowKey = String(row.id);
      return h(NSelect, {
        size: 'small',
        value: draftMode[rowKey] ?? row.mode,
        options: modeOptions,
        onUpdateValue: (v: string) => (draftMode[rowKey] = v),
        style: 'min-width: 96px;'
      });
    }
  },
  {
    title: '间隔(秒)',
    key: 'interval_seconds',
    width: 140,
    render: (row: any) => {
      const rowKey = String(row.id);
      return h(NInputNumber, {
        size: 'small',
        min: 1,
        max: 3600,
        value: draftInterval[rowKey] ?? row.interval_seconds,
        onUpdateValue: (v: number | null) => (draftInterval[rowKey] = Number(v ?? row.interval_seconds)),
        style: 'width: 120px;'
      });
    }
  },
  {
    title: '状态',
    key: 'enabled',
    width: 80,
    render: (row: any) => {
      const rowKey = String(row.id);
      return h(NSwitch, {
        value: draftEnabled[rowKey] ?? Boolean(row.enabled),
        onUpdateValue: (v: boolean) => (draftEnabled[rowKey] = v),
      });
    }
  },
  {
    title: '最后运行',
    key: 'last_run_at',
    width: 160,
    render: (row: any) => {
      const mode = String(row.mode ?? 'realtime');
      if (mode === 'realtime') return '实时模式';
      return row.last_run_at ? new Date(row.last_run_at).toLocaleString() : '从未运行';
    }
  },
  {
    title: '操作',
    key: 'actions',
    width: 160,
    render: (row: any) => h('div', { class: 'space-x-2' }, [
      h(NButton, {
        size: 'small',
        type: 'primary',
        onClick: () => saveConfig(row)
      }, '保存'),
      h(NButton, {
        size: 'small',
        type: 'error',
        onClick: () => deleteConfig(row)
      }, '删除')
    ])
  }
];

// 加载同步配置
async function loadSyncConfigs() {
  loadingConfigs.value = true;
  try {
    const response = await api.get('/sync/configs');
    const data = response.data;
    syncConfigs.value = Array.isArray(data) ? data : (data?.configs ?? []);
  } catch (error) {
    console.error('加载同步配置失败:', error);
    message.error('加载同步配置失败');
  } finally {
    loadingConfigs.value = false;
  }
}

async function saveConfig(config: any) {
  try {
    const id = String(config.id);
    const mode = draftMode[id] ?? config.mode;
    const interval_seconds = draftInterval[id] ?? config.interval_seconds;
    const enabled = draftEnabled[id] ?? Boolean(config.enabled);
    await api.put(`/sync/configs/${id}`, { mode, interval_seconds, enabled });
    await loadSyncConfigs();
    message.success('配置已保存');
  } catch (error) {
    console.error('保存配置失败:', error);
    message.error('保存配置失败');
  }
}

// 删除配置
async function deleteConfig(config: any) {
  try {
    await api.delete(`/sync/configs/${config.id}`);
    await loadSyncConfigs();
    message.success('配置已删除');
  } catch (error) {
    console.error('删除配置失败:', error);
    message.error('删除配置失败');
  }
}

// 创建配置
async function createConfig() {
  try {
    await configFormRef.value?.validate();
    creatingConfig.value = true;
    await api.post('/sync/configs', {
      source: configForm.value.source,
      target: configForm.value.target,
      mode: configForm.value.mode,
      interval_seconds: configForm.value.interval_seconds,
      enabled: Boolean(configForm.value.enabled),
    });
    await loadSyncConfigs();
    showCreateConfigModal.value = false;
    configForm.value = {
      source: '',
      target: '',
      mode: 'realtime',
      interval_seconds: 30,
      enabled: true
    };
    message.success('配置已创建');
  } catch (error) {
    if (error.type !== 'validation') {
      console.error('创建配置失败:', error);
      message.error('创建配置失败');
    }
  } finally {
    creatingConfig.value = false;
  }
}

// 加载同步统计数据
async function loadSyncStats() {
  try {
    const response = await api.get('/sync/stats');
    syncStats.value = response.data;
  } catch (error) {
    console.error('加载同步统计失败:', error);
  }
}

async function loadDatabaseStatus() {
  try {
    const { data } = await api.get('/sync/databases/status');
    const list = Array.isArray(data?.databases) ? data.databases : [];
    databases.value = list.map((row: any) => ({
      name: String(row.name ?? ''),
      label: String(row.label ?? row.name ?? ''),
      type: String(row.type ?? ''),
      status: row.status === 'healthy' ? 'online' : 'offline',
      latency: typeof row.latency === 'number' ? row.latency : null,
      last_sync: row.last_sync ? new Date(row.last_sync).toLocaleString() : null,
    }));
  } catch (error) {
    console.error('加载数据库状态失败:', error);
  }
}

async function refreshAll() {
  if (refreshing.value) return;
  refreshing.value = true;
  try {
    await Promise.all([
      loadSyncStats(),
      loadSyncConfigs(),
      loadDatabaseStatus(),
      syncStore.fetchStatus(),
      syncStore.fetchConflicts(),
    ]);
    message.success('状态已刷新');
  } finally {
    refreshing.value = false;
  }
}

async function exportConflicts() {
  if (exportingConflicts.value) return;
  exportingConflicts.value = true;
  try {
    const response = await api.get('/admin/operations/conflicts/export', {
      responseType: 'blob',
    });
    const disposition = response.headers['content-disposition'] as string | undefined;
    let filename = `conflicts-${Date.now()}.csv`;
    if (disposition) {
      const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i);
      const encoded = match?.[1] || match?.[2];
      if (encoded) {
        filename = decodeURIComponent(encoded);
      }
    }
    const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
    message.success('冲突报告已导出');
  } catch (error) {
    console.error('导出冲突报告失败:', error);
    message.error('导出失败，请稍后再试');
  } finally {
    exportingConflicts.value = false;
  }
}


function scrollToConfigs() {
  const el = document.getElementById('sync-configs');
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

watch(
  () => isAdmin.value,
  (authorized) => {
    if (authorized) {
      refreshAll();
    }
  },
  { immediate: true }
);

</script>
