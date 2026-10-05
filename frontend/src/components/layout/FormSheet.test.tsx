import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

import { FormSheet } from '@/components/layout/FormSheet'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

describe('FormSheet', () => {
  afterEach(() => cleanup())

  it('renders fields inside padded body and supports keyboard focus', async () => {
    const user = userEvent.setup()
    render(
      <FormSheet
        open
        onOpenChange={() => {}}
        title="Create user"
        description="Test form"
        footer={<Button type="button">Save</Button>}
      >
        <div className="space-y-2">
          <Label htmlFor="test-email">Email</Label>
          <Input id="test-email" />
        </div>
      </FormSheet>,
    )

    const body = screen.getByTestId('form-sheet-body')
    expect(body).toHaveClass('px-6')

    const input = screen.getByLabelText('Email')
    expect(input).not.toHaveAttribute('disabled')
    await user.click(input)
    expect(input).toHaveFocus()
  })
})
