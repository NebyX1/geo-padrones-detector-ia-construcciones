import { test, expect } from '@playwright/test'

test('gestionar análisis y revisiones sin afectar el catastro de prueba', async ({ page, request }) => {
  test.setTimeout(240000)
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
  const api = page.request
  const get = async (path: string) => (await api.get('/api/v1' + path)).json()
  const csrf = (await get('/auth/csrf')).csrf_token
  const reset = { target: 'analysis', mode: 'all' }
  let initial: { fingerprint: string; empty: boolean; active_jobs: number }
  await expect.poll(async () => {
    const response = await api.post('/api/v1/analysis/cleanup/preview', { data: reset, headers: { 'X-CSRFToken': csrf } })
    expect(response.status()).toBe(200)
    initial = await response.json()
    return initial.active_jobs
  }, { timeout: 30000, intervals: [1000] }).toBe(0)
  if (!initial!.empty) {
    const response = await api.post('/api/v1/analysis/cleanup', { data: { ...reset, fingerprint: initial!.fingerprint, confirmation: 'ELIMINAR' }, headers: { 'X-CSRFToken': csrf } })
    expect(response.status()).toBe(200)
  }
  const parcels = (await get('/parcels?limit=100')).items.filter((p: { m2_parcela: number }) => p.m2_parcela > 150 && p.m2_parcela < 600).slice(0, 2)
  expect(parcels).toHaveLength(2)
  const scene = (await get('/imagery/scenes')).items[0]
  const model = (await get('/models')).items[0]
  const payloads = parcels.map((p: { id: string }) => ({ parcel_ids: [p.id], scene_id: scene.id, model_version_id: model.id }))
  const jobIds = []
  for (const data of payloads) {
    const response = await api.post('/api/v1/analysis/jobs', { data, headers: { 'X-CSRFToken': csrf } })
    expect(response.status()).toBe(202)
    jobIds.push((await response.json()).job.id)
  }
  await expect.poll(async () => Promise.all(jobIds.map(async id => (await get(`/analysis/jobs/${id}`)).job.status)), { timeout: 150000, intervals: [2000] }).toEqual(['COMPLETED', 'COMPLETED'])
  expect((await get('/reviews')).total).toBe(2)

  await page.getByRole('link', { name: 'Casos para revisar', exact: true }).click()
  await expect(page.getByText('2 casos filtrados')).toBeVisible()
  await page.getByLabel('Filtrar por padrón o localidad').fill(parcels[0].padron)
  await expect(page.getByText('1 caso filtrado')).toBeVisible()
  await page.getByRole('button', { name: 'Eliminar filtrados', exact: true }).click()
  const reviewDialog = page.getByRole('dialog', { name: 'Eliminar casos y resultados' })
  await expect(reviewDialog).toBeVisible()
  await expect(reviewDialog.getByText('Resultados de IA')).toBeVisible()
  await expect(reviewDialog.getByRole('button', { name: 'Eliminar definitivamente' })).toBeDisabled()
  await reviewDialog.getByLabel('Confirmar eliminación').fill('ELIMINAR')
  await reviewDialog.getByRole('button', { name: 'Eliminar definitivamente' }).click()
  await expect(reviewDialog).toBeHidden()
  await expect.poll(async () => (await get('/reviews')).total).toBe(1)
  expect((await get(`/parcels/${parcels[0].id}`)).parcel.properties.state).toBe('NO_ANALIZADO')
  expect((await get(`/parcels/${parcels[1].id}`)).parcel.properties.state).not.toBe('NO_ANALIZADO')

  await page.getByRole('button', { name: 'Limpiar filtros' }).click()
  await page.getByRole('link', { name: 'Análisis con IA', exact: true }).click()
  await expect(page.getByText('1 trabajo con estos filtros')).toBeVisible()
  await page.getByRole('button', { name: 'Empezar de cero', exact: true }).click()
  const resetDialog = page.getByRole('dialog', { name: 'Empezar de cero' })
  await expect(resetDialog).toBeVisible()
  await resetDialog.getByLabel('Confirmar eliminación').fill('ELIMINAR')
  await resetDialog.getByRole('button', { name: 'Eliminar definitivamente' }).click()
  await expect(resetDialog).toBeHidden()
  await expect.poll(async () => (await get('/analysis/jobs?kind=analysis')).total).toBe(0)
  expect((await get('/reviews')).total).toBe(0)
  expect((await get('/parcels?limit=1')).items.length).toBe(1)
  const response = await api.post('/api/v1/analysis/jobs', { data: payloads[1], headers: { 'X-CSRFToken': csrf } })
  expect(response.status()).toBe(202)
  expect((await response.json()).job.id).not.toBe(jobIds[1])
})
