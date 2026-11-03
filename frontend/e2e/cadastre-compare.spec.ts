import { test, expect } from '@playwright/test'

// Todo el tráfico de la API se intercepta: los padrones y resultados son
// sintéticos y nunca se crean trabajos ni se modifican datos de la instalación.
test('compara una selección catastral sintética y destaca una discrepancia en el mapa', async ({ page }) => {
  let submitted: Record<string, unknown> | null = null
  const filters = {category:'urbano',locality:'AA',state:'no',padron_desde:100,padron_hasta:200}
  const batch = {
    id:'lote-sintetico', name:'Comparación sintética', total:1, processed:1, status:'COMPLETED',
    cancel_requested:false, scene_id:'imagen-sintetica', model_version_id:'modelo-sintetico',
    created_at:'2026-11-01T12:00:00Z', bounds:[-55.24,-34.38,-55.23,-34.37],
    selection_filters:filters, states:{CON_CONSTRUCCION_VISIBLE:1}, jobs:[],
  }
  const preview = {total:1,available:1,unavailable:0,sin_geometria:0,no_conciliados:0,fuera_cobertura:0,supera_limites:0,lineas_sin_resumen:0,can_analyze:true,max_parcels:5000}
  const summary = {total:1,discrepancia:1,coincide:0,sin_referencia:0,indeterminado:0,pendiente:0}
  const feature = {type:'Feature',id:'parcela-sintetica',properties:{
    id:'parcela-sintetica',parcel_id:'parcela-sintetica',padron:'123',locality:'MINAS',categoria_suelo:'urbano',
    declared_building:false,model_state:'CON_CONSTRUCCION_VISIBLE',outcome:'discrepancia',m2_huella_detectada:55,
    result_id:'resultado-sintetico',coverage:1,error:null,tiene_registro_alfanumerico:true,lineas_sin_resumen:false,
  },geometry:{type:'Polygon',coordinates:[[[-55.24,-34.38],[-55.23,-34.38],[-55.23,-34.37],[-55.24,-34.37],[-55.24,-34.38]]]}}
  await page.route('https://*.tile.openstreetmap.org/**', route => route.abort())
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname.replace('/api/v1','')
    const respond = (data:unknown, status=200) => route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)})
    if (path === '/auth/me') return respond({user:{id:'usuario-sintetico',name:'Prueba Sintética',role:'admin',is_active:true}})
    if (path === '/auth/csrf') return respond({csrf_token:'token-sintetico'})
    if (path === '/localities') return respond({items:[]})
    if (path === '/analysis/jobs') return respond({items:[]})
    if (path === '/imagery/scenes') return respond({items:[{id:'imagen-sintetica',name:'Minas',captured_at:'2025-12-01',resolution_m:0.05}]})
    if (path.startsWith('/imagery/scenes/imagen-sintetica/tiles/')) return route.fulfill({status:204})
    if (path === '/models') return respond({items:[{id:'modelo-sintetico',model_id:'FLAIR',revision:'123456789',enabled:true}]})
    if (path === '/preferences') return respond({settings:{default_thresholds:{probability:0.5,min_area:8}}})
    if (path === '/catastro-comparar/options') return respond({
      categories:[{value:'urbano',label:'Urbano',count:10},{value:'rural',label:'Rural',count:3}],
      localities:url.searchParams.get('category') === 'rural' ? [{value:'sin_localidad',label:'Sin localidad',count:3}] : [{value:'AA',label:'MINAS',count:10}],
      states:[{value:'si',label:'Con construcción declarada',count:3},{value:'no',label:'Sin construcción declarada',count:1},{value:'desconocido',label:'No definido',count:2}],
    })
    if (path === '/catastro-comparar/preview') return respond(preview)
    if (path === '/catastro-comparar/runs' && request.method() === 'GET') return respond({items:submitted ? [batch] : []})
    if (path === '/catastro-comparar/runs' && request.method() === 'POST') {submitted = request.postDataJSON(); return respond({batch},202)}
    if (path === '/catastro-comparar/runs/lote-sintetico') return respond({batch,summary,preview})
    if (path === '/catastro-comparar/runs/lote-sintetico/features') return respond({type:'FeatureCollection',features:[feature]})
    return respond({error:{message:`Ruta de prueba no simulada: ${path}`}},404)
  })

  await page.goto('/compare')
  await expect(page.getByRole('heading',{name:'Comparar padrones.'})).toBeVisible()
  await page.getByLabel('Categoría de suelo').selectOption('urbano')
  await page.getByLabel('Localidad de la comparación').selectOption('AA')
  await page.getByLabel('Construcción según Catastro').selectOption('no')
  await page.getByLabel('Padrón desde').fill('100')
  await page.getByLabel('Padrón hasta').fill('200')
  await page.getByRole('button',{name:'Comparar selección'}).click()
  await expect.poll(() => submitted).toMatchObject({...filters,scene_id:'imagen-sintetica',model_version_id:'modelo-sintetico',device:'cpu'})
  await expect(page).toHaveURL(/lote=lote-sintetico/)
  await expect(page.getByRole('button',{name:/Posible discrepancia/})).toContainText('1')
  await expect(page.getByLabel('Padrón desde')).toHaveValue('100')
  const canvas = page.locator('.cadastre-map canvas')
  await expect(canvas).toBeVisible()
  await expect.poll(() => canvas.evaluate((el:HTMLCanvasElement) => {
    const pixels = el.getContext('2d')!.getImageData(0,0,el.width,el.height).data
    for (let i=0;i<pixels.length;i+=4) if (pixels[i]>190 && pixels[i+1]<120 && pixels[i+2]<130 && pixels[i+3]>150) return true
    return false
  })).toBe(true)
  const map = page.locator('.cadastre-map .leaflet-container'), box = await map.boundingBox()
  expect(box).not.toBeNull()
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2)
  await expect(page.getByRole('heading',{name:'Padrón 123'})).toBeVisible()
  const detail = page.locator('.cadastre-detail')
  await expect(detail.getByText('Sin construcción declarada',{exact:true})).toBeVisible()
  await expect(detail.getByText('Construcción visible',{exact:true})).toBeVisible()
})
