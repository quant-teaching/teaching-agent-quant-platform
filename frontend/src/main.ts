import { createPinia } from 'pinia'
import { createApp } from 'vue'
import App from './App.vue'
import { setUnauthorizedHandler } from './api/client'
import { router } from './router'
import './styles/base.css'
import './styles/motion.css'
import './styles/content.css'
import './charts/register'

const app = createApp(App).use(createPinia()).use(router)
// 等首个路由（含登录检查）确定后再挂载，避免未登录时先闪一下主界面
router.isReady().then(() => app.mount('#app'))

setUnauthorizedHandler(() => {
  const here = router.currentRoute.value
  if (here.name !== 'login') window.location.href = `/login?redirect=${encodeURIComponent(here.fullPath)}`
})
