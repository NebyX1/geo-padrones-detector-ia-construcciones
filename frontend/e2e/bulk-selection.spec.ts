import { test, expect } from '@playwright/test'
import type { FeatureCollection, MultiPolygon } from 'geojson'
import { mkdir, writeFile } from 'node:fs/promises'

test('selección rectangular real, inferencia múltiple, filtros, orden y CSV completo', async ({ page, request }) => {
  test.setTimeout(300000)
  await page.goto('/')
  await page.getByLabel('Correo electrónico').fill('browser-test@example.org')
  await page.getByLabel('Contraseña', { exact: true }).fill('Disposable-browser-test-only-2026')
  await expect(page.getByLabel('Resultado del captcha')).toBeEnabled()
  const operands = (await page.locator('#captcha-question').innerText()).match(/\d+/g)!.map(Number)
  await page.getByLabel('Resultado del captcha').fill(String(operands[0] + operands[1]))
  await page.getByRole('button', { name: 'Ingresar a la plataforma' }).click()
  await expect(page.getByLabel('Código de verificación')).toBeVisible()
  const inbox = await (await request.get('http://127.0.0.1:8125/api/v1/messages')).json()
  const entry = inbox.messages.find((m: { To: { Address: string }[] }) => m.To.some(t => t.Address === 'browser-test@example.org'))
  const message = await (await request.get(`http://127.0.0.1:8125/api/v1/message/${entry.ID}`)).json()
  await page.getByLabel('Código de verificación').fill(message.Text.match(/\b\d{6}\b/)[0])
  await page.getByRole('button', { name: 'Verificar e ingresar' }).click()
  await expect(page.getByRole('heading', { name: /Explorador catastral/ })).toBeVisible()
  await page.getByLabel('Localidad', { exact: true }).selectOption({ label: 'MINAS' })
  await page.getByRole('link', { name: 'Selección múltiple', exact: true }).click()
  const api = page.request
  const get = async (path: string) => (await api.get('/api/v1' + path)).json()
  const locality = (await get('/localities')).items.find((l: { name: string }) => l.name === 'MINAS')
  const extent: number[] = locality.bbox
  const collection: FeatureCollection<MultiPolygon> = await get(`/parcels?format=geojson&limit=1000&bbox=${extent.join(',')}`)
  const boxes = collection.features.filter(f => f.properties!.m2_parcela > 150 && f.properties!.m2_parcela < 1000).map(f => {
    const points = f.geometry.coordinates.flat(2)
    return [Math.min(...points.map(p => p[0])), Math.min(...points.map(p => p[1])), Math.max(...points.map(p => p[0])), Math.max(...points.map(p => p[1]))]
  })
  const center = [(extent[0] + extent[2]) / 2, (extent[1] + extent[3]) / 2]
  boxes.sort((a, b) => Math.hypot((a[0] + a[2]) / 2 - center[0], (a[1] + a[3]) / 2 - center[1]) - Math.hypot((b[0] + b[2]) / 2 - center[0], (b[1] + b[3]) / 2 - center[1]))
  const target = boxes[0]
  expect(target).toBeTruthy()
  // Web Mercator projection matches Leaflet fitBounds. The gesture uses public screen coordinates.
  const project = (lon: number, lat: number) => {
    const sin = Math.sin(lat * Math.PI / 180)
    return [(lon + 180) / 360 * 256, (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * 256]
  }
  const map = page.locator('.bulk-map .leaflet-container')
  await expect(map).toBeVisible()
  await expect(page.locator('.bulk-map-caption')).toContainText(/^[1-9]/, { timeout: 15000 })
  const screen = (await map.boundingBox())!
  const nw = project(extent[0], extent[3]), se = project(extent[2], extent[1])
  let zoom = Math.min(19, Math.floor(Math.log2(Math.min((screen.width - 60) / (se[0] - nw[0]), (screen.height - 60) / (se[1] - nw[1])))))
  const origin = [(nw[0] + se[0]) / 2, (nw[1] + se[1]) / 2]
  const first = project(target[0], target[3]), last = project(target[2], target[1])
  while ((last[0] - first[0]) * 2 ** zoom < 12 && zoom < 19) {
    await map.locator('.leaflet-control-zoom-in').click()
    zoom++
  }
  await expect(page.getByRole('button', { name: 'Seleccionar rectángulo', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Seleccionar rectángulo', exact: true }).click()
  const point = (p: number[]) => ({ x: screen.x + screen.width / 2 + (p[0] - origin[0]) * 2 ** zoom, y: screen.y + screen.height / 2 + (p[1] - origin[1]) * 2 ** zoom })
  const a = point(first), b = point(last)
  const previewResponse = page.waitForResponse(r => r.url().endsWith('/bulk-selections/preview') && r.request().method() === 'POST')
  await page.mouse.move(a.x, a.y)
  await page.mouse.down()
  await page.mouse.move(b.x, b.y, { steps: 12 })
  await page.mouse.up()
  const preview = await (await previewResponse).json()
  expect(preview.total).toBeGreaterThan(1)
  expect(preview.total).toBeLessThan(15)
  await page.getByLabel('Nombre del lote').fill('Minas · selección rectangular QA real')
  await expect(page.locator('.bulk-map-caption')).toContainText(/^[1-9]/, { timeout: 15000 })
  await mkdir('../artifacts/screenshots', { recursive: true })
  await page.screenshot({ path: '../artifacts/screenshots/bulk-selection.png', fullPage: true })
  const created = page.waitForResponse(r => r.url().endsWith('/bulk-selections') && r.request().method() === 'POST')
  await page.getByRole('button', { name: new RegExp(`^Analizar ${preview.total} padrones$`) }).click()
  const response = await created
  expect(response.status()).toBe(202)
  const batchId = (await response.json()).batch.id
  await expect(page.getByRole('heading', { name: 'Analítica de los casos seleccionados' })).toBeVisible()
  await expect.poll(async () => (await get(`/bulk-selections/${batchId}`)).batch.status, { timeout: 210000, intervals: [2000] }).toBe('COMPLETED')
  await expect(page.locator('.bulk-progress-value strong')).toHaveText('100 %', { timeout: 15000 })
  const all = await get(`/bulk-selections/${batchId}/results?sort=footprint_desc`)
  expect(all.total_filtered).toBe(preview.total)
  expect(all.items.every((r: { state: string; m2_huella_detectada: number }) => ['CON_CONSTRUCCION_VISIBLE', 'SIN_CONSTRUCCION_VISIBLE'].includes(r.state) && r.m2_huella_detectada >= 0)).toBe(true)
  await page.getByLabel('Construcción detectada', { exact: true }).selectOption('SIN_CONSTRUCCION_VISIBLE')
  const withoutBuildings = all.items.filter((r: { state: string }) => r.state === 'SIN_CONSTRUCCION_VISIBLE')
  if (!withoutBuildings.length) await expect(page.getByText('Sin casos para estos filtros', { exact: true })).toBeVisible()
  await page.getByLabel('Construcción detectada', { exact: true }).selectOption('CON_CONSTRUCCION_VISIBLE')
  await page.getByLabel('Huella desde (m²)', { exact: true }).fill('100')
  await page.getByLabel('Huella hasta (m²)', { exact: true }).fill('500')
  const visible = all.items.filter((r: { state: string; m2_huella_detectada: number }) => r.state === 'CON_CONSTRUCCION_VISIBLE' && r.m2_huella_detectada >= 100 && r.m2_huella_detectada <= 500)
  expect(visible.length).toBeGreaterThan(0)
  await expect(page.locator('.bulk-table tbody tr')).toHaveCount(visible.length)
  const ascending = page.waitForResponse(r => r.url().includes(`/bulk-selections/${batchId}/results?`) && r.url().includes('sort=footprint_asc'))
  await page.getByLabel('Ordenar por').selectOption('footprint_asc')
  const ascendingRows = (await (await ascending).json()).items
  expect(ascendingRows.map((r: { m2_huella_detectada: number }) => r.m2_huella_detectada)).toEqual(visible.map((r: { m2_huella_detectada: number }) => r.m2_huella_detectada).sort((a: number, b: number) => a - b))
  await page.getByLabel('Ordenar por').selectOption('footprint_desc')
  await expect(page.locator('.bulk-table tbody tr')).toHaveCount(visible.length)
  await page.screenshot({ path: '../artifacts/screenshots/bulk-analytics.png', fullPage: true })
  const exported = page.waitForResponse(r => r.url().endsWith('/exports') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Exportar casos filtrados a CSV', exact: true }).click()
  const exportJob = (await (await exported).json()).job
  await expect.poll(async () => (await get(`/exports/${exportJob.id}`)).job.status, { timeout: 30000, intervals: [1000] }).toBe('COMPLETED')
  const link = page.getByRole('link', { name: /^Descargar CSV/ })
  await expect(link).toBeVisible({ timeout: 15000 })
  const csv = await (await api.get((await link.getAttribute('href'))!)).text()
  expect(csv).toContain('lote_seleccion')
  const lines = csv.trim().split(/\r?\n/)
  expect(lines.length - 1).toBe(visible.length)
  expect(lines.slice(1).every(line => line.includes(batchId) && line.includes('CON_CONSTRUCCION_VISIBLE'))).toBe(true)
  await mkdir('../artifacts/tests', { recursive: true })
  await writeFile('../artifacts/tests/bulk-real.json', JSON.stringify({ scope: 'Disposable real official Minas geometries and actual FLAIR inference; not an accuracy assessment', batchId, parcels: preview.total, states: (await get(`/bulk-selections/${batchId}`)).batch.states, exported_filtered: visible.length }, null, 2))
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Analítica de los casos seleccionados' })).toBeVisible()
})
