import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import fixture from '../../test-fixtures/onepostPostState.json'
import { DeliveryChips } from './DeliveryChips'

describe('DeliveryChips', () => {
  it('shows one chip per picked delivery with failed error and actions', () => {
    const html = renderToStaticMarkup(
      <DeliveryChips
        deliveries={fixture.deliveries}
        onRetry={() => {}}
        onDrop={() => {}}
      />,
    )
    expect(html).toContain('data-testid="delivery-chips"')
    expect(html).toContain('data-testid="delivery-chip-instagram"')
    expect(html).toContain('data-testid="delivery-chip-facebook"')
    expect(html).toContain('data-testid="delivery-error-facebook"')
    expect(html).toContain('401')
    expect(html).toContain('data-testid="delivery-retry-facebook"')
    expect(html).toContain('data-testid="delivery-drop-facebook"')
  })
})
