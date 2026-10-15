import { test, expect } from '@playwright/test'

async function runSQL(page, sql) {
  await page.getByRole('button', { name: 'SQL', exact: true }).click()
  await page.getByLabel('SQL query', { exact: true }).fill(sql)
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Run query', exact: true })).toBeVisible()
}

test('real query, sorting, feedback and history', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/')
  await expect(page.getByText('PostgreSQL connected')).toBeVisible()
  await runSQL(page, 'SELECT name, unit_price FROM products ORDER BY unit_price DESC LIMIT 5')
  await expect(page.locator('tbody tr')).toHaveCount(5)
  await page.getByRole('button', { name: 'unit_price', exact: true }).click()
  const prices = await page.locator('tbody tr td:nth-child(2)').allTextContents()
  expect(prices.map(Number)).toEqual(prices.map(Number).sort((a,b) => a-b))
  await page.getByRole('button', { name: 'Yes', exact: true }).click()
  await expect(page.getByText('Feedback recorded')).toBeVisible()
  await page.getByRole('button', { name: 'Query history', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Query history' })).toBeVisible()
  await expect(page.locator('.hist-item').first()).toContainText('SELECT name')
  expect(errors).toEqual([])
})

test('schema and evaluations are real pages', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Database schema', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'customers', exact: true })).toBeVisible()
  await expect(page.locator('.schema-card')).toHaveCount(8)
  await page.getByRole('button', { name: 'Evaluations', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Run Evals' })).toBeDisabled()
  await expect(page.getByText('Live evaluations are disabled.', { exact: false })).toBeVisible()
})

test('unsafe query blocked and database remains available', async ({ page }) => {
  await page.goto('/')
  await runSQL(page, 'DELETE FROM customers')
  await expect(page.getByText('Query Blocked by Guardrails')).toBeVisible()
  await runSQL(page, 'SELECT COUNT(*) AS count FROM customers')
  await expect(page.locator('tbody')).toContainText('20')
})

test('empty and database failure states', async ({ page }) => {
  await page.goto('/')
  await runSQL(page, 'SELECT name FROM products WHERE false')
  await expect(page.getByText('No rows returned', { exact: true })).toBeVisible()
  await runSQL(page, 'SELECT missing_column FROM products')
  await expect(page.getByText('The database could not execute this query.', { exact: false })).toBeVisible()
})

test('pagination preserves all returned rows', async ({ page }) => {
  await page.goto('/')
  await runSQL(page, 'SELECT order_id, status FROM orders ORDER BY order_id LIMIT 25')
  await expect(page.locator('tbody tr')).toHaveCount(20)
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect(page.locator('tbody tr')).toHaveCount(5)
  await page.getByRole('button', { name: 'Previous page' }).click()
  await expect(page.locator('tbody tr')).toHaveCount(20)
})

test('mobile navigation and query stay inside viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await runSQL(page, 'SELECT name, category, unit_price FROM products LIMIT 5')
  await expect(page.locator('tbody tr')).toHaveCount(5)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Database schema', exact: true }).click()
  await expect(page.locator('.schema-card')).toHaveCount(8)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

test('clarification sends interpretation and feedback failure is honest (mocked transport)', async ({ page }) => {
  let count = 0
  await page.route('**/v1/query', async route => {
    count++
    const request = route.request().postDataJSON()
    if (count === 2) expect(request.clarification_choice).toBe('Net: After discounts')
    await route.fulfill({ json: count === 1 ? {
      query_id: 'test-clarification', question: 'What is revenue?', status: 'clarification_needed',
      clarification_options: [{ label: 'Net', description: 'After discounts', example_sql: 'SELECT 1' }],
    } : {
      query_id: 'test-result', question: 'What is revenue?', status: 'success', sql: 'SELECT 1',
      columns: ['value'], rows: [[1]], row_count: 1, total_rows_available: 1,
      guardrail_violations: [], hallucination_flags: [], tables_used: [],
    } })
  })
  await page.route('**/v1/feedback', route => route.fulfill({ status: 503, json: { detail: 'Feedback storage unavailable' } }))
  await page.goto('/')
  await page.getByLabel('Your question').fill('What is revenue?')
  await page.getByRole('button', { name: 'Run query', exact: true }).click()
  await page.getByRole('button', { name: /Net After discounts/ }).click()
  await page.getByRole('button', { name: 'Yes', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveText('Feedback storage unavailable')
  await expect(page.getByText('Feedback recorded')).toHaveCount(0)
})
