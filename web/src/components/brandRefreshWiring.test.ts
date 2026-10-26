import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

function read(rel: string) {
  return readFileSync(resolve(__dirname, rel), 'utf8')
}

describe('brand switch refresh wiring', () => {
  it('increments brandVersion when brand changes', () => {
    const source = read('./BrandSwitch.tsx')
    expect(source).toContain('const [brandVersion, setBrandVersion] = useState(0)')
    expect(source).toContain('setBrandVersion((v) => v + 1)')
  })

  it('remounts routed page when brandVersion changes', () => {
    const source = read('./Shell.tsx')
    expect(source).toContain('<Outlet key={brandVersion} />')
  })
})
