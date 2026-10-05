/** WCAG 2.x contrast ratios for theme token pairs (run: node scripts/measure-contrast.mjs) */

function hexToRgb(hex) {
  const h = hex.replace('#', '')
  const n = parseInt(h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function relativeLuminance([r, g, b]) {
  const srgb = [r, g, b].map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * srgb[0] + 0.7152 * srgb[1] + 0.0722 * srgb[2]
}

function contrastRatio(fgHex, bgHex) {
  const l1 = relativeLuminance(hexToRgb(fgHex))
  const l2 = relativeLuminance(hexToRgb(bgHex))
  const lighter = Math.max(l1, l2)
  const darker = Math.min(l1, l2)
  return (lighter + 0.05) / (darker + 0.05)
}

const light = {
  background: '#f1f5f9',
  card: '#ffffff',
  fg: '#0f172a',
  muted: '#5e6b80',
  primary: '#4f46e5',
  primaryFg: '#ffffff',
  sidebarFg: '#e2e8f0',
  sidebarBg: '#0f172a',
  sidebarActiveBg: '#4f46e5',
  sidebarActiveFg: '#ffffff',
  sidebarMuted: '#94a3b8',
  successSubtleFg: '#047857',
  successSubtle: '#ecfdf5',
  inactiveSubtleFg: '#5e6b80',
  inactiveSubtle: '#f1f5f9',
  chipSkyFg: '#0369a1',
  chipSky: '#e0f2fe',
}

const dark = {
  background: '#1c1917',
  card: '#292524',
  fg: '#f8fafc',
  muted: '#94a3b8',
  primary: '#4f46e5',
  primaryFg: '#ffffff',
  sidebarFg: '#e2e8f0',
  sidebarBg: '#0f172a',
  sidebarActiveBg: '#4f46e5',
  sidebarActiveFg: '#ffffff',
  sidebarMuted: '#94a3b8',
  successSubtleFg: '#a7f3d0',
  successSubtle: '#052e16',
  inactiveSubtleFg: '#a1a1aa',
  inactiveSubtle: '#27272a',
  chipSkyFg: '#7dd3fc',
  chipSky: '#0c4a6e',
}

const pairs = [
  ['body on card', 'fg', 'card'],
  ['body on background', 'fg', 'background'],
  ['muted on card', 'muted', 'card'],
  ['muted on background', 'muted', 'background'],
  ['primary-fg on primary', 'primaryFg', 'primary'],
  ['sidebar text on sidebar bg', 'sidebarFg', 'sidebarBg'],
  ['sidebar muted on sidebar bg', 'sidebarMuted', 'sidebarBg'],
  ['sidebar active on active bg', 'sidebarActiveFg', 'sidebarActiveBg'],
  ['success badge fg on bg', 'successSubtleFg', 'successSubtle'],
  ['inactive badge fg on bg', 'inactiveSubtleFg', 'inactiveSubtle'],
  ['chip sky fg on bg', 'chipSkyFg', 'chipSky'],
]

function report(mode, tokens) {
  console.log(`\n${mode}`)
  console.log('Pair | Ratio | AA body (4.5) | AA large/UI (3)')
  for (const [label, fgKey, bgKey] of pairs) {
    const ratio = contrastRatio(tokens[fgKey], tokens[bgKey])
    const body = ratio >= 4.5 ? 'pass' : 'FAIL'
    const ui = ratio >= 3 ? 'pass' : 'FAIL'
    console.log(`${label} | ${ratio.toFixed(2)}:1 | ${body} | ${ui}`)
  }
}

report('Light', light)
report('Dark', dark)
