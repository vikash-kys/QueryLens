import { chromium, expect } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

// Captures only real application responses. No request interception or mock data.
const output = fileURLToPath(new URL('../../artifacts/screenshots/', import.meta.url))
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const browserErrors = []
page.on('pageerror', e => browserErrors.push(e.message))
const captures = []
async function capture(name, fullPage = false) {
  await page.screenshot({ path: `${output}${name}.png`, fullPage, animations: 'disabled' })
  captures.push(name + '.png')
}
async function home() {
  await page.goto('http://127.0.0.1:3000')
  await expect(page.getByText('PostgreSQL connected')).toBeVisible()
}
async function query(sql) {
  await page.getByRole('button', { name: 'SQL', exact: true }).click()
  await page.getByLabel('SQL query', { exact: true }).fill(sql)
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Run query', exact: true })).toBeVisible()
}
try {
  await home()
  await capture('home-desktop')
  await query('SELECT name, category, revenue, units_sold FROM product_performance ORDER BY revenue DESC NULLS LAST LIMIT 5')
  await expect(page.locator('tbody tr')).toHaveCount(5)
  await capture('query-desktop')
  await page.getByRole('button', { name: 'Yes', exact: true }).click()
  await expect(page.getByText('Feedback recorded')).toBeVisible()
  await capture('feedback-desktop')
  await page.setViewportSize({ width: 390, height: 844 })
  await capture('query-mobile', true)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.getByRole('button', { name: 'Database schema', exact: true }).click()
  await expect(page.locator('.schema-card')).toHaveCount(8)
  await capture('schema-desktop')
  await page.setViewportSize({ width: 390, height: 844 })
  await capture('schema-mobile', true)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.getByRole('button', { name: 'Query history', exact: true }).click()
  await expect(page.locator('.hist-item').first()).toBeVisible()
  await capture('history-desktop')
  await page.getByRole('button', { name: 'Evaluations', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Run Evals' })).toBeDisabled()
  await capture('evaluations-desktop')
  await home()
  await query('DELETE FROM customers WHERE is_active = false')
  await expect(page.getByText('Query Blocked by Guardrails')).toBeVisible()
  await capture('blocked-desktop')
  await home()
  await query('SELECT name FROM products WHERE false')
  await expect(page.getByText('No rows returned', { exact: true })).toBeVisible()
  await capture('empty-result-desktop')
  await home()
  await query('SELECT missing_column FROM products')
  await expect(page.getByText('The database could not execute this query.', { exact: false })).toBeVisible()
  await capture('error-desktop')
  await home()
  await page.setViewportSize({ width: 390, height: 844 })
  await capture('home-mobile', true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(browserErrors).toEqual([])
  await writeFile(`${output}capture-manifest.json`, JSON.stringify({ captured_at: new Date().toISOString(), url: page.url(), desktop: '1440x900', mobile: '390x844 (full page where needed)', backend: 'real PostgreSQL; SQL mode; no model calls', captures, browserErrors }, null, 2))
  console.log(`Captured ${captures.length} real screens; no browser errors.`)
} finally { await browser.close() }
