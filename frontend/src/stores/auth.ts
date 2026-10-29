// 登录状态。平台未开启登录（本地单人使用）时 enabled 为 false，所有页面直接可用
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api } from '@/api/client'

export interface AuthUser {
  id: number
  username: string
  display_name: string
  role: 'admin' | 'user'
  disabled: boolean
  created_at: string
  last_login: string | null
}

interface Me {
  enabled: boolean
  user: AuthUser | null
  registration: boolean
}

export const useAuth = defineStore('auth', () => {
  const loaded = ref(false)
  const enabled = ref(false)
  const registration = ref(false)
  const user = ref<AuthUser | null>(null)

  const isAdmin = computed(() => !enabled.value || user.value?.role === 'admin')

  async function fetchMe() {
    const r = await api.get<Me>('/api/auth/me')
    enabled.value = r.enabled
    registration.value = r.registration
    user.value = r.user
    loaded.value = true
  }

  async function login(username: string, password: string, remember: boolean) {
    user.value = (await api.post<{ user: AuthUser }>('/api/auth/login', { username, password, remember })).user
  }

  async function register(username: string, password: string, inviteCode: string, displayName: string) {
    user.value = (
      await api.post<{ user: AuthUser }>('/api/auth/register', {
        username, password, invite_code: inviteCode, display_name: displayName,
      })
    ).user
  }

  async function logout() {
    await api.post('/api/auth/logout')
    // 整页刷新，清掉上一个用户的会话列表、报告缓存等
    window.location.href = '/login'
  }

  return { loaded, enabled, registration, user, isAdmin, fetchMe, login, register, logout }
})
