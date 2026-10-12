import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ChannelPicker } from './ChannelPicker'

describe('ChannelPicker', () => {
  it('toggles IG/FB/GBP and disables coming-soon channels', () => {
    const onChange = vi.fn()
    render(
      <ChannelPicker
        available={['instagram', 'facebook', 'gbp']}
        picked={['instagram', 'facebook']}
        onChange={onChange}
      />,
    )
    expect(screen.getByText('YouTube (coming later)')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Google Business' }))
    expect(onChange).toHaveBeenCalledWith(['instagram', 'facebook', 'gbp'])
  })

  it('is read-only when locked and requires at least one channel', () => {
    const onChange = vi.fn()
    render(
      <ChannelPicker available={['instagram', 'facebook']} picked={['instagram']} locked onChange={onChange} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Facebook' }))
    expect(onChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Instagram' }))
    expect(onChange).not.toHaveBeenCalled()
  })
})
