<template>
  <div class="marketplace-view">
    <!-- 搜索栏 -->
    <div class="search-bar bg-gradient-to-r from-orange-400 to-orange-500 p-4 rounded-lg mb-4">
      <div class="flex items-center gap-4 max-w-4xl mx-auto">
        <div class="flex-1">
          <n-auto-complete
            v-model:value="searchKeyword"
            :options="autocompleteOptions"
            :loading="searchLoading"
            placeholder="搜索宝贝、店铺..."
            size="large"
            clearable
            @select="handleSelect"
            @update:value="handleInput"
            @keyup.enter="handleSearch"
          >
            <template #prefix>
              <span>🔍</span>
            </template>
          </n-auto-complete>

          <!-- 热门搜索下拉面板 -->
          <transition name="fade">
            <div v-if="showHotSearches && !searchKeyword" class="hot-searches-panel">
              <div class="panel-header">
                <n-space justify="space-between">
                  <span class="title">🔥 热门搜索</span>
                  <n-button text size="small" @click="showHotSearches = false">
                    <template #icon>
                      <n-icon><CloseOutline /></n-icon>
                    </template>
                  </n-button>
                </n-space>
              </div>
              <div class="panel-content">
                <n-space>
                  <n-tag
                    v-for="(item, index) in hotSearches"
                    :key="index"
                    :type="getTrendType(item.trend)"
                    :bordered="false"
                    style="cursor: pointer"
                    @click="selectHotSearch(item.keyword)"
                  >
                    {{ item.keyword }}
                  </n-tag>
                </n-space>
              </div>
            </div>
          </transition>

          <!-- 搜索历史下拉面板 -->
          <transition name="fade">
            <div v-if="showSearchHistory && !searchKeyword" class="search-history-panel">
              <div class="panel-header">
                <n-space justify="space-between">
                  <span class="title">🕒 搜索历史</span>
                  <n-space>
                    <n-button text size="small" @click="clearSearchHistory">
                      清空
                    </n-button>
                    <n-button text size="small" @click="showSearchHistory = false">
                      <template #icon>
                        <n-icon><CloseOutline /></n-icon>
                      </template>
                    </n-button>
                  </n-space>
                </n-space>
              </div>
              <div class="panel-content">
                <n-list hoverable clickable>
                  <n-list-item
                    v-for="(item, index) in searchHistory"
                    :key="index"
                    @click="selectHistoryItem(item)"
                  >
                    <n-space>
                      <n-icon><TimeOutline /></n-icon>
                      <span>{{ item }}</span>
                    </n-space>
                  </n-list-item>
                </n-list>
              </div>
            </div>
          </transition>
        </div>
        <n-button type="warning" size="large" @click="handleSearch">
          搜索
        </n-button>
        <n-button 
          v-if="authStore.isAuthenticated"
          type="primary" 
          size="large" 
          @click="$router.push('/publish')"
        >
          ✏️ 我要卖
        </n-button>
      </div>
      
      <!-- 热门搜索 -->
      <div class="flex items-center gap-2 mt-2 max-w-4xl mx-auto text-white text-sm">
        <span>热门:</span>
        <span 
          v-for="keyword in ['iPhone', '自行车', '教材', '显示器', '二手书']" 
          :key="keyword"
          class="cursor-pointer hover:underline"
          @click="searchKeyword = keyword; handleSearch()"
        >
          {{ keyword }}
        </span>
      </div>
    </div>

    <!-- 分类导航 -->
    <div class="categories-bar bg-white p-4 rounded-lg mb-4 shadow-sm">
      <div class="flex flex-wrap gap-2">
        <n-button
          v-for="cat in categories"
          :key="cat.id ?? 'all'"
          :type="selectedCategory === cat.id ? 'warning' : 'default'"
          :tertiary="selectedCategory !== cat.id"
          round
          @click="selectCategory(cat.id)"
        >
          {{ cat.icon }} {{ cat.name }}
          <n-tag v-if="cat.count > 0" size="small" round class="ml-1">
            {{ cat.count }}
          </n-tag>
        </n-button>
      </div>
    </div>

    <!-- 跨校区价格比较面板 -->
    <div class="campus-price-comparison bg-gradient-to-r from-blue-50 to-purple-50 p-4 rounded-lg mb-4 border border-blue-200">
      <div class="max-w-6xl mx-auto">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-lg font-bold text-gray-800 flex items-center gap-2">
            🏫 跨校区价格情报
            <n-tag type="info" size="small">实时同步</n-tag>
          </h3>
          <n-button text @click="togglePriceComparison">
            {{ showPriceComparison ? '收起' : '展开' }}
          </n-button>
        </div>
        
        <transition name="slide">
          <div v-if="showPriceComparison" class="price-comparison-content">
            <n-spin :show="priceComparisonLoading">
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <n-card
                  v-for="item in campusPriceData"
                  :key="item.item_id"
                  hoverable
                  class="price-card"
                >
                  <template #header>
                    <div class="flex items-center justify-between">
                      <span class="font-medium">{{ item.title }}</span>
                      <n-tag :type="getCampusTagType(item.lowest_campus)" size="small">
                        {{ getCampusName(item.lowest_campus) }}最优
                      </n-tag>
                    </div>
                  </template>
                  
                  <div class="space-y-2">
                    <div class="text-sm text-gray-600">{{ item.category }}</div>
                    
                    <div class="price-grid">
                      <div 
                        v-for="(price, campus) in item.prices" 
                        :key="campus"
                        class="price-item"
                        :class="{ 'lowest-price': campus === item.lowest_campus }"
                      >
                        <span class="campus-name">{{ getCampusName(campus) }}</span>
                        <span class="price">¥{{ price }}</span>
                      </div>
                    </div>
                    
                    <div class="text-xs text-gray-500">
                      节省 ¥{{ item.price_diff }} • {{ formatTime(item.updated_at) }}更新
                    </div>
                  </div>
                </n-card>
              </div>
              
              <div v-if="campusPriceData.length === 0" class="text-center py-8 text-gray-500">
                暂无价格比较数据
              </div>
            </n-spin>
          </div>
        </transition>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar bg-white p-4 rounded-lg mb-4 shadow-sm">
      <div class="flex flex-wrap items-center gap-4">
        <!-- 成色筛选 -->
        <div class="flex items-center gap-2">
          <span class="text-gray-500">成色:</span>
          <n-button
            v-for="opt in conditionOptions"
            :key="opt.value ?? 'all'"
            :type="selectedCondition === opt.value ? 'primary' : 'default'"
            :tertiary="selectedCondition !== opt.value"
            size="small"
            @click="handleConditionChange(opt.value)"
          >
            {{ opt.label }}
          </n-button>
        </div>
        
        <!-- 校区筛选 -->
        <div class="flex items-center gap-2">
          <span class="text-gray-500">校区:</span>
          <n-select
            v-model:value="selectedCampus"
            :options="campusOptions"
            placeholder="选择校区"
            size="small"
            style="width: 120px"
            clearable
            @update:value="handleCampusChange"
          />
        </div>
        
        <!-- 价格区间 -->
        <div class="flex items-center gap-2">
          <span class="text-gray-500">价格:</span>
          <n-input-number
            v-model:value="priceRange.min"
            placeholder="最低价"
            size="small"
            :min="0"
            style="width: 100px"
            @blur="handleSearch"
          />
          <span>-</span>
          <n-input-number
            v-model:value="priceRange.max"
            placeholder="最高价"
            size="small"
            :min="0"
            style="width: 100px"
            @blur="handleSearch"
          />
        </div>
        
        <!-- 排序 -->
        <div class="flex items-center gap-2 ml-auto">
          <span class="text-gray-500">排序:</span>
          <n-select
            v-model:value="sortBy"
            :options="sortOptions"
            size="small"
            style="width: 140px"
            @update:value="handleSortChange"
          />
        </div>
      </div>
    </div>

    <!-- 商品列表 -->
    <n-spin :show="loading">
      <div v-if="items.length > 0" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        <n-card
          v-for="item in items"
          :key="item.id"
          hoverable
          class="item-card cursor-pointer"
          @click="goToItemDetail(item.id)"
        >
          <!-- 商品图片 -->
          <div class="relative">
            <img
              :src="getItemImageUrl(item.images, item.id)"
              :alt="item.title"
              class="w-full h-48 object-cover rounded-t-lg"
              loading="lazy"
            />
            <!-- 标签 -->
            <div class="absolute top-2 left-2 flex gap-1">
              <n-tag v-if="item.condition_type === '全新'" type="success" size="small">全新</n-tag>
              <n-tag v-if="item.is_shipped" type="info" size="small">包邮</n-tag>
            </div>
            <!-- 图片数量 -->
            <div v-if="Array.isArray(item.images) && item.images.length > 1" class="absolute bottom-2 right-2 bg-black/50 text-white text-xs px-2 py-1 rounded">
              📷 {{ item.images.length }}
            </div>
          </div>

          <!-- 商品信息 -->
          <div class="p-3">
            <!-- 价格 -->
            <div class="flex items-baseline gap-2 mb-2">
              <span class="text-red-500 text-xl font-bold">¥{{ item.price }}</span>
              <span v-if="item.original_price && item.original_price > item.price" class="text-gray-400 text-sm line-through">
                ¥{{ item.original_price }}
              </span>
            </div>

            <!-- 标题 -->
            <h3 class="text-sm font-medium mb-2 line-clamp-2">
              {{ item.emoji }} {{ item.title }}
            </h3>

            <!-- 标签 -->
            <div class="flex flex-wrap gap-1 mb-2">
              <n-tag v-for="tag in item.tags?.slice(0, 3)" :key="tag" size="small" round>
                {{ tag }}
              </n-tag>
            </div>

            <!-- 卖家和统计 -->
            <div class="flex items-center justify-between text-xs text-gray-500">
              <span>👤 {{ item.seller_name }}</span>
              <span>👁️ {{ item.view_count }}</span>
            </div>
            
            <!-- 校区和时间 -->
            <div class="flex items-center justify-between text-xs text-gray-400 mt-1">
              <span>🏫 {{ item.campus }}</span>
              <span>{{ formatTime(item.created_at) }}</span>
            </div>
          </div>

          <!-- 快捷操作 -->
          <div class="px-3 pb-3 flex gap-2">
            <n-button 
              size="small" 
              type="primary"
              @click.stop="handleAddToCart(item)"
            >
              🛒 加购
            </n-button>
            <n-button 
              size="small"
              :type="item.isFavorited ? 'error' : 'default'"
              @click.stop="handleToggleFavorite(item)"
            >
              {{ item.isFavorited ? '❤️' : '🤍' }}
            </n-button>
          </div>
        </n-card>
      </div>

      <!-- 空状态 -->
      <n-empty v-else-if="!loading" description="暂无商品，快来发布第一件吧~">
        <template #extra>
          <n-button type="primary" @click="showPublishModal = true">
            ✏️ 立即发布
          </n-button>
        </template>
      </n-empty>
    </n-spin>

    <!-- 分页 -->
    <div v-if="totalCount > 0" class="flex justify-center mt-8">
      <n-pagination
        v-model:page="currentPage"
        :page-count="totalPages"
        :page-size="pageSize"
        show-size-picker
        :page-sizes="[20, 40, 60, 100]"
        @update:page="handlePageChange"
        @update:page-size="handlePageSizeChange"
      />
    </div>

    <!-- 发布商品对话框 -->
    <n-modal 
      v-model:show="showPublishModal" 
      preset="card" 
      title="📤 发布商品" 
      style="width: 600px"
    >
      <n-form :model="newItem" label-placement="left" label-width="80">
        <n-form-item label="商品名称">
          <n-input v-model:value="newItem.name" placeholder="例如：二手iPhone 13 Pro" />
        </n-form-item>
        
        <n-form-item label="分类">
          <n-select v-model:value="newItem.category_id" :options="categoryOptions" placeholder="请选择分类" />
        </n-form-item>
        
        <n-form-item label="价格">
          <n-input-number v-model:value="newItem.price" :min="0" placeholder="输入价格" style="width: 100%">
            <template #prefix>¥</template>
          </n-input-number>
        </n-form-item>
        
        <n-form-item label="成色">
          <n-select
            v-model:value="newItem.condition"
            :options="[
              { label: '全新', value: 'new' },
              { label: '99新', value: 'like-new' },
              { label: '95新', value: 'excellent' },
              { label: '9成新', value: 'good' },
              { label: '二手', value: 'used' }
            ]"
          />
        </n-form-item>
        
        <n-form-item label="描述">
          <n-input
            v-model:value="newItem.description"
            type="textarea"
            placeholder="详细描述商品情况..."
            :rows="4"
          />
        </n-form-item>
        
        <n-form-item label="商品图片">
          <n-upload
            v-model:file-list="newItem.images"
            :max="5"
            :accept="'.jpg,.jpeg,.png,.gif'"
            :show-file-list="true"
            :show-preview-button="true"
            :show-remove-button="true"
            :show-download-button="false"
            :show-retry-button="false"
            list-type="image-card"
            :custom-request="customUpload"
            @before-upload="handleBeforeUpload"
            @remove="handleRemoveImage"
          >
            <n-upload-dragger>
              <div style="margin-bottom: 12px">
                <n-icon size="48" :depth="3">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z" />
                  </svg>
                </n-icon>
              </div>
              <n-text style="font-size: 14px; text-align: center;">
                点击或拖拽上传图片
              </n-text>
              <n-p depth="3" style="margin: 8px 0 0 0; font-size: 12px; text-align: center; line-height: 1.4;">
                支持 JPG、PNG、GIF 格式<br>最多 5 张图片
              </n-p>
            </n-upload-dragger>
          </n-upload>
        </n-form-item>
        
        <n-form-item label="交易地点">
          <n-input v-model:value="newItem.location" placeholder="例如：东区2号楼" />
        </n-form-item>
      </n-form>
      
      <template #footer>
        <div class="flex justify-end gap-2">
          <n-button @click="showPublishModal = false">取消</n-button>
          <n-button type="primary" @click="handlePublish">发布商品</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 商品详情对话框 -->
    <n-modal
      v-model:show="showDetailModal"
      preset="card"
      :title="currentItem?.title"
      style="width: 900px; max-height: 90vh"
    >
      <div v-if="currentItem" class="flex gap-6">
        <!-- 左侧图片 -->
        <div class="w-1/2">
          <n-carousel show-arrow>
            <img
              v-for="(img, idx) in (currentItem.images?.length ? currentItem.images : ['placeholder'])"
              :key="idx"
              :src="currentItem.images?.length ? getFullImageUrl(img) : getItemImageUrl([], currentItem.id)"
              class="w-full h-80 object-cover rounded"
            />
          </n-carousel>
        </div>

        <!-- 右侧信息 -->
        <div class="w-1/2 space-y-4">
          <!-- 价格 -->
          <div class="flex items-baseline gap-2">
            <span class="text-red-500 text-3xl font-bold">¥{{ currentItem.price }}</span>
            <span v-if="currentItem.original_price" class="text-gray-400 line-through">
              ¥{{ currentItem.original_price }}
            </span>
          </div>

          <!-- 标签 -->
          <div class="flex flex-wrap gap-2">
            <n-tag v-for="tag in currentItem.tags" :key="tag" type="info">
              {{ tag }}
            </n-tag>
          </div>

          <!-- 描述 -->
          <p class="text-gray-600">{{ currentItem.description }}</p>

          <!-- 卖家信息 -->
          <div class="bg-gray-50 p-4 rounded">
            <div class="flex items-center gap-3">
              <n-avatar :size="48">{{ currentItem.seller_name?.[0] }}</n-avatar>
              <div>
                <div class="font-bold">{{ currentItem.seller_name }}</div>
                <n-rate :value="4.5" readonly size="small" />
              </div>
            </div>
          </div>

          <!-- 统计 -->
          <div class="flex gap-4 text-sm text-gray-500">
            <span>👁️ {{ currentItem.view_count }} 浏览</span>
            <span>❤️ {{ currentItem.favorite_count }} 收藏</span>
            <span v-if="currentItem.location">📍 {{ currentItem.location }}</span>
          </div>

          <n-divider />

          <!-- 操作按钮 -->
          <div class="space-y-2">
            <n-button type="warning" size="large" block @click="handleContactSeller(currentItem!)">
              💬 联系卖家
            </n-button>
            <n-button type="primary" size="large" block @click="handleAddToCart(currentItem!)">
              🛒 加入购物车
            </n-button>
            <n-button 
              size="large" 
              block 
              :type="currentItem.isFavorited ? 'error' : 'default'"
              @click="handleToggleFavorite(currentItem!)"
            >
              {{ currentItem.isFavorited ? '❤️ 已收藏' : '🤍 收藏' }}
            </n-button>
          </div>

          <n-alert type="warning" class="mt-4">
            <template #header>⚠️ 交易提示</template>
            <p class="text-sm">请线下当面交易，验货后付款。禁止线上转账！</p>
          </n-alert>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  NCard,
  NSpace,
  NButton,
  NInput,
  NSelect,
  NTag,
  NModal,
  NForm,
  NFormItem,
  NInputNumber,
  NCarousel,
  NTabs,
  NTabPane,
  NAvatar,
  NPagination,
  NEmpty,
  NSpin,
  NRate,
  NDivider,
  NAlert,
  useMessage
} from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { http } from '@/lib/http'
import { CloseOutline, TimeOutline } from '@vicons/ionicons5'

const router = useRouter()
const route = useRoute()
const message = useMessage()
const authStore = useAuthStore()

// ========== 状态定义 ==========
const loading = ref(false)
const searchKeyword = ref('')
const selectedCategory = ref<number | null>(null)
const selectedCondition = ref<string | null>(null)
const selectedCampus = ref<string | null>(null)
const priceRange = ref({ min: null as number | null, max: null as number | null })
const sortBy = ref('default')
const currentPage = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)

// 商品列表 - 改为响应式数据
const items = ref<any[]>([])
const totalItems = ref(0)

// 搜索相关状态
const autocompleteOptions = ref<any[]>([])
const searchLoading = ref(false)
const showHotSearches = ref(false)
const showSearchHistory = ref(false)
const hotSearches = ref<any[]>([])
const searchHistory = ref<string[]>([])
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// 跨校区价格比较状态
const showPriceComparison = ref(true)
const priceComparisonLoading = ref(false)
const campusPriceData = ref<any[]>([])

// 分类数据
const categories = ref([
  { id: null, name: '全部分类', icon: '🏪', count: 0 },
  { id: 1, name: '数码产品', icon: '📱', count: 0 },
  { id: 2, name: '图书教材', icon: '📚', count: 0 },
  { id: 3, name: '生活用品', icon: '🛋️', count: 0 },
  { id: 4, name: '运动器材', icon: '⚽', count: 0 },
  { id: 5, name: '服装鞋包', icon: '👔', count: 0 },
  { id: 6, name: '美妆护肤', icon: '💄', count: 0 },
  { id: 7, name: '其他闲置', icon: '📦', count: 0 }
])

// 成色选项
const conditionOptions = [
  { label: '全部', value: null },
  { label: '全新', value: '全新' },
  { label: '99新', value: '99新' },
  { label: '95新', value: '95新' },
  { label: '9成新', value: '9成新' },
  { label: '二手', value: '二手' }
]

// 校区选项
const campusOptions = ref([
  { label: '全部校区', value: null },
  { label: '🏫 本部校区', value: 'main' },
  { label: '🏫 南校区', value: 'south' }
  // { label: '🏫 北校区', value: 'north' }
])

// 排序选项
const sortOptions = [
  { label: '综合排序', value: 'default' },
  { label: '最新发布', value: 'newest' },
  { label: '价格从低到高', value: 'price_asc' },
  { label: '价格从高到低', value: 'price_desc' },
  { label: '浏览最多', value: 'views' }
]

// 分类 slug 映射
const categorySlugMap: Record<number, string> = {
  1: 'electronics',
  2: 'books',
  3: 'daily',
  4: 'sports',
  5: 'fashion',
  6: 'beauty',
  7: 'other'
}

// 分类 emoji 映射
const categoryEmojiMap: Record<string, string> = {
  'electronics': '📱',
  'books': '📚',
  'daily': '🛋️',
  'sports': '⚽',
  'fashion': '👔',
  'beauty': '💄',
  'other': '📦'
}

// 加载跨校区价格比较数据
const loadCampusPriceComparison = async () => {
  priceComparisonLoading.value = true
  try {
    const response = await http.get('/items/campus-price-comparison')
    campusPriceData.value = response.data
  } catch (error) {
    console.error('加载价格比较数据失败:', error)
    // 使用模拟数据作为后备
    campusPriceData.value = [
      {
        item_id: 1,
        title: "iPad Pro 12.9寸",
        category: "数码产品",
        prices: { main: 5899, branch: 5799, hub: 5849 },
        lowest_price: 5799,
        lowest_campus: "branch",
        price_diff: 100,
        updated_at: new Date().toISOString()
      },
      {
        item_id: 2,
        title: "MacBook Air M2",
        category: "数码产品",
        prices: { main: 8999, branch: 8899, hub: 8949 },
        lowest_price: 8899,
        lowest_campus: "branch",
        price_diff: 100,
        updated_at: new Date().toISOString()
      }
    ]
  } finally {
    priceComparisonLoading.value = false
  }
}

// 切换价格比较面板显示
const togglePriceComparison = () => {
  showPriceComparison.value = !showPriceComparison.value
}

// 获取校区显示名称
const getCampusName = (campus: string | number) => {
  const campusMap: Record<string, string> = {
    main: '本部校区',
    branch: '分校区',
    hub: '价格情报中心',
    south: '南校区'
    // north: '北校区'
  }
  const key = String(campus)
  return campusMap[key] || String(campus)
}

// 获取校区标签类型
type TagType = 'error' | 'default' | 'success' | 'warning' | 'info' | 'primary'
const getCampusTagType = (campus: string | number): TagType => {
  const typeMap: Record<string, TagType> = {
    main: 'primary',
    branch: 'success',
    hub: 'warning'
  }
  const key = String(campus)
  return typeMap[key] || 'default'
}

// 加载商品列表
const loadItems = async () => {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: currentPage.value,
      page_size: pageSize.value,
      status: 'available'
    }
    
    // 分类筛选
    if (selectedCategory.value) {
      params.category = categorySlugMap[selectedCategory.value] || ''
    }
    
    // 成色筛选
    if (selectedCondition.value) {
      params.condition = selectedCondition.value
    }
    
    // 校区筛选
    if (selectedCampus.value) {
      params.campus = selectedCampus.value
    }
    
    // 关键词搜索
    if (searchKeyword.value.trim()) {
      params.keyword = searchKeyword.value.trim()
    }
    
    // 价格区间
    if (priceRange.value.min !== null) {
      params.min_price = priceRange.value.min
    }
    if (priceRange.value.max !== null) {
      params.max_price = priceRange.value.max
    }
    
    // 根据是否有搜索关键词选择API
    let apiEndpoint = '/items'
    const searchQuery = searchKeyword.value.trim()
    if (searchQuery) {
      apiEndpoint = '/search/search'
      params.q = searchQuery  // 搜索API使用 q 参数
      // 搜索API不接受 keyword 参数，移除它
      delete params.keyword
    }
    
    const response = await http.get(apiEndpoint, { params })
    
    // 处理返回数据
    items.value = response.data.items.map((item: any) => {
      // Snowflake/BIGINT ids must be treated as string in JS.
      const normalizedId = String(item.id)
      return {
        ...item,
        id: normalizedId,
        original_price: item.original_price || Math.round(item.price * 1.3),
        emoji: categoryEmojiMap[item.category] || '📦',
        // 兼容两种接口返回：
        // - /items: images: string[]
        // - /search/search: image: string
        images:
          item.images?.length > 0
            ? item.images
            : (item.image ? [item.image] : [`https://picsum.photos/400/400?random=${normalizedId}`]),
        tags: parseTags(item),
        isFavorited: false
      }
    })
    
    totalCount.value = response.data.total
    
    // 同时加载价格比较数据
    await loadCampusPriceComparison()
    
    // 如果用户已登录，检查收藏状态
    if (authStore.isAuthenticated) {
      await checkFavoriteStatus()
    }
    
  } catch (error: any) {
    console.error('加载商品失败:', error)
    message.error(error.response?.data?.detail || '加载商品失败')
  } finally {
    loading.value = false
  }
}

// 解析标签
const parseTags = (item: any): string[] => {
  const tags: string[] = []
  if (item.condition_type) tags.push(item.condition_type)
  if (item.is_negotiable) tags.push('可议价')
  if (item.is_shipped) tags.push('包邮')
  if (item.tags) {
    try {
      const parsed = typeof item.tags === 'string' ? JSON.parse(item.tags) : item.tags
      if (Array.isArray(parsed)) tags.push(...parsed)
    } catch { }
  }
  return tags.slice(0, 4) // 最多显示4个标签
}

// 检查收藏状态
const checkFavoriteStatus = async () => {
  try {
    const response = await http.get('/favorites')
    const favoriteIds = new Set(response.data.map((f: any) => f.item_id))
    items.value.forEach(item => {
      item.isFavorited = favoriteIds.has(item.id)
    })
  } catch (error) {
    console.error('检查收藏状态失败:', error)
  }
}

// 加载分类统计
const loadCategoryStats = async () => {
  try {
    // 获取各分类商品数量
    for (const cat of categories.value) {
      if (cat.id === null) {
        // 全部分类
        const res = await http.get('/items', { params: { page_size: 1, status: 'available' } })
        cat.count = res.data.total
      } else {
        const slug = categorySlugMap[cat.id]
        if (slug) {
          const res = await http.get('/items', { params: { page_size: 1, category: slug, status: 'available' } })
          cat.count = res.data.total
        }
      }
    }
  } catch (error) {
    console.error('加载分类统计失败:', error)
  }
}

// ========== 用户操作 ==========

// 搜索相关方法
const handleInput = (value: string) => {
  // 过滤掉包含格式化字符的输入（防止autocomplete标签污染）
  const cleanValue = value
    .replace(/^[🔍📁📦🎮📱💻📚🎨🏀👕🎸🚲🎵📦]+\s*/g, '') // 移除开头的图标
    .replace(/\s*\(\d+\)\s*$/g, '') // 移除末尾的计数
    .replace(/\s+/g, ' ') // 规范化空格
    .trim()

  // 如果组件把 label(含图标/计数) 写回到输入框，这里强制回写为纯文本，避免出现“🔍 被重复复制”
  if (cleanValue !== value) {
    searchKeyword.value = cleanValue
  }

  if (!cleanValue) {
    autocompleteOptions.value = []
    showHotSearches.value = true
    showSearchHistory.value = false
    return
  }

  showHotSearches.value = false
  showSearchHistory.value = false

  // 防抖处理
  if (debounceTimer) {
    clearTimeout(debounceTimer)
  }

  debounceTimer = setTimeout(() => {
    fetchAutocomplete(cleanValue)
  }, 300)
}

const fetchAutocomplete = async (query: string) => {
  if (!query || query.length < 1) {
    return
  }

  searchLoading.value = true

  try {
    // 确保查询参数是安全的
    const safeQuery = query.replace(/[^\w\s\u4e00-\u9fff\-_]/g, '').trim()
    if (!safeQuery) {
      autocompleteOptions.value = []
      return
    }

    // 调用真实的自动补全API
    const response = await http.get('/search/autocomplete', {
      params: { query: safeQuery, limit: 10 }
    })

    // 转换为autocomplete选项格式
    autocompleteOptions.value = response.data.suggestions.map((item: any) => ({
      label: formatLabel(item),
      value: item.text,
      type: item.type,
      count: item.count
    }))
  } catch (error) {
    console.error('自动补全失败:', error)
    autocompleteOptions.value = []
  } finally {
    searchLoading.value = false
  }
}

const formatLabel = (item: any) => {
  const icon = item.type === 'category' ? '📁' : '🔍'
  return `${icon} ${item.text} ${item.count ? `(${item.count})` : ''}`
}

const handleSelect = (value: string, option: any) => {
  // 明确使用选项对象的value属性，避免使用格式化的label
  const selectedValue = option?.value || value
  const cleanSelected = String(selectedValue)
    .replace(/^[🔍📁📦🎮📱💻📚🎨🏀👕🎸🚲🎵📦]+\s*/g, '')
    .replace(/\s*\(\d+\)\s*$/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  searchKeyword.value = cleanSelected
  handleSearch()
}

const selectHotSearch = (keyword: string) => {
  const clean = String(keyword).trim()
  searchKeyword.value = clean
  handleSearch()
}

const selectHistoryItem = (keyword: string) => {
  const clean = String(keyword).trim()
  searchKeyword.value = clean
  handleSearch()
}

const clearSearchHistory = () => {
  searchHistory.value = []
  showSearchHistory.value = false
  message.success('搜索历史已清空')
}

const getTrendType = (trend: string) => {
  switch (trend) {
    case 'up':
      return 'error'
    case 'down':
      return 'info'
    default:
      return 'default'
  }
}

// 加载热门搜索
const loadHotSearches = async () => {
  try {
    // 调用真实API加载热门搜索
    const response = await http.get('/search/popular', { params: { limit: 10 } })
    if (response.data.keywords && response.data.keywords.length > 0) {
      hotSearches.value = response.data.keywords
    }
  } catch (error) {
    console.error('加载热门搜索失败:', error)
    // 使用默认数据
    hotSearches.value = [
      { keyword: 'iPhone', count: 150, trend: 'up' },
      { keyword: '自行车', count: 120, trend: 'down' },
      { keyword: '教材', count: 100, trend: 'up' }
    ]
  }
}

// 加载搜索历史
const loadSearchHistory = async () => {
  try {
    // 从localStorage加载
    const history = localStorage.getItem('searchHistory')
    if (history) {
      searchHistory.value = JSON.parse(history)
    }

    // 如果用户已登录，尝试从服务器加载
    if (authStore.isAuthenticated) {
      try {
        console.log('🔍 加载服务器搜索历史...')
        const response = await http.get('/search/history', { params: { page_size: 10 } })
        console.log('✅ 服务器搜索历史响应:', response.data)
        if (response.data.history && response.data.history.length > 0) {
          // 合并服务器历史和本地历史
          const serverKeywords = response.data.history.map((h: any) => h.keyword)
          const merged = [...new Set([...serverKeywords, ...searchHistory.value])]
          searchHistory.value = merged.slice(0, 10)
          console.log('📚 合并搜索历史:', searchHistory.value)
        } else {
          console.log('📭 服务器无搜索历史')
        }
      } catch (error: any) {
        console.warn('⚠️ 加载服务器搜索历史失败:', error.response?.status, error.response?.data?.detail || error.message)
        // 如果是认证错误，清除登录状态
        if (error.response?.status === 401) {
          console.log('🔐 认证失效，清除登录状态')
          authStore.logout()
        }
        // 静默失败，继续使用本地历史
      }
    } else {
      console.log('👤 用户未登录，跳过服务器搜索历史')
    }
  } catch (error) {
    console.error('加载搜索历史失败:', error)
  }
}

// 添加到搜索历史
const addToHistory = (keyword: string) => {
  // 检查是否已存在
  const existsIndex = searchHistory.value.findIndex(item => item === keyword)
  if (existsIndex !== -1) {
    // 移到最前面
    searchHistory.value.splice(existsIndex, 1)
  }

  // 添加新记录
  searchHistory.value.unshift(keyword)

  // 限制历史记录数量
  if (searchHistory.value.length > 10) {
    searchHistory.value = searchHistory.value.slice(0, 10)
  }

  // 保存到localStorage
  localStorage.setItem('searchHistory', JSON.stringify(searchHistory.value))

  // 注意：搜索历史会在执行搜索时自动保存到服务器
}

// 搜索
const handleSearch = () => {
  // 清理搜索关键词
  const cleanKeyword = searchKeyword.value
    .replace(/^[🔍📁📦🎮📱💻📚🎨🏀👕🎸🚲🎵📦]+\s*/g, '') // 移除开头的图标
    .replace(/\s*\(\d+\)\s*$/g, '') // 移除末尾的计数
    .replace(/\s+/g, ' ') // 规范化空格
    .trim()

  if (!cleanKeyword) {
    message.warning('请输入有效的搜索关键词')
    return
  }

  // 更新清理后的关键词
  searchKeyword.value = cleanKeyword

  // 添加到搜索历史
  addToHistory(cleanKeyword)

  // 执行搜索
  currentPage.value = 1
  loadItems()

  // 清空建议
  autocompleteOptions.value = []
  showHotSearches.value = false
  showSearchHistory.value = false
}

// 选择分类
const selectCategory = (categoryId: number | null) => {
  selectedCategory.value = categoryId
  currentPage.value = 1
  loadItems()
}

// 选择成色
const handleConditionChange = (value: string | null) => {
  selectedCondition.value = value
  currentPage.value = 1
  loadItems()
}

// 选择校区
const handleCampusChange = (value: string | null) => {
  selectedCampus.value = value
  currentPage.value = 1
  loadItems()
}

// 排序变更
const handleSortChange = (value: string) => {
  sortBy.value = value
  currentPage.value = 1
  loadItems()
}

// 页码变更
const handlePageChange = (page: number) => {
  currentPage.value = page
  loadItems()
}

// 每页数量变更
const handlePageSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadItems()
}

// 计算总页数
const totalPages = computed(() => Math.ceil(totalCount.value / pageSize.value))

// ========== 商品详情弹窗 ==========
const showDetailModal = ref(false)
const currentItem = ref<any | null>(null)
const currentImageIndex = ref(0)

const viewItemDetail = (item: any) => {
  currentItem.value = item
  currentImageIndex.value = 0
  showDetailModal.value = true
}

// 跳转到商品详情页
const goToItemDetail = (itemId: string | number) => {
  router.push(`/item/${String(itemId)}`)
}

// ========== 购物车 & 收藏 ==========

// 加入购物车
const handleAddToCart = async (item: any) => {
  if (!authStore.isAuthenticated) {
    message.warning('请先登录')
    router.push('/login')
    return
  }
  
  try {
    await http.post('/cart', {
      item_id: item.id,
      quantity: 1
    })
    message.success(`"${item.title}" 已加入购物车`)
  } catch (error: any) {
    const detail = error.response?.data?.detail
    if (detail === '不能购买自己发布的商品') {
      message.warning('不能购买自己的商品哦~')
    } else if (detail?.includes('已下架') || detail?.includes('已售出')) {
      message.warning('该商品已下架或已售出')
    } else {
      message.error(detail || '加入购物车失败')
    }
  }
}

// 收藏/取消收藏
const handleToggleFavorite = async (item: any) => {
  if (!authStore.isAuthenticated) {
    message.warning('请先登录')
    router.push('/login')
    return
  }
  
  try {
    if (item.isFavorited) {
      await http.delete(`/favorites/${item.id}`)
      item.isFavorited = false
      message.success('已取消收藏')
    } else {
      await http.post(`/favorites/${item.id}`)
      item.isFavorited = true
      message.success('收藏成功')
    }
  } catch (error: any) {
    message.error(error.response?.data?.detail || '操作失败')
  }
}

// 联系卖家
const handleContactSeller = (item: any) => {
  if (!authStore.isAuthenticated) {
    message.warning('请先登录')
    router.push('/login')
    return
  }
  // Avoid passing Snowflake BIGINT ids via JS numbers; use seller username instead.
  const username = item.seller_username || item.seller_name
  router.push(`/messages?username=${encodeURIComponent(username)}`)
}

// ========== 发布商品弹窗 ==========
const showPublishModal = ref(false)
const newItem = ref({
  name: '',
  category_id: null as number | null,
  price: 0,
  condition: 'used',
  description: '',
  location: '',
  images: [] as any[]
})

const categoryOptions = computed(() => 
  categories.value
    .filter(c => c.id !== null)
    .map(c => ({ label: `${c.icon} ${c.name}`, value: c.id! })) as { label: string; value: number }[]
)

const handlePublish = async () => {
  if (!newItem.value.name || !newItem.value.category_id || !newItem.value.price) {
    message.warning('请填写完整信息')
    return
  }
  
  // 检查是否有图片正在上传
  const uploadingImages = newItem.value.images.filter((file: any) => file.status === 'uploading')
  if (uploadingImages.length > 0) {
    message.warning('请等待图片上传完成')
    return
  }
  
  // 检查是否有成功上传的图片（Naive UI状态为'finished'）
  console.log('当前图片列表:', newItem.value.images)  // 调试日志
  const uploadedImages = newItem.value.images.filter((file: any) => 
    (file.status === 'finished' || file.status === 'done') && file.url
  )
  console.log('已上传图片:', uploadedImages)  // 调试日志
  if (uploadedImages.length === 0) {
    message.warning('请至少上传一张商品图片')
    return
  }
  
  try {
    const categorySlug = categorySlugMap[newItem.value.category_id] || 'other'
    
    // 处理图片URL - 将完整URL转换为相对路径
    const imageUrls = newItem.value.images
      .filter((file: any) => file.url) // 只包含成功上传的文件
      .map((file: any) => {
        // 从完整URL中提取相对路径
        const url = new URL(file.url)
        return url.pathname
      })
    
    await http.post('/items', {
      title: newItem.value.name,
      description: newItem.value.description || newItem.value.name,
      price: newItem.value.price,
      category: categorySlug,
      condition: newItem.value.condition,
      status: 'available',
      images: imageUrls
    })
    
    message.success('发布成功!')
    showPublishModal.value = false
    
    // 重置表单
    newItem.value = {
      name: '',
      category_id: null,
      price: 0,
      condition: 'used',
      description: '',
      location: '',
      images: []
    }
    
    // 刷新列表
    await loadItems()
  } catch (error: any) {
    message.error(error.response?.data?.detail || '发布失败')
  }
}

// 格式化时间
const formatTime = (dateStr: string) => {
  if (!dateStr) return '刚刚'
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  
  const minutes = Math.floor(diff / 60000)
  if (minutes < 60) return `${minutes}分钟前`
  
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}小时前`
  
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}天前`
  
  return date.toLocaleDateString()
}

// 页面加载时获取数据
onMounted(() => {
  // 处理URL参数
  if (route.query.keyword) {
    searchKeyword.value = route.query.keyword as string
  }
  loadItems()
  loadCategoryStats()
  loadHotSearches()
  loadSearchHistory()
})

// 图片上传处理
const handleBeforeUpload = async (data: { file: File; fileList: any[] }) => {
  // 检查文件类型
  const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
  if (!allowedTypes.includes(data.file.type)) {
    message.error('只支持 JPG、PNG、GIF 格式的图片')
    return false
  }
  
  // 检查文件大小 (5MB)
  if (data.file.size > 5 * 1024 * 1024) {
    message.error('图片大小不能超过 5MB')
    return false
  }
  
  return true
}

const handleRemoveImage = (file: any) => {
  // 从newItem.images中移除
  const index = newItem.value.images.findIndex((img: any) => img.id === file.id)
  if (index > -1) {
    newItem.value.images.splice(index, 1)
  }
}

// 自定义上传函数
const customUpload = async ({ file, onFinish, onError }: any) => {
  try {
    const formData = new FormData()
    formData.append('file', file.file)
    
    const response = await http.post('/items/upload-image', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    
    // 设置文件的URL为完整的服务器URL
    const serverUrl = window.location.origin
    file.url = `${serverUrl}${response.data.url}`
    file.status = 'finished'  // Naive UI 使用 'finished' 表示上传完成
    file.name = file.file.name
    
    console.log('图片上传成功:', file)  // 调试日志
    onFinish()
    message.success('图片上传成功')
  } catch (error: any) {
    console.error('图片上传失败', error)
    file.status = 'error'
    onError()
    message.error(error.response?.data?.detail || '图片上传失败')
  }
}

// 本地占位图列表（存放于public/demo-images目录）
const PLACEHOLDER_IMAGES = [
  '/demo-images/placeholder1.jpg',
  '/demo-images/placeholder2.jpg',
  '/demo-images/placeholder3.jpg',
  '/demo-images/placeholder4.jpg',
  '/demo-images/placeholder5.jpg',
  '/demo-images/placeholder6.jpg',
]

// 根据商品ID获取占位图 URL，保证每个商品稳定但又有区分度
const getPlaceholderImage = (itemId: number) => {
  if (PLACEHOLDER_IMAGES.length === 0) {
    return ''
  }
  const index = Math.abs(itemId) % PLACEHOLDER_IMAGES.length
  return PLACEHOLDER_IMAGES[index]
}

const getFullImageUrl = (relativeUrl: string) => {
  if (!relativeUrl) return ''
  if (/^https?:/i.test(relativeUrl) || relativeUrl.startsWith('data:')) {
    return relativeUrl
  }
  const serverUrl = window.location.origin
  return `${serverUrl}${relativeUrl}`
}

// 获取商品图片URL，支持多图/字符串字段/无图情况
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
      // ignore json parse error
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

// 监听搜索关键词变化
watch(searchKeyword, (newVal) => {
  if (!newVal) {
    showHotSearches.value = true
    showSearchHistory.value = false
  }
})
</script>

<style scoped>
.marketplace-view {
  padding: 16px;
  max-width: 1400px;
  margin: 0 auto;
}

.item-card {
  transition: transform 0.2s, box-shadow 0.2s;
}

.item-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-clamp: 2;
}

/* 价格比较面板样式 */
.campus-price-comparison {
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.price-comparison-content {
  max-height: 400px;
  overflow-y: auto;
}

.price-card {
  transition: transform 0.2s, box-shadow 0.2s;
}

.price-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.price-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 8px;
  margin-top: 8px;
}

.price-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px;
  border-radius: 6px;
  background: #f8f9fa;
  border: 1px solid #e9ecef;
}

.price-item.lowest-price {
  background: #f0f9ff;
  border-color: #0ea5e9;
  position: relative;
}

.price-item.lowest-price::after {
  content: '💰';
  position: absolute;
  top: -8px;
  right: -8px;
  font-size: 16px;
}

.campus-name {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}

.price {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

/* 过渡动画 */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

/* 搜索面板样式 */
.hot-searches-panel,
.search-history-panel {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  max-height: 300px;
  overflow-y: auto;
}

.panel-header {
  padding: 12px 16px;
  border-bottom: 1px solid #f3f4f6;
  background: #f9fafb;
  border-radius: 8px 8px 0 0;
}

.panel-content {
  padding: 8px;
}
</style>
