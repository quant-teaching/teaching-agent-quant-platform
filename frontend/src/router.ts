import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from './stores/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { title: '登录', bare: true } },
    { path: '/chat/:sessionId?', name: 'chat', component: () => import('./views/ChatView.vue'), meta: { title: '智能助手', full: true } },
    { path: '/learn/:id?', name: 'learn', component: () => import('./views/LearnView.vue'), meta: { title: '新手教程' } },
    { path: '/library', name: 'library', component: () => import('./views/LibraryView.vue'), meta: { title: '算法库' } },
    { path: '/library/:id', name: 'strategy', component: () => import('./views/StrategyView.vue'), meta: { title: '策略详情' } },
    { path: '/backtest', name: 'backtest', component: () => import('./views/BacktestView.vue'), meta: { title: '回测实验室' } },
    { path: '/portfolio', name: 'portfolio', component: () => import('./views/PortfolioView.vue'), meta: { title: '组合实验室' } },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue'), meta: { title: '回测记录' } },
    { path: '/report/:id', name: 'report', component: () => import('./views/ReportView.vue'), meta: { title: '回测报告' } },
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue'), meta: { title: '设置' } },
  ],
})

// 开启登录时，未登录访问任何页面都先去登录页，登录后回到原来的页面
router.beforeEach(async (to) => {
  const auth = useAuth()
  if (!auth.loaded) {
    try {
      await auth.fetchMe()
    } catch {
      return true // 后端暂时不可用：照常进入，页面自己会提示
    }
  }
  if (!auth.enabled) return to.name === 'login' ? '/' : true
  if (to.name === 'login') return auth.user ? (to.query.redirect as string) || '/' : true
  if (!auth.user) return { name: 'login', query: to.fullPath.startsWith('/chat') && !to.params.sessionId ? {} : { redirect: to.fullPath } }
  return true
})

router.afterEach((to) => {
  document.title = `${(to.meta.title as string) || ''} · 量化策略教学平台`
})
