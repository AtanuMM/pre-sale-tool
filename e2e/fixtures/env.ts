const placeholderPassword = 'change-me-admin-password'
const e2ePassword = process.env.E2E_ADMIN_PASSWORD
export const adminEmail = process.env.E2E_ADMIN_EMAIL || process.env.ADMIN_EMAIL || 'admin@example.com'
export const adminPassword =
  (e2ePassword && e2ePassword !== placeholderPassword ? e2ePassword : null) ||
  process.env.ADMIN_PASSWORD ||
  placeholderPassword

export const liveGenerate = process.env.E2E_LIVE_GENERATE === '1'
