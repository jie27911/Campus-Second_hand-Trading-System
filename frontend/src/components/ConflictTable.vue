<template>
  <div class="p-4 bg-white rounded-xl shadow space-y-3">
    <header class="flex items-center justify-between">
      <div>
        <p class="text-sm text-slate-500">冲突记录</p>
        <h2 class="text-lg font-semibold">待处理事件</h2>
      </div>
      <div class="flex items-center gap-3">
        <div v-if="isAdmin" class="flex items-center gap-2 text-sm text-slate-500">
          <span>显示全部</span>
          <n-switch v-model:value="showAll" size="small" @update:value="applyFilter" />
        </div>
        <button class="text-sm text-slate-500" :disabled="loadingConflicts" @click="fetch">
          {{ loadingConflicts ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </header>

    <p v-if="!isAdmin" class="text-sm text-slate-500">仅管理员可查看冲突详情。</p>

    <div v-else class="overflow-x-auto">
      <table class="min-w-full text-sm">
        <thead>
          <tr class="text-left text-slate-500 text-xs uppercase">
            <th class="py-2">表</th>
            <th class="py-2">记录</th>
            <th class="py-2">来源 → 目标</th>
            <th class="py-2">时间</th>
            <th class="py-2">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="conflicts.length === 0">
            <td colspan="5" class="py-6 text-center text-slate-400">暂无冲突，运行稳定。</td>
          </tr>
          <tr
            v-for="conflict in conflicts"
            :key="conflict.id"
            class="border-t cursor-pointer hover:bg-slate-50"
            @click="openDetail(conflict)"
          >
            <td class="py-2 font-mono text-xs">{{ conflict.table_name }}</td>
            <td class="py-2">#{{ conflict.record_id }}</td>
            <td class="py-2">
              <span class="font-semibold">{{ conflict.source }}</span>
              <span> → </span>
              <span class="font-semibold">{{ conflict.target }}</span>
            </td>
            <td class="py-2 text-slate-500">{{ formatDate(conflict.created_at) }}</td>
            <td class="py-2">
              <div class="flex gap-2 text-xs">
                <button
                  class="rounded bg-emerald-100 px-2 py-1 text-emerald-700 disabled:opacity-60"
                  :disabled="isReadOnly || resolvingConflictId === conflict.id"
                  @click.stop="() => resolveAction(conflict.id, 'source')"
                >
                  {{ resolvingConflictId === conflict.id ? '处理中…' : '采纳来源' }}
                </button>
                <button
                  class="rounded bg-amber-100 px-2 py-1 text-amber-700 disabled:opacity-60"
                  :disabled="isReadOnly || resolvingConflictId === conflict.id"
                  @click.stop="() => resolveAction(conflict.id, 'target')"
                >
                  {{ resolvingConflictId === conflict.id ? '处理中…' : '保留目标' }}
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <n-modal v-model:show="detailVisible" preset="card" :title="detailTitle" style="width: min(1100px, 94vw)">
      <div v-if="selectedConflict" class="space-y-4">
        <div class="text-sm text-slate-600">
          <div><span class="font-semibold">表：</span><span class="font-mono">{{ selectedConflict.table_name }}</span></div>
          <div><span class="font-semibold">记录：</span>#{{ selectedConflict.record_id }}</div>
          <div><span class="font-semibold">来源 → 目标：</span>{{ selectedConflict.source }} → {{ selectedConflict.target }}</div>
          <div><span class="font-semibold">时间：</span>{{ formatDate(selectedConflict.created_at) }}</div>
          <div v-if="conflictReason" class="mt-1">
            <span class="font-semibold">原因：</span><span>{{ conflictReason }}</span>
          </div>
        </div>

        <div v-if="sourceVClockText || targetVClockText" class="grid gap-3 md:grid-cols-2">
          <div class="rounded-lg bg-slate-50 p-3">
            <div class="text-xs font-semibold text-slate-700">来源版本 v_clock</div>
            <pre class="mt-2 overflow-auto text-xs leading-5 text-slate-800">{{ sourceVClockText || '（无）' }}</pre>
          </div>
          <div class="rounded-lg bg-slate-50 p-3">
            <div class="text-xs font-semibold text-slate-700">目标版本 v_clock</div>
            <pre class="mt-2 overflow-auto text-xs leading-5 text-slate-800">{{ targetVClockText || '（无）' }}</pre>
          </div>
        </div>

        <div class="rounded-lg border border-slate-200">
          <div class="flex items-center justify-between border-b border-slate-200 bg-white px-3 py-2">
            <div class="text-sm font-semibold text-slate-800">字段差异（来源 vs 目标）</div>
            <div class="text-xs text-slate-500" v-if="diffRows.length">仅展示差异字段：{{ diffRows.length }} 项</div>
          </div>

          <div v-if="!diffRows.length" class="p-3 text-sm text-slate-500">
            未检测到字段差异（或 payload 缺少来源/目标快照）。
          </div>

          <div v-else class="overflow-x-auto">
            <table class="min-w-full text-xs">
              <thead>
                <tr class="text-left text-slate-500 uppercase">
                  <th class="px-3 py-2">字段</th>
                  <th class="px-3 py-2">来源</th>
                  <th class="px-3 py-2">目标</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in diffRows" :key="row.key" class="border-t">
                  <td class="px-3 py-2 font-mono text-slate-700 align-top">{{ row.key }}</td>
                  <td class="px-3 py-2 align-top">
                    <pre class="whitespace-pre-wrap break-words text-slate-800">{{ row.source }}</pre>
                  </td>
                  <td class="px-3 py-2 align-top">
                    <pre class="whitespace-pre-wrap break-words text-slate-800">{{ row.target }}</pre>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <details class="rounded-lg bg-slate-50 p-3">
          <summary class="cursor-pointer text-xs font-semibold text-slate-700">查看原始 payload</summary>
          <pre class="mt-2 overflow-auto text-xs leading-5 text-slate-800">{{ prettyPayload(selectedConflict.payload) }}</pre>
        </details>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useMessage } from 'naive-ui';

import { useAuthStore } from '@/stores/auth';
import { useSyncStore, type ConflictRecord } from '@/stores/sync';

const message = useMessage();
const authStore = useAuthStore();
const syncStore = useSyncStore();
const { conflicts, loadingConflicts, resolvingConflictId } = storeToRefs(syncStore);
const isAdmin = computed(() => authStore.isAdmin);

const showAll = ref(false);
const isReadOnly = computed(() => showAll.value);

const detailVisible = ref(false);
const selectedConflict = ref<ConflictRecord | null>(null);
const detailTitle = computed(() => {
  if (!selectedConflict.value) return '冲突详情';
  return `冲突详情 #${selectedConflict.value.id}`;
});

function fetch() {
  syncStore.fetchConflicts();
}

function applyFilter() {
  syncStore.fetchConflicts({ page: 1, filter: showAll.value ? 'all' : 'unresolved' });
}

async function resolveAction(id: string, strategy: 'source' | 'target') {
  if (isReadOnly.value) {
    message.warning('只读模式：无法裁决历史冲突');
    return;
  }
  try {
    await syncStore.resolveConflict(id, strategy);
    message.success(strategy === 'source' ? '已采纳来源版本' : '已保留目标版本');
  } catch (error) {
    console.error(error);
    message.error('冲突处理失败');
  }
}

function formatDate(input: string) {
  return new Date(input).toLocaleString();
}

function openDetail(conflict: ConflictRecord) {
  selectedConflict.value = conflict;
  detailVisible.value = true;
}

function prettyPayload(payload: Record<string, unknown>) {
  try {
    return JSON.stringify(payload ?? {}, null, 2);
  } catch {
    return String(payload);
  }
}

function safeStringify(value: unknown) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function toCompactString(value: unknown) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function normalizeForCompare(value: unknown): unknown {
  if (value === null || value === undefined) return null;

  // Treat boolean-like values as equivalent.
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'number' && (value === 0 || value === 1)) return value;

  if (typeof value === 'string') {
    const trimmed = value.trim();
    const lower = trimmed.toLowerCase();
    if (lower === 'true') return 1;
    if (lower === 'false') return 0;
    if (trimmed === '0' || trimmed === '1') return Number(trimmed);

    // Numeric strings: normalize small/decimal numeric strings to numbers for comparison.
    // Avoid converting very large integers (e.g., snowflake ids) to prevent precision loss.
    const isPlainInt = /^-?\d+$/.test(trimmed);
    if (isPlainInt && trimmed.replace('-', '').length > 15) {
      return trimmed;
    }
    const isNumeric = /^-?\d+(?:\.\d+)?$/.test(trimmed);
    if (isNumeric) {
      const n = Number(trimmed);
      if (Number.isFinite(n)) return n;
    }
    return trimmed;
  }

  return value;
}

function normalizeRecordSnapshot(raw: unknown): Record<string, unknown> {
  if (!raw || typeof raw !== 'object') return {};
  const obj = raw as Record<string, unknown>;
  // Some payloads may wrap the real row under data/record.
  const inner = (obj.data as any) ?? (obj.record as any);
  if (inner && typeof inner === 'object') return inner as Record<string, unknown>;
  return obj;
}

function extractConflictSnapshots(payload: Record<string, unknown>) {
  // Some backends wrap the conflict details under payload.data.
  const base = (payload?.data && typeof payload.data === 'object') ? (payload.data as Record<string, unknown>) : payload;

  const reason = (base?.reason as any) ?? '';
  const sourceRaw = (base?.source_new as any) ?? (base?.source_old as any) ?? null;
  const targetRaw = (base?.target_current as any) ?? null;

  const sourceSnapshot = normalizeRecordSnapshot(sourceRaw);
  const targetSnapshot = normalizeRecordSnapshot(targetRaw);

  const sourceVClock = (sourceRaw && typeof sourceRaw === 'object') ? (sourceRaw as any).v_clock : undefined;
  const targetVClock = (targetRaw && typeof targetRaw === 'object') ? (targetRaw as any).v_clock : undefined;

  return {
    reason: typeof reason === 'string' ? reason : safeStringify(reason),
    sourceSnapshot,
    targetSnapshot,
    sourceVClock,
    targetVClock,
  };
}

const conflictReason = computed(() => {
  if (!selectedConflict.value) return '';
  const payload = (selectedConflict.value.payload ?? {}) as Record<string, unknown>;
  return extractConflictSnapshots(payload).reason;
});

const sourceVClockText = computed(() => {
  if (!selectedConflict.value) return '';
  const payload = (selectedConflict.value.payload ?? {}) as Record<string, unknown>;
  const { sourceVClock } = extractConflictSnapshots(payload);
  return safeStringify(sourceVClock);
});

const targetVClockText = computed(() => {
  if (!selectedConflict.value) return '';
  const payload = (selectedConflict.value.payload ?? {}) as Record<string, unknown>;
  const { targetVClock } = extractConflictSnapshots(payload);
  return safeStringify(targetVClock);
});

const diffRows = computed(() => {
  if (!selectedConflict.value) return [] as Array<{ key: string; source: string; target: string }>;
  const payload = (selectedConflict.value.payload ?? {}) as Record<string, unknown>;
  const { sourceSnapshot, targetSnapshot } = extractConflictSnapshots(payload);

  const keys = new Set<string>([...Object.keys(sourceSnapshot || {}), ...Object.keys(targetSnapshot || {})]);
  const sortedKeys = Array.from(keys).sort();

  const rows: Array<{ key: string; source: string; target: string }> = [];
  for (const key of sortedKeys) {
    if (key === 'v_clock') continue;
    const s = (sourceSnapshot as any)?.[key];
    const t = (targetSnapshot as any)?.[key];

    const sNorm = normalizeForCompare(s);
    const tNorm = normalizeForCompare(t);
    if (toCompactString(sNorm) === toCompactString(tNorm)) {
      continue;
    }

    rows.push({ key, source: safeStringify(s), target: safeStringify(t) });
  }
  // Avoid huge tables in the modal.
  return rows.slice(0, 80);
});

onMounted(() => {
  if (isAdmin.value) {
    applyFilter();
  }
});
</script>
