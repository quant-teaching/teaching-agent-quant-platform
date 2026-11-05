// 班级与账号管理接口（老师、管理员）
import { api } from './client'

export type Role = 'admin' | 'teacher' | 'student'

export interface ClassInfo {
  id: number
  name: string
  description: string
  teacher_id: number | null
  teacher_name: string | null
  invite_code: string
  registration_open: boolean
  created_at: string
  student_count: number
  disabled_count: number
  active_7d: number
  backtest_count: number
}

export interface ManagedUser {
  id: number
  username: string
  display_name: string
  role: Role
  role_label: string
  class_id: number | null
  class_name: string | null
  disabled: boolean
  created_at: string
  last_login: string | null
  backtest_count: number
  chat_count: number
  initial_password?: string
}

export interface ImportRow { row: number; username: string; display_name: string; password: string; error: string | null }
export interface ImportResult { class_name: string; total: number; valid: number; rows: ImportRow[]; created: boolean }

export const ROLE_TEXT: Record<Role, string> = { admin: '管理员', teacher: '老师', student: '学生' }

export const accountsApi = {
  classes: () => api.get<ClassInfo[]>('/api/classes'),
  createClass: (body: { name: string; description?: string; teacher_id?: number | null }) => api.post<ClassInfo>('/api/classes', body),
  updateClass: (id: number, body: Partial<ClassInfo>) => api.patch<ClassInfo>(`/api/classes/${id}`, body),
  regenerate: (id: number) => api.post<ClassInfo>(`/api/classes/${id}/regenerate-code`),
  deleteClass: (id: number) => api.del(`/api/classes/${id}`),
  activity: (id: number) => api.get<{ dates: string[]; backtests: number[]; active: number[] }>(`/api/classes/${id}/activity`),
  importStudents: (id: number, filename: string, content: string, dryRun: boolean) =>
    api.post<ImportResult>(`/api/classes/${id}/import`, { filename, content, dry_run: dryRun }),
  users: (params: { role?: string; class_id?: number; q?: string } = {}) => {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== '').map(([k, v]) => [k, String(v)]))
    return api.get<ManagedUser[]>(`/api/users${qs.toString() ? `?${qs}` : ''}`)
  },
  createUser: (body: { username: string; display_name?: string; password?: string; role?: Role; class_id?: number | null }) =>
    api.post<ManagedUser>('/api/users', body),
  updateUser: (id: number, body: Partial<Pick<ManagedUser, 'display_name' | 'role' | 'class_id' | 'disabled'>>) =>
    api.patch<ManagedUser>(`/api/users/${id}`, body),
  resetPassword: (id: number, password = '') => api.post<{ ok: boolean; password: string }>(`/api/users/${id}/reset-password`, { password }),
  deleteUser: (id: number) => api.del(`/api/users/${id}`),
  userBacktests: (id: number) => api.get<{ id: string; kind: string; title: string; start: string; end: string; source: string; summary: Record<string, number>; created_at: string }[]>(`/api/users/${id}/backtests`),
  teacherInvite: () => api.get<{ code: string; enabled: boolean; source: string }>('/api/auth/teacher-invite'),
  setTeacherInvite: (code: string, enabled: boolean) => api.put<{ code: string; enabled: boolean; source: string }>('/api/auth/teacher-invite', { code, enabled }),
}

/** 生成并下载 CSV（带 BOM，Excel 打开不乱码） */
export function downloadCsv(filename: string, rows: (string | number)[][]) {
  const esc = (v: string | number) => {
    const s = String(v ?? '')
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const blob = new Blob(['﻿' + rows.map((r) => r.map(esc).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result).split(',')[1] ?? '')
    r.onerror = () => reject(new Error('读取文件失败'))
    r.readAsDataURL(file)
  })
}
