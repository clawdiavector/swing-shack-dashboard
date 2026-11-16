import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { PickBrandButtons, pickableBrands } from './PickBrand'

// Audit 3 Nov 2026: Photos, Library and Brand visuals dead-ended on "All brands" with
// only a "pick a brand" line. One tap on the page should pick it.
const rows = [
  { id: 'stick', label: 'Stick' },
  { id: 'mcm', label: 'MCM' },
  { id: 'swing-shack', label: 'Swing Shack' },
  { id: 'bag-drop', label: 'Bag Drop' },
]

describe('pickableBrands', () => {
  it('keeps the operating brands, in their order', () => {
    expect(pickableBrands(rows).map((b) => b.id)).toEqual(['stick', 'swing-shack', 'bag-drop'])
  })
})

describe('PickBrandButtons', () => {
  it('shows the message and one button per brand', () => {
    const html = renderToStaticMarkup(
      <PickBrandButtons message="Photos are kept per brand." brands={pickableBrands(rows)} onPick={() => undefined} />,
    )
    expect(html).toContain('Photos are kept per brand.')
    expect(html.match(/<button/g)).toHaveLength(3)
    for (const label of ['Stick', 'Swing Shack', 'Bag Drop']) expect(html).toContain(`>${label}<`)
    expect(html).not.toContain('MCM')
  })
})
