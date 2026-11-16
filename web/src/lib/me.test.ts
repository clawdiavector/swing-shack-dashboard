import { afterEach, describe, expect, it, vi } from 'vitest'
import { setMeFromApi, signedInActorName } from './me'
import { actorName } from './plan'

describe('actorName with signed-in user', () => {
  afterEach(() => {
    setMeFromApi({ signed_in: false, user: null, shared: false })
    vi.restoreAllMocks()
  })

  it('returns the signed-in name without prompting', () => {
    setMeFromApi({
      signed_in: true,
      shared: false,
      user: { id: 'u1', name: 'Christelle', role: 'admin', brands: ['*'] },
    })
    expect(signedInActorName()).toBe('Christelle')
    const ask = vi.fn(() => 'Prompted Name')
    expect(actorName(ask)).toBe('Christelle')
    expect(ask).not.toHaveBeenCalled()
  })
})
