import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { DeliveryChips } from './DeliveryChips'

describe('DeliveryChips', () => {
  it('shows failed error with retry and drop', () => {
    const onRetry = vi.fn()
    const onDrop = vi.fn()
    render(
      <DeliveryChips
        deliveries={[
          { channel: 'facebook', status: 'failed', last_error: 'postiz create_post: 401' },
        ]}
        onRetry={onRetry}
        onDrop={onDrop}
      />,
    )
    expect(screen.getByText('postiz create_post: 401')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    fireEvent.click(screen.getByRole('button', { name: 'Drop' }))
    expect(onRetry).toHaveBeenCalledWith('facebook')
    expect(onDrop).toHaveBeenCalledWith('facebook')
  })
})
