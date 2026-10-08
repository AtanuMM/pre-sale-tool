export type CopyResult =
  | { ok: true }
  | { ok: false; reason: 'unsupported' | 'denied' }

export async function copyTextToClipboard(text: string): Promise<CopyResult> {
  if (!text) return { ok: false, reason: 'unsupported' }
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return { ok: true }
    }
  } catch {
    return { ok: false, reason: 'denied' }
  }
  return { ok: false, reason: 'unsupported' }
}
