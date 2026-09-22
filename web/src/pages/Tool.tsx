import { Navigate, useParams, useSearchParams } from 'react-router-dom'
import { ToolFrame } from '../components/ToolFrame'
import { TOOL_BY_SLUG, parentLabel, toolEmbedSrc } from '../lib/tools'

export function Tool() {
  const { slug = '' } = useParams()
  const [params] = useSearchParams()
  const tool = TOOL_BY_SLUG[slug]
  if (!tool) {
    return <Navigate to="/other" replace />
  }

  const chip = params.get('title') || params.get('asset') || params.get('item') || undefined
  const from = params.get('from') || tool.from

  return (
    <ToolFrame
      back={from}
      backLabel={parentLabel(from)}
      title={tool.label}
      hint={tool.hint}
      chip={chip}
      src={toolEmbedSrc(tool, params)}
    />
  )
}
