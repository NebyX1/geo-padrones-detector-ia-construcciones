import { test, expect } from '@playwright/test'

test('entrada local sin credenciales y login protegido conservado',async({page})=>{
  await page.goto('http://127.0.0.1:8787/')
  await expect(page.getByRole('heading',{name:/Explorador catastral/})).toBeVisible()
  await expect(page.getByText('Modo de prueba local',{exact:true})).toBeVisible()
  const session=await(await page.request.get('http://127.0.0.1:8787/api/v1/auth/me')).json()
  expect(session.user.is_local_preview).toBe(true)
  const parcels=await page.request.get('http://127.0.0.1:8787/api/v1/parcels?limit=1')
  expect(parcels.status()).toBe(200)
  expect((await parcels.json()).items).toHaveLength(1)
  for(const path of ['dashboard','multi-selection','analysis','imports','comparisons','reviews','exports','admin','settings']){
    await page.goto(`http://127.0.0.1:8787/${path}`)
    await expect(page.getByRole('heading',{level:1})).toBeVisible()
    await expect(page.getByText('Modo de prueba local',{exact:true})).toBeVisible()
  }
  await page.getByRole('link',{name:'Ver login con captcha y 2FA'}).click()
  await expect(page.getByText('Bienvenido a GeoPadrones')).toBeVisible()
  await expect(page.getByLabel('Resultado del captcha')).toBeEnabled()
  await page.getByLabel('Correo electrónico').fill('local-preview-check@example.org')
  await page.getByLabel('Contraseña',{exact:true}).fill('Not-a-real-account-password-2026')
  await page.getByLabel('Resultado del captcha').fill('99')
  await page.getByRole('button',{name:'Ingresar a la plataforma'}).click()
  await expect(page.getByRole('alert').filter({hasText:'Captcha incorrecto o vencido'})).toBeVisible()
  await page.getByRole('link',{name:'Volver a la prueba sin autenticación'}).click()
  await expect(page.getByRole('heading',{name:/Explorador catastral/})).toBeVisible()
  await page.screenshot({path:'../artifacts/screenshots/local-preview-explorer.png',fullPage:true})
})
