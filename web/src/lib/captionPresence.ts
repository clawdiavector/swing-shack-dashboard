export type CaptionTag = {
  id: 'caption' | 'no-caption'
  label: string
  tone: 'green' | 'mute'
}

export function captionTag(row: { caption_present?: boolean } | null | undefined): CaptionTag {
  if (row?.caption_present) {
    return { id: 'caption', label: 'Caption', tone: 'green' }
  }
  return { id: 'no-caption', label: 'No caption', tone: 'mute' }
}
