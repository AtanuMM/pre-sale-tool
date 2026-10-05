/**
 * Scan src for Tailwind-like class tokens and report any not found in built CSS.
 * Run: npm run build && node scripts/audit-tailwind-classes.mjs
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const srcDir = join(root, 'src')
const distDir = join(root, 'dist/assets')

function walk(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...walk(p))
    else if (/\.(tsx|ts|jsx|js)$/.test(name)) out.push(p)
  }
  return out
}

function extractClasses(source) {
  const found = new Set()
  const re = /className(?:=\{cn\([^)]*\}|="([^"]*)"|=\{'([^']*)'\}|=\{`([^`]*)`\})/g
  let m
  while ((m = re.exec(source))) {
    const chunk = m[1] ?? m[2] ?? m[3] ?? ''
    for (const token of chunk.split(/\s+/)) {
      const t = token.replace(/^['"`]|['"`]$/g, '').trim()
      if (t && !t.includes('${') && !t.startsWith('[')) found.add(t)
    }
  }
  const simple = /className="([^"]+)"/g
  while ((m = simple.exec(source))) {
    for (const token of m[1].split(/\s+/)) {
      if (token) found.add(token)
    }
  }
  return found
}

const cssFiles = readdirSync(distDir).filter((f) => f.endsWith('.css'))
const css = cssFiles.map((f) => readFileSync(join(distDir, f), 'utf8')).join('\n')

const allClasses = new Set()
for (const file of walk(srcDir)) {
  const src = readFileSync(file, 'utf8')
  for (const c of extractClasses(src)) allClasses.add(c)
}

const missing = []
for (const cls of [...allClasses].sort()) {
  if (cls.includes(':') || cls.includes('(') || cls.startsWith('!')) continue
  const escaped = cls.replace(/\//g, '\\/').replace(/\./g, '\\.')
  const pattern = new RegExp(`\\.${escaped}[\\s,{:]`)
  if (!pattern.test(css) && !css.includes(`.${cls}`)) {
    missing.push(cls)
  }
}

if (missing.length === 0) {
  console.log('No unresolved utility classes detected in scan (heuristic).')
} else {
  console.log('Classes not found in built CSS (review — may be dynamic or false positive):')
  for (const c of missing) console.log(`  - ${c}`)
}
