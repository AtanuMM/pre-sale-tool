const PLACEHOLDER_TOKENS = new Set(['unknown', 'tbd', 'na', 'test', 'client', 'xxx'])

/** Whole-token match after splitting on non-alphanumerics. "n/a" is treated as "na". */
export function isPlaceholderClientName(name: string): boolean {
  const normalized = name.toLowerCase().replace(/n\/a/gi, 'na')
  const tokens = normalized.split(/[^a-z0-9]+/g).filter(Boolean)
  return tokens.some((token) => PLACEHOLDER_TOKENS.has(token))
}
