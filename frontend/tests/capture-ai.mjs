import { chromium, expect } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

// Explicitly invoked live smoke test: exactly one submission, no retries or mocks.
const output = fileURLToPath(new URL('../../artifacts/screenshots/', import.meta.url))
await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
const browserErrors = []
let submissions = 0
page.on('pageerror', error => browserErrors.push(error.message))
page.on('request', request => {
  if (request.url().endsWith('/v1/query') && request.method() === 'POST') submissions++
})
try {
  await page.goto('http://127.0.0.1:3000')
  await expect(page.getByText('PostgreSQL connected')).toBeVisible()
  await page.getByLabel('Your question').fill('Show the 5 most expensive products: name, category and unit_price, ordered by unit_price descending.')
  const responsePromise = page.waitForResponse(r => r.url().endsWith('/v1/query'), { timeout: 60000 })
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  const result = await (await responsePromise).json()
  await writeFile(`${output}ai-query-result.json`, JSON.stringify({ captured_at: new Date().toISOString(), submissions, result }, null, 2))
  expect(result.status, JSON.stringify(result)).toBe('success')
  expect(result.row_count).toBe(5)
  await expect(page.locator('tbody tr')).toHaveCount(5)
  await page.screenshot({ path: `${output}ai-query-desktop.png`, fullPage: true, animations: 'disabled' })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: `${output}ai-query-mobile.png`, fullPage: true, animations: 'disabled' })
  expect(submissions).toBe(1)
  expect(browserErrors).toEqual([])
  console.log('One live AI submission succeeded; desktop and mobile screenshots captured; no browser errors.')
} finally {
  await browser.close()
}
