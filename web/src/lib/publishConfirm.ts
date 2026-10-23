/** Text for the "really send?" prompt, or null when Publish now is safe to fire (sandbox). */
export function publishNowConfirmText(
  mode: string | null | undefined,
  channels: string,
  title: string,
): string | null {
  if ((mode || '').toLowerCase() === 'sandbox') return null
  const where = channels ? ` to ${channels}` : ''
  const what = title ? `"${title}"` : 'this post'
  return `This is LIVE. ${what} goes out for real${where} right now. Send it?`
}
