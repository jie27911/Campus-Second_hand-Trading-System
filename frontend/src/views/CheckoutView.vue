<template>
  <div class="checkout-view min-h-screen bg-gray-50">
    <div class="max-w-4xl mx-auto py-6 px-4">
      <div class="bg-white rounded-lg shadow p-6">
        <h1 class="text-2xl font-bold mb-6">📦 订单确认</h1>
        
        <!-- 加载中 -->
        <n-spin v-if="loading" class="flex justify-center py-12">
          <template #description>加载中...</template>
        </n-spin>
        
        <!-- 商品列表 -->
        <div v-else-if="checkoutItems.length > 0">
          <n-card v-for="item in checkoutItems" :key="item.item_id" class="mb-4">
            <div class="flex gap-4">
              <div class="w-24 h-24 bg-gradient-to-br from-blue-100 to-purple-100 rounded flex items-center justify-center">
                <n-image 
                  v-if="item.item_image" 
                  :src="item.item_image" 
                  class="w-full h-full object-cover rounded"
                  fallback-src=""
                />
                <span v-else class="text-3xl">📦</span>
              </div>
              <div class="flex-1">
                <h3 class="font-bold text-lg mb-2">{{ item.item_title }}</h3>
                <p class="text-gray-500 text-sm mb-2">卖家: {{ item.seller_name }}</p>
                <div class="flex items-center justify-between">
                  <span class="text-red-500 font-bold text-xl">¥{{ item.item_price }}</span>
                  <span class="text-gray-400">x {{ item.quantity }}</span>
                </div>
              </div>
            </div>
          </n-card>
          
          <!-- 订单汇总 -->
          <n-divider />
          
          <!-- 收货信息表单 -->
          <n-card title="📍 收货信息" class="mb-6">
            <n-form ref="formRef" :model="deliveryForm" :rules="deliveryRules">
              <n-form-item label="收货人" path="receiver_name">
                <n-input 
                  v-model:value="deliveryForm.receiver_name" 
                  placeholder="请输入收货人姓名"
                />
              </n-form-item>
              <n-form-item label="联系电话" path="receiver_phone">
                <n-input 
                  v-model:value="deliveryForm.receiver_phone" 
                  placeholder="请输入联系电话"
                />
              </n-form-item>
              <n-form-item label="收货地址" path="receiver_address">
                <n-input 
                  v-model:value="deliveryForm.receiver_address" 
                  type="textarea"
                  placeholder="请输入详细收货地址"
                  :autosize="{ minRows: 2, maxRows: 4 }"
                />
              </n-form-item>
            </n-form>
          </n-card>
          
          <div class="flex justify-between items-center mb-6">
            <span class="text-gray-600">商品总计 ({{ totalQuantity }} 件)</span>
            <span class="text-red-500 font-bold text-2xl">¥{{ totalAmount.toFixed(2) }}</span>
          </div>
          
          <!-- 卖家联系方式 -->
          <n-card title="卖家联系方式" class="mb-6">
            <div v-for="seller in uniqueSellers" :key="seller.id" class="flex items-center justify-between py-2 border-b last:border-b-0">
              <div class="flex items-center gap-3">
                <n-avatar :size="40">{{ seller.name.charAt(0) }}</n-avatar>
                <span class="font-medium">{{ seller.name }}</span>
              </div>
              <n-button type="primary" @click="contactSeller(seller)">
                💬 发送消息
              </n-button>
            </div>
          </n-card>
          
          <!-- 操作按钮 -->
          <div class="flex gap-4">
            <n-button size="large" @click="router.back()">返回购物车</n-button>
            <n-button type="primary" size="large" class="flex-1" @click="createOrders">
              确认下单
            </n-button>
          </div>
        </div>
        
        <!-- 空状态 -->
        <n-empty v-else description="没有待结算的商品">
          <template #extra>
            <n-button type="primary" @click="router.push('/marketplace')">
              去逛逛
            </n-button>
          </template>
        </n-empty>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMessage, type FormRules, type FormInst } from 'naive-ui'
import { http } from '@/lib/http'

const router = useRouter()
const route = useRoute()
const message = useMessage()

const loading = ref(true)
const checkoutItems = ref<any[]>([])
const formRef = ref<FormInst | null>(null)

// 收货信息表单
const deliveryForm = reactive({
  receiver_name: '',
  receiver_phone: '',
  receiver_address: ''
})

// 表单验证规则
const deliveryRules: FormRules = {
  receiver_name: [
    { required: true, message: '请输入收货人姓名', trigger: ['input', 'blur'] }
  ],
  receiver_phone: [
    { required: true, message: '请输入联系电话', trigger: ['input', 'blur'] },
    // 允许手机号/固话/微信号/QQ号等较宽松的联系方式，避免“已填写但校验不通过”
    { pattern: /^[0-9A-Za-z+\-()\s]{5,30}$/, message: '请输入正确的联系方式', trigger: ['input', 'blur'] }
  ],
  receiver_address: [
    { required: true, message: '请输入收货地址', trigger: ['input', 'blur'] },
    { min: 5, message: '地址至少5个字符', trigger: ['input', 'blur'] }
  ]
}

// 计算总数量和总金额
const totalQuantity = computed(() => 
  checkoutItems.value.reduce((sum, item) => sum + item.quantity, 0)
)

const totalAmount = computed(() => 
  checkoutItems.value.reduce((sum, item) => sum + item.item_price * item.quantity, 0)
)

// 获取唯一卖家列表
const uniqueSellers = computed(() => {
  const sellerMap = new Map()
  checkoutItems.value.forEach(item => {
    if (!sellerMap.has(item.seller_id)) {
      sellerMap.set(item.seller_id, {
        id: item.seller_id,
        name: item.seller_name
      })
    }
  })
  return Array.from(sellerMap.values())
})

// 加载结算商品
const loadCheckoutItems = async () => {
  try {
    // Snowflake-style BIGINT ids exceed JS safe integer range; keep them as strings.
    const itemIds = route.query.items?.toString().split(',').map(s => s.trim()).filter(Boolean) || []
    if (itemIds.length === 0) {
      loading.value = false
      return
    }
    
    // 从购物车获取商品详情
    const response = await http.get('/cart')
    const allItems = response.data.items || []
    // `items` query param comes from cart selection and contains cart_item.id
    checkoutItems.value = allItems.filter((item: any) => itemIds.includes(String(item.id)))
  } catch (error: any) {
    message.error('加载失败: ' + (error.response?.data?.detail || error.message))
  } finally {
    loading.value = false
  }
}

// 联系卖家
const contactSeller = (seller: any) => {
  router.push({
    path: '/messages',
    query: { to: seller.id, name: seller.name }
  })
}

// 创建订单
const createOrders = async () => {
  try {
    // 先 trim，避免用户输入空格导致校验失败
    deliveryForm.receiver_name = deliveryForm.receiver_name.trim()
    deliveryForm.receiver_phone = deliveryForm.receiver_phone.trim()
    deliveryForm.receiver_address = deliveryForm.receiver_address.trim()

    // 验证表单
    await formRef.value?.validate()

    const buyerContact = deliveryForm.receiver_phone
    
    // 为每个商品创建订单
    for (const item of checkoutItems.value) {
      await http.post('/orders', {
        item_id: item.item_id,
        buyer_contact: buyerContact
      })
    }
    
    message.success('订单创建成功！')
    router.push('/orders')
  } catch (error: any) {
    // Naive UI 表单校验失败时，error 往往不是 AxiosError，可能没有 response/message
    if (Array.isArray(error) || error?.errors) {
      message.warning('请先完善收货信息后再下单')
      return
    }
    message.error('创建订单失败: ' + (error.response?.data?.detail || error.message || '未知错误'))
  }
}

onMounted(() => {
  loadCheckoutItems()
})
</script>

<style scoped>
.checkout-view {
  padding-bottom: 80px;
}
</style>
