import { defineConfig, presetUno, presetAttributify, presetTypography } from 'unocss';

export default defineConfig({
  presets: [presetUno(), presetAttributify(), presetTypography()],
  theme: {
    colors: {
      // 咸鱼风格颜色主题
      primary: {
        50: '#fff7ed',
        100: '#ffedd5',
        200: '#fed7aa',
        300: '#fdba74',
        400: '#fb923c',
        500: '#f97316', // 主色调橙色
        600: '#ea580c',
        700: '#c2410c',
        800: '#9a3412',
        900: '#7c2d12',
      },
      secondary: {
        50: '#fef2f2',
        100: '#fee2e2',
        200: '#fecaca',
        300: '#fca5a5',
        400: '#f87171',
        500: '#ef4444', // 红色强调色
        600: '#dc2626',
        700: '#b91c1c',
        800: '#991b1b',
        900: '#7f1d1d',
      }
    }
  },
  shortcuts: {
    // 咸鱼风格卡片
    'xianyu-card': 'p-4 bg-white rounded-xl shadow-lg border border-orange-100',
    // 按钮样式
    'xianyu-btn': 'px-6 py-2 rounded-full font-medium transition-all duration-200',
    'xianyu-btn-primary': 'xianyu-btn bg-orange-500 text-white hover:bg-orange-600 active:bg-orange-700',
    'xianyu-btn-secondary': 'xianyu-btn bg-white text-orange-600 border border-orange-200 hover:bg-orange-50',
    // 导航样式
    'xianyu-nav-link': 'px-4 py-2 rounded-lg text-gray-700 hover:bg-orange-50 hover:text-orange-600 transition-colors',
    'xianyu-nav-active': 'bg-orange-100 text-orange-700 font-medium',
    // 输入框样式
    'xianyu-input': 'border border-gray-200 rounded-lg px-3 py-2 focus:border-orange-400 focus:ring-2 focus:ring-orange-100 transition-colors',
    // 页面容器
    'xianyu-container': 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8'
  }
});
