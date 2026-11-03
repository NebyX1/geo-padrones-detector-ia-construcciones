import { render, screen, waitFor, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { CadastreCompare } from './CadastreCompare'

const api = vi.hoisted(() => ({get:vi.fn(),post:vi.fn()}))
vi.mock('../../lib/axios', () => ({default:api}))
vi.mock('../auth/AuthProvider', () => ({useAuth:() => ({user:{id:'tester',role:'admin'}}),can:() => true}))
vi.mock('../parcels/hooks', () => ({
  useScenes:() => ({data:[{id:'scene',name:'Minas',captured_at:'2025-12'}]}),
  useModels:() => ({data:[{id:'model',model_id:'FLAIR',revision:'123456789',enabled:true}]}),
  usePreferences:() => ({data:{default_thresholds:{probability:0.5,min_area:8}}}),
}))
vi.mock('./ComparisonMap', () => ({ComparisonMap:() => <div>Mapa de prueba</div>}))

const categories = [{value:'urbano',label:'Urbano',count:10},{value:'rural',label:'Rural',count:5}]
const states = [{value:'si',label:'Con construcción',count:2},{value:'no',label:'Sin construcción',count:1},{value:'desconocido',label:'No definido',count:2}]
const preview = {total:5,available:3,unavailable:2,sin_geometria:1,no_conciliados:0,fuera_cobertura:1,supera_limites:0,lineas_sin_resumen:0,can_analyze:true,max_parcels:5000}
function setup(path='/compare') {
  const query = new QueryClient({defaultOptions:{queries:{retry:false},mutations:{retry:false}}})
  return render(<QueryClientProvider client={query}><MemoryRouter initialEntries={[path]}><CadastreCompare/></MemoryRouter></QueryClientProvider>)
}
beforeEach(() => {
  localStorage.clear(); api.get.mockReset(); api.post.mockReset()
  api.get.mockImplementation(async (url:string,config?:{params?:{category?:string}}) => {
    if (url === '/catastro-comparar/runs') return {data:{items:[]}}
    if (url === '/catastro-comparar/options') return {data:{categories,states,localities:config?.params?.category === 'rural' ? [{value:'sin_localidad',label:'Sin localidad',count:5}] : [{value:'AA',label:'Minas',count:10}]}}
    throw new Error(`GET inesperado: ${url}`)
  })
  api.post.mockImplementation(async (url:string) => {
    if (url === '/catastro-comparar/preview') return {data:preview}
    throw new Error(`POST inesperado: ${url}`)
  })
})
afterEach(() => cleanup())

it('encadena localidad con categoría y muestra por qué hay casos omitidos', async () => {
  setup()
  const user = userEvent.setup()
  const category = await screen.findByLabelText('Categoría de suelo')
  await user.selectOptions(category,'urbano')
  const locality = screen.getByLabelText('Localidad de la comparación')
  await screen.findByRole('option',{name:/Minas/})
  await user.selectOptions(locality,'AA')
  await user.selectOptions(screen.getByLabelText('Categoría de suelo'),'rural')
  await screen.findByRole('option',{name:/Sin localidad/})
  expect(screen.getByLabelText('Localidad de la comparación')).toHaveValue('todos')
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/catastro-comparar/preview',expect.objectContaining({category:'rural',locality:'todos',state:'todos'}),expect.anything()))
  expect(screen.getByText(/Se omitirán del lote/)).toHaveTextContent('Fuera de cobertura de imagen: 1')
})

it('recupera el alcance congelado al abrir un lote por enlace', async () => {
  api.get.mockImplementation(async (url:string) => {
    if (url === '/catastro-comparar/runs') return {data:{items:[]}}
    if (url === '/catastro-comparar/options') return {data:{categories,states,localities:[{value:'AA',label:'Minas',count:10}]}}
    if (url === '/catastro-comparar/runs/abc') return {data:{batch:{id:'abc',selection_filters:{category:'urbano',locality:'AA',state:'no',padron_desde:100,padron_hasta:500},processed:1,total:1,status:'COMPLETED',jobs:[]},summary:{discrepancia:1,coincide:0,sin_referencia:0,indeterminado:0,pendiente:0,total:1}}}
    throw new Error(`GET inesperado: ${url}`)
  })
  setup('/compare?lote=abc')
  await waitFor(() => expect(screen.getByLabelText('Categoría de suelo')).toHaveValue('urbano'))
  expect(screen.getByLabelText('Localidad de la comparación')).toHaveValue('AA')
  expect(screen.getByLabelText('Construcción según Catastro')).toHaveValue('no')
  expect(screen.getByLabelText('Padrón desde')).toHaveValue(100)
  expect(screen.getByLabelText('Padrón hasta')).toHaveValue(500)
  expect(screen.getAllByText('Posible discrepancia').length).toBeGreaterThan(0)
})

it('envía los filtros elegidos y el modelo al iniciar la comparación', async () => {
  api.post.mockImplementation(async (url:string) => {
    if (url === '/catastro-comparar/preview') return {data:preview}
    if (url === '/catastro-comparar/runs') return {data:{batch:{id:'nuevo',total:3}}}
    throw new Error(`POST inesperado: ${url}`)
  })
  setup()
  const user = userEvent.setup()
  await user.selectOptions(await screen.findByLabelText('Categoría de suelo'),'urbano')
  await screen.findByRole('option',{name:/Minas/})
  await user.selectOptions(screen.getByLabelText('Localidad de la comparación'),'AA')
  await user.selectOptions(screen.getByLabelText('Construcción según Catastro'),'no')
  await user.type(screen.getByLabelText('Padrón desde'),'100')
  await user.type(screen.getByLabelText('Padrón hasta'),'500')
  const button = screen.getByRole('button',{name:'Comparar selección'})
  await waitFor(() => expect(button).toBeEnabled())
  await user.click(button)
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/catastro-comparar/runs',expect.objectContaining({category:'urbano',locality:'AA',state:'no',padron_desde:100,padron_hasta:500,scene_id:'scene',model_version_id:'model',device:'cpu'}),expect.objectContaining({headers:expect.objectContaining({'Idempotency-Key':expect.any(String)})})))
})

it('espera a que la vista previa corresponda a los filtros visibles antes de habilitar Comparar', async () => {
  let finishPreview: (() => void) | undefined
  api.post.mockImplementation(async (url:string,body:{padron_desde?:number}) => {
    if (url === '/catastro-comparar/preview' && body.padron_desde === 123) {
      return await new Promise(resolve => {finishPreview = () => resolve({data:preview})})
    }
    if (url === '/catastro-comparar/preview') return {data:preview}
    throw new Error(`POST inesperado: ${url}`)
  })
  setup()
  const user = userEvent.setup()
  const button = await screen.findByRole('button',{name:'Comparar selección'})
  await waitFor(() => expect(button).toBeEnabled())
  const before = api.post.mock.calls.filter(([url]) => url === '/catastro-comparar/preview').length
  await user.type(screen.getByLabelText('Padrón desde'),'123')
  expect(button).toBeDisabled()
  expect(api.post.mock.calls.filter(([url]) => url === '/catastro-comparar/preview')).toHaveLength(before)
  await waitFor(() => expect(finishPreview).toBeDefined())
  expect(button).toBeDisabled()
  const requests = api.post.mock.calls.filter(([url]) => url === '/catastro-comparar/preview')
  expect(requests).toHaveLength(before + 1)
  expect(requests.at(-1)?.[1]).toMatchObject({padron_desde:123})
  finishPreview?.()
  await waitFor(() => expect(button).toBeEnabled())
})
