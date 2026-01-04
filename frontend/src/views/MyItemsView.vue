<template>
  <div class="my-items min-h-screen bg-gray-50">
    <div class="max-w-6xl mx-auto py-6 px-4">
      <div class="bg-white rounded-lg shadow p-6">
        <h1 class="text-2xl font-bold mb-6">📦 我的商品</h1>
        <n-spin :show="loading">
          <n-tabs v-model:value="activeTab" type="segment" animated>
            <n-tab-pane name="selling" tab="在售中">
              <div v-if="sellingItems.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
                <n-card v-for="item in sellingItems" :key="item.id" hoverable>
                  <div class="flex gap-4">
                    <div class="w-24 h-24 bg-gradient-to-br from-blue-100 to-purple-100 rounded flex items-center justify-center flex-shrink-0 overflow-hidden">
                      <img
                        :src="getItemImageUrl(item.images, item.id)"
                        :alt="item.title"
                        class="w-full h-full object-cover"
                      />
                    </div>
                    <div class="flex-1 min-w-0">
                      <h3 class="font-bold mb-1 truncate">{{ item.title }}</h3>
                      <p class="text-red-500 font-bold mb-2">¥{{ item.price }}</p>
                      <div class="text-sm text-gray-500 space-y-1">
                        <div>👁️ {{ item.views }} 浏览</div>
                        <div>💬 {{ item.inquiries }} 咨询</div>
                      </div>
                      <div class="flex gap-2 mt-3">
                        <n-button size="small" @click="editItem(item)">编辑</n-button>
                        <n-button size="small" type="error" @click="removeItem(item)">下架</n-button>
                      </div>
                    </div>
                  </div>
                </n-card>
              </div>
              <div v-else class="text-center text-gray-400 py-12">
                <span class="text-4xl block mb-2">🤔</span>
                <p>还没有在售商品，快去发布吧～</p>
              </div>
            </n-tab-pane>

            <n-tab-pane name="sold" tab="已售出">
              <div v-if="soldItems.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
                <n-card v-for="item in soldItems" :key="item.id">
                  <div class="flex gap-4">
                    <div class="w-24 h-24 bg-gray-200 rounded flex items-center justify-center flex-shrink-0 overflow-hidden">
                      <img
                        :src="getItemImageUrl(item.images, item.id)"
                        :alt="item.title"
                        class="w-full h-full object-cover opacity-80"
                      />
                    </div>
                    <div class="flex-1">
                      <h3 class="font-bold mb-1">{{ item.title }}</h3>
                      <p class="text-gray-500 mb-2">¥{{ item.price }}</p>
                      <n-tag type="success" size="small">已售出</n-tag>
                      <div class="text-sm text-gray-500 mt-2">
                        成交时间: {{ formatDate(item.updated_at || item.created_at) }}
                      </div>
                    </div>
                  </div>
                </n-card>
              </div>
              <div v-else class="text-center text-gray-400 py-12">
                <span class="text-4xl block mb-2">🕒</span>
                <p>还没有售出的商品</p>
              </div>
            </n-tab-pane>

            <n-tab-pane name="removed" tab="已下架">
              <div v-if="removedItems.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
                <n-card v-for="item in removedItems" :key="item.id">
                  <div class="flex gap-4">
                    <div class="w-24 h-24 bg-gray-100 rounded flex items-center justify-center flex-shrink-0 overflow-hidden">
                      <img
                        :src="getItemImageUrl(item.images, item.id)"
                        :alt="item.title"
                        class="w-full h-full object-cover grayscale"
                      />
                    </div>
                    <div class="flex-1">
                      <h3 class="font-bold mb-1">{{ item.title }}</h3>
                      <p class="text-gray-500 mb-2">¥{{ item.price }}</p>
                      <n-tag size="small">已下架</n-tag>
                      <div class="text-sm text-gray-500 mt-2">
                        下架时间: {{ formatDate(item.updated_at || item.created_at) }}
                      </div>
                    </div>
                  </div>
                </n-card>
              </div>
              <div v-else class="text-center text-gray-400 py-12">
                <span class="text-6xl block mb-4">📭</span>
                <p>暂无下架商品</p>
              </div>
            </n-tab-pane>
          </n-tabs>
        </n-spin>
      </div>
    </div>

    <!-- Edit Item Modal -->
    <n-modal
      v-model:show="editModalVisible"
      preset="card"
      title="编辑商品"
      size="huge"
      :bordered="false"
      :segmented="false"
    >
      <n-form :model="editForm" label-placement="top">
        <n-form-item label="商品标题" path="title">
          <n-input v-model:value="editForm.title" placeholder="请输入商品标题" />
        </n-form-item>
        
        <n-form-item label="商品描述" path="description">
          <n-input 
            v-model:value="editForm.description" 
            type="textarea" 
            placeholder="请输入商品描述"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
        </n-form-item>
        
        <n-form-item label="价格" path="price">
          <n-input-number 
            v-model:value="editForm.price" 
            :min="0" 
            :precision="2"
            placeholder="请输入价格"
            class="w-full"
          />
        </n-form-item>
        
        <n-form-item label="商品成色" path="condition">
          <n-select 
            v-model:value="editForm.condition" 
            :options="conditionOptions"
            placeholder="请选择商品成色"
          />
        </n-form-item>
      </n-form>
      
      <template #footer>
        <n-space justify="end">
          <n-button @click="cancelEdit">取消</n-button>
          <n-button type="primary" @click="saveEdit">保存</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { NButton, NCard, NSpin, NTabPane, NTabs, NTag, useMessage, NModal, NForm, NFormItem, NInput, NInputNumber, NSelect, NSpace } from 'naive-ui'
import { http } from '@/lib/http'

type TabKey = 'selling' | 'sold' | 'removed'

const message = useMessage()
const activeTab = ref<TabKey>('selling')
const loading = ref(false)

const itemsByTab = reactive<Record<TabKey, any[]>>({
  selling: [],
  sold: [],
  removed: []
})

const fetchedTabs = reactive<Record<TabKey, boolean>>({
  selling: false,
  sold: false,
  removed: false
})

const statusMap: Record<TabKey, string> = {
  selling: 'available',
  sold: 'sold',
  removed: 'removed'
}

const categoryEmojiMap: Record<string, string> = {
  electronics: '📱',
  books: '📚',
  daily: '🛋️',
  sports: '⚽',
  fashion: '👕',
  beauty: '💄',
  other: '📦'
}

// Edit modal state
const editModalVisible = ref(false)
const editingItem = ref<any>(null)
const editForm = reactive({
  title: '',
  description: '',
  price: 0,
  condition: 'good'
})

const conditionOptions = [
  { label: '全新', value: 'new' },
  { label: '良好', value: 'good' },
  { label: '一般', value: 'fair' },
  { label: '较差', value: 'poor' }
]

const formatItems = (items: any[]) => {
  return items.map((item) => ({
    ...item,
    emoji: categoryEmojiMap[item.category] || '📦',
    views: item.view_count ?? 0,
    inquiries: item.inquiry_count ?? 0,
    price: Number(item.price) || 0
  }))
}

const loadItems = async (tabKey: TabKey, options: { force?: boolean } = {}) => {
  const force = options.force ?? false
  if (!force && fetchedTabs[tabKey]) {
    return
  }
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: 1,
      page_size: 50,
      status: statusMap[tabKey]
    }
    const response = await http.get('/items/my', { params })
    itemsByTab[tabKey] = formatItems(response.data.items)
    fetchedTabs[tabKey] = true
  } catch (error: any) {
    console.error('加载我的商品失败:', error)
    message.error(error.response?.data?.detail || '加载我的商品失败')
  } finally {
    loading.value = false
  }
}

const formatDate = (value?: string) => {
  if (!value) return '-'
  return new Date(value).toLocaleDateString()
}

const refreshTab = async (tabKey: TabKey) => {
  fetchedTabs[tabKey] = false
  await loadItems(tabKey, { force: true })
}

const editItem = (item: any) => {
  editingItem.value = item
  editForm.title = item.title
  editForm.description = item.description || ''
  editForm.price = item.price
  editForm.condition = item.condition || 'good'
  editModalVisible.value = true
}

const saveEdit = async () => {
  if (!editingItem.value) return
  
  try {
    await http.put(`/items/${editingItem.value.id}`, {
      title: editForm.title,
      description: editForm.description,
      price: editForm.price,
      condition: editForm.condition
    })
    
    message.success('商品信息已更新')
    editModalVisible.value = false
    editingItem.value = null
    
    // Refresh the current tab
    await refreshTab(activeTab.value)
  } catch (error: any) {
    console.error('编辑失败:', error)
    message.error('编辑失败，请重试')
  }
}

const cancelEdit = () => {
  editModalVisible.value = false
  editingItem.value = null
}

const removeItem = async (item: any) => {
  try {
    await http.put(`/items/${item.id}`, { status: 'deleted' })
    message.success('商品已下架')
    fetchedTabs.removed = false
    await refreshTab(activeTab.value)
  } catch (error: any) {
    console.error('下架失败:', error)
    message.error(error.response?.data?.detail || '下架失败')
  }
}

const sellingItems = computed(() => itemsByTab.selling)
const soldItems = computed(() => itemsByTab.sold)
const removedItems = computed(() => itemsByTab.sold)

// 本地占位图列表
const PLACEHOLDER_IMAGES = [
  '/demo-images/placeholder1.jpg',
  '/demo-images/placeholder2.jpg',
  '/demo-images/placeholder3.jpg',
  '/demo-images/placeholder4.jpg',
  '/demo-images/placeholder5.jpg',
  '/demo-images/placeholder6.jpg',
]

const getPlaceholderImage = (itemId: number) => {
  if (PLACEHOLDER_IMAGES.length === 0) return ''
  const index = Math.abs(itemId) % PLACEHOLDER_IMAGES.length
  return PLACEHOLDER_IMAGES[index]
}

// 将相对图片URL转换为完整URL
const getFullImageUrl = (relativeUrl: string) => {
  if (!relativeUrl) return ''
  if (/^https?:/i.test(relativeUrl) || relativeUrl.startsWith('data:')) {
    return relativeUrl
  }
  const serverUrl = window.location.origin
  return `${serverUrl}${relativeUrl}`
}

// 获取商品图片URL，支持随机占位图
const getItemImageUrl = (images: string[] | string | undefined | null, itemId?: number) => {
  if (Array.isArray(images) && images.length > 0) {
    return getFullImageUrl(images[0])
  }

  if (typeof images === 'string') {
    try {
      const parsed = JSON.parse(images)
      if (Array.isArray(parsed) && parsed.length > 0) {
        return getFullImageUrl(parsed[0])
      }
    } catch (err) {
      // ignore
    }
    if (images.startsWith('http') || images.startsWith('data:')) {
      return images
    }
    if (images.startsWith('/')) {
      return getFullImageUrl(images)
    }
  }

  return getPlaceholderImage(itemId || 0)
}

watch(activeTab, (tab) => {
  loadItems(tab)
})

onMounted(() => {
  loadItems('selling', { force: true })
})
</script>
