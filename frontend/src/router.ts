import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/chat' },
    { path: '/chat/:sessionId?', name: 'chat', component: () => import('./views/ChatView.vue'), meta: { title: '智能助手', full: true } },
    { path: '/library', name: 'library', component: () => import('./views/LibraryView.vue'), meta: { title: '算法库' } },
    { path: '/library/:id', name: 'strategy', component: () => import('./views/StrategyView.vue'), meta: { title: '策略详情' } },
    { path: '/backtest', name: 'backtest', component: () => import('./views/BacktestView.vue'), meta: { title: '回测实验室' } },
    { path: '/portfolio', name: 'portfolio', component: () => import('./views/PortfolioView.vue'), meta: { title: '组合实验室' } },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue'), meta: { title: '回测记录' } },
    { path: '/report/:id', name: 'report', component: () => import('./views/ReportView.vue'), meta: { title: '回测报告' } },
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue'), meta: { title: '模型设置' } },
  ],
})

router.afterEach((to) => {
  document.title = `${(to.meta.title as string) || ''} · 量化策略教学平台`
})
