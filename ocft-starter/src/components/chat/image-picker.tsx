/** 已选图片预览与移除；校验与读取见 lib/images.ts。 */
import { XIcon } from 'lucide-react'

import { ALLOWED_IMAGE_LABEL, MAX_IMAGES, type PickedImage } from '@/lib/images'

export function ImagePreviews({ images, disabled, onRemove }: {
  images: PickedImage[]
  disabled: boolean
  onRemove: (index: number) => void
}) {
  if (images.length === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-2">
      {images.map((img, i) => (
        <div key={`${img.name}-${i}`} className="relative">
          <img src={img.dataUrl} alt={img.name} title={img.name} className="size-14 rounded-md border object-cover" />
          <button
            type="button"
            aria-label={`移除 ${img.name}`}
            disabled={disabled}
            onClick={() => onRemove(i)}
            className="absolute -top-1.5 -right-1.5 flex size-5 items-center justify-center rounded-full bg-destructive text-white shadow outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <XIcon className="size-3" />
          </button>
        </div>
      ))}
      <span className="text-xs text-muted-foreground">
        {images.length}/{MAX_IMAGES} 张（{ALLOWED_IMAGE_LABEL}），随下一条消息发送
      </span>
    </div>
  )
}
