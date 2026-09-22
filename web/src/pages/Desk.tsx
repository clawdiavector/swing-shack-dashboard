import { Navigate, useSearchParams } from 'react-router-dom'
import { ToolFrame } from '../components/ToolFrame'
import { deskSrcFromSearch } from '../lib/desk'
import { matchTool, toolTo } from '../lib/tools'

export function Desk() {
  const [params] = useSearchParams()
  const src = deskSrcFromSearch(params.toString() ? `?${params}` : '')
  let parsed: URL | null = null
  try {
    parsed = new URL(src, 'https://campaign-os.local')
  } catch {
    parsed = null
  }
  const tool = parsed ? matchTool(parsed) : null
  if (tool) {
    return (
      <Navigate
        to={toolTo(tool.slug, {
          item: parsed?.searchParams.get('item') || undefined,
          asset: parsed?.searchParams.get('asset') || parsed?.searchParams.get('id') || undefined,
          campaign: parsed?.searchParams.get('campaign') || undefined,
          brand: parsed?.searchParams.get('brand') || undefined,
          title: parsed?.searchParams.get('title') || undefined,
        })}
        replace
      />
    )
  }

  return <ToolFrame back="/other" backLabel="Other" title="Classic tool" src={src} />
}