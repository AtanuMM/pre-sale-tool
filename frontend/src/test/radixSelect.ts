import { screen } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'

import { prettyToken } from '@/lib/stepLayoutTypes'

/** Open a Radix `Select` trigger and choose an option by raw value. */
export async function pickSelectOption(
  user: UserEvent,
  trigger: HTMLElement,
  value: string,
): Promise<void> {
  await user.click(trigger)
  await user.click(screen.getByRole('option', { name: prettyToken(value) }))
}
