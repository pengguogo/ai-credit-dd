/** 图片附件预校验（契约 §多模态输入约定：仅 image_url；≤4 张、单张 ≤32MB；不支持 PDF）。 */
export const MAX_IMAGES = 4
const MAX_IMAGE_BYTES = 32 * 1024 * 1024

/** 与后端 / 模型视觉入参一致的允许类型；PDF 等其它附件一律拒绝。 */
export const ALLOWED_IMAGE_MIME = [
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
] as const

export const ALLOWED_IMAGE_ACCEPT = ALLOWED_IMAGE_MIME.join(',')
export const ALLOWED_IMAGE_LABEL = 'JPEG / PNG / WebP / GIF'

const EXT_BY_MIME: Record<string, string[]> = {
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/webp': ['.webp'],
  'image/gif': ['.gif'],
}

export interface PickedImage {
  name: string
  dataUrl: string
}

function isAllowedImage(file: File): boolean {
  if ((ALLOWED_IMAGE_MIME as readonly string[]).includes(file.type)) return true
  // 少数环境 type 为空：用扩展名兜底
  if (file.type) return false
  const lower = file.name.toLowerCase()
  return Object.values(EXT_BY_MIME).some((exts) => exts.some((ext) => lower.endsWith(ext)))
}

/** 读取用户选择的图片为 data URL；返回 [新增图片, 错误提示] */
export async function readImages(files: FileList | null, current: number): Promise<[PickedImage[], string]> {
  const raw = Array.from(files ?? [])
  if (raw.length === 0) return [[], '']
  const rejected = raw.filter((f) => !isAllowedImage(f))
  if (rejected.length > 0) {
    const name = rejected[0].name
    const isPdf = name.toLowerCase().endsWith('.pdf') || rejected[0].type === 'application/pdf'
    return [[], isPdf
      ? '不支持 PDF，请上传图片（JPEG / PNG / WebP / GIF）'
      : `不支持「${name}」。仅支持 ${ALLOWED_IMAGE_LABEL}`]
  }
  const list = raw.filter(isAllowedImage)
  if (current + list.length > MAX_IMAGES) return [[], `最多 ${MAX_IMAGES} 张图片`]
  const oversized = list.find((f) => f.size > MAX_IMAGE_BYTES)
  if (oversized) return [[], `${oversized.name} 超出 32MB 上限`]
  const read = (file: File) => new Promise<PickedImage>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve({ name: file.name, dataUrl: String(reader.result) })
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
  try {
    return [await Promise.all(list.map(read)), '']
  } catch {
    return [[], '图片读取失败']
  }
}
