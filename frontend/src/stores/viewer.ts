// 全局图片查看器的状态：任何 Markdown 里的图片点击后都在这里打开
import { reactive } from 'vue'

export const viewer = reactive({ src: '', alt: '', open: false })

export function openImage(src: string, alt = '') {
  Object.assign(viewer, { src, alt, open: true })
}
