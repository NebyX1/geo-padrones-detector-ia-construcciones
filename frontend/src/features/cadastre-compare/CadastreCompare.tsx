import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { GitCompareArrows, Info, MapPin, RefreshCw, XCircle } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../../lib/axios'
import { queryClient } from '../../lib/query-client'
import { date, number } from '../../lib/utils'
import { Badge, ErrorState, Loading } from '../../components/ui/Common'
import { useAuth, can } from '../auth/AuthProvider'
import { useModels, usePreferences, useScenes } from '../parcels/hooks'
import { useAnalysisOptions } from '../parcels/useAnalysisOptions'
import { AnalysisOptions } from '../parcels/AnalysisOptions'
import type { BulkBatch } from '../bulk-analysis/types'
import { BulkJobErrors } from '../bulk-analysis/BulkJobErrors'
import { ComparisonMap, type ComparisonProperties } from './ComparisonMap'
import { outcomes } from './outcomes'
import './cadastre-compare.css'

type Choice = {value: string; label: string; count: number}
type Options = {categories: Choice[]; localities: Choice[]; states: Choice[]}
type Selection = {category: string; locality: string; state: string; padron_desde: string; padron_hasta: string}
type FrozenSelection = Omit<Selection,'padron_desde'|'padron_hasta'> & {padron_desde?: number | string | null; padron_hasta?: number | string | null}
type Preview = {total: number; available: number; unavailable: number; sin_geometria: number; no_conciliados: number; fuera_cobertura: number; supera_limites: number; lineas_sin_resumen: number; can_analyze: boolean; max_parcels: number}
type Summary = {discrepancia: number; coincide: number; sin_referencia: number; indeterminado: number; pendiente: number; total: number}
type Run = {batch: BulkBatch; summary: Summary; preview?: Preview}
const selectionInitial: Selection = {category:'todos',locality:'todos',state:'todos',padron_desde:'',padron_hasta:''}
function payloadFor(selection: Selection) {
  return {category:selection.category,locality:selection.locality,state:selection.state,...(selection.padron_desde ? {padron_desde:Number(selection.padron_desde)} : {}),...(selection.padron_hasta ? {padron_hasta:Number(selection.padron_hasta)} : {})}
}
const summaryOrder = ['discrepancia','coincide','sin_referencia','indeterminado','pendiente'] as const
const stateNames: Record<string,string> = {
  CON_CONSTRUCCION_VISIBLE: 'Construcción visible', SIN_CONSTRUCCION_VISIBLE: 'Sin construcción visible',
  INDETERMINADO: 'Indeterminado', ERROR_ANALISIS: 'Error de análisis', NO_ANALIZADO: 'Pendiente',
}
function declared(value: boolean | null) {return value === true ? 'Con construcción declarada' : value === false ? 'Sin construcción declarada' : 'Sin dato definido'}

export function CadastreCompare() {
  const {user} = useAuth(), [params,setParams] = useSearchParams(), batchId = params.get('lote') || ''
  const [selection,setSelection] = useState<Selection>(selectionInitial)
  const [debouncedSelection,setDebouncedSelection] = useState<Selection>(selectionInitial)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSelection(selection),350)
    return () => window.clearTimeout(timer)
  },[selection])
  const [outcome,setOutcome] = useState(''), [selected,setSelected] = useState<ComparisonProperties | null>(null)
  const scenes = useScenes(), models = useModels(), preferences = usePreferences()
  const scene = scenes.data?.[0], analysis = useAnalysisOptions(models.data,user!.id)
  const history = useQuery({queryKey:['catastro-compare-history'],queryFn:async () => (await api.get<{items:BulkBatch[]}>('/catastro-comparar/runs')).data.items})
  const detail = useQuery({queryKey:['catastro-compare-run',batchId],enabled:!!batchId,
    queryFn:async ({signal}) => (await api.get<Run>(`/catastro-comparar/runs/${batchId}`,{signal})).data,
    refetchInterval:query => query.state.data && !['QUEUED','RUNNING','CANCELLING','PENDING'].includes(query.state.data.batch.status) ? false : 4000})
  const batch = detail.data?.batch, active = !!batch && ['QUEUED','RUNNING','CANCELLING','PENDING'].includes(batch.status)
  const frozen = batch?.selection_filters as unknown as FrozenSelection | undefined
  const shown = batchId && frozen ? {category:frozen.category || 'todos',locality:frozen.locality || 'todos',state:frozen.state || 'todos',padron_desde:frozen.padron_desde == null ? '' : String(frozen.padron_desde),padron_hasta:frozen.padron_hasta == null ? '' : String(frozen.padron_hasta)} : selection
  const rangeValid = (!selection.padron_desde || /^\d{1,9}$/.test(selection.padron_desde)) && (!selection.padron_hasta || /^\d{1,9}$/.test(selection.padron_hasta)) && (!selection.padron_desde || !selection.padron_hasta || Number(selection.padron_desde) <= Number(selection.padron_hasta))
  const filtersInSync = JSON.stringify(selection) === JSON.stringify(debouncedSelection)
  const selectionPayload = payloadFor(selection)
  const options = useQuery({queryKey:['catastro-compare-options',shown.category],
    queryFn:async ({signal}) => (await api.get<Options>('/catastro-comparar/options',{params:{category:shown.category},signal})).data})
  const preview = useQuery({queryKey:['catastro-compare-preview',debouncedSelection,scene?.id],enabled:!!scene?.id && !batchId && rangeValid && filtersInSync,
    queryFn:async ({signal}) => (await api.post<Preview>('/catastro-comparar/preview',{...payloadFor(debouncedSelection),scene_id:scene?.id},{signal})).data,
    retry:false})
  const start = useMutation({mutationFn:async () => (await api.post<Run>('/catastro-comparar/runs',{
    ...selectionPayload,scene_id:scene?.id,model_version_id:analysis.model?.id,device:analysis.device,
    probability:preferences.data?.default_thresholds?.probability ?? .5,min_area:preferences.data?.default_thresholds?.min_area ?? 8,
  },{headers:{'Idempotency-Key':crypto.randomUUID()}})).data,
    onSuccess: result => {setParams({lote:result.batch.id});setOutcome('');setSelected(null);void queryClient.invalidateQueries({queryKey:['jobs']});void history.refetch();toast.success(`Comparación de ${number(result.batch.total)} padrones iniciada`)},
    onError:error => toast.error(error.message)})
  const cancel = useMutation({mutationFn:async () => api.post(`/bulk-selections/${batchId}/cancel`),
    onSuccess:() => {void detail.refetch();toast.success('Cancelación solicitada. Se conservan los resultados procesados.')},onError:error => toast.error(error.message)})
  const reset = () => {setParams({});setSelection(selectionInitial);setOutcome('');setSelected(null)}
  const setCategory = (value: string) => {setSelection(previous => ({...previous,category:value,locality:'todos'}));setSelected(null)}

  return <div className="standard-page cadastre-compare-page">
    <div className="page-heading"><div><span className="eyebrow">CATASTRO + INTELIGENCIA ARTIFICIAL</span><h1>Comparar <em>padrones.</em></h1><p>Contrastá lo informado por Catastro con lo que se observa en la imagen.</p></div>{batchId && <button className="secondary" onClick={reset}><RefreshCw size={16}/> Nueva comparación</button>}</div>
    <div className="cadastre-history"><label>Comparaciones anteriores<select aria-label="Comparaciones anteriores" value={batchId} onChange={e => {setParams(e.target.value ? {lote:e.target.value} : {});setOutcome('');setSelected(null)}}><option value="">Nueva selección</option>{history.data?.map(item => <option key={item.id} value={item.id}>{date(item.created_at)} · {number(item.total)} padrones · {item.id.slice(0,8)}</option>)}</select></label>{history.isError && <span className="field-error">No se pudo cargar el historial. <button className="text-button" onClick={() => void history.refetch()}>Reintentar</button></span>}</div>
    <div className="cadastre-compare-layout">
      <aside className="surface cadastre-filter-panel" aria-label="Selección de casos">
        <span className="eyebrow">1 · DEFINÍ TU SELECCIÓN</span><h2>Elegí los casos</h2><p>Filtrá el archivo de Catastro antes de ejecutar el modelo.</p>
        {options.isLoading ? <Loading text="Cargando categorías y localidades…"/> : options.error ? <ErrorState error={options.error} retry={options.refetch}/> : <>
          <label>Categoría de suelo<select aria-label="Categoría de suelo" value={shown.category} disabled={!!batchId} onChange={e => setCategory(e.target.value)}>
            <option value="todos">Todas las categorías</option>{options.data?.categories.filter(c => c.value !== 'todos').map(c => <option key={c.value} value={c.value}>{c.label} · {number(c.count)}</option>)}
          </select></label>
          <label>Localidad<select aria-label="Localidad de la comparación" value={shown.locality} disabled={!!batchId || options.isFetching} onChange={e => setSelection(previous => ({...previous,locality:e.target.value}))}>
            <option value="todos">Todas las localidades</option>{options.data?.localities.filter(c => c.value !== 'todos').map(c => <option key={c.value} value={c.value}>{c.label} · {number(c.count)}</option>)}
          </select></label>
          <label>Construcción según Catastro<select aria-label="Construcción según Catastro" value={shown.state} disabled={!!batchId} onChange={e => setSelection(previous => ({...previous,state:e.target.value}))}>
            <option value="todos">Todos los estados</option>{options.data?.states.filter(c => c.value !== 'todos').map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select></label>
          <div className="cadastre-range"><label>Padrón desde<input aria-label="Padrón desde" type="number" min="0" max="999999999" step="1" value={shown.padron_desde} disabled={!!batchId} onChange={e => setSelection(previous => ({...previous,padron_desde:e.target.value}))}/></label><label>Padrón hasta<input aria-label="Padrón hasta" type="number" min="0" max="999999999" step="1" value={shown.padron_hasta} disabled={!!batchId} onChange={e => setSelection(previous => ({...previous,padron_hasta:e.target.value}))}/></label></div>
          <p className="muted">Rango opcional e inclusivo. Si hay más de 5.000 casos aptos, dividilos en rangos para comparar por partes.</p>
          {!rangeValid && !batchId && <p className="field-error">Indicá números enteros entre 0 y 999.999.999, con el valor inicial menor o igual al final.</p>}
        </>}
        {!batchId && <>
          <div className="cadastre-preview" aria-live="polite">
            {scenes.isLoading || preview.isFetching || !filtersInSync ? <Loading text="Calculando la selección…"/> : scenes.error ? <ErrorState error={scenes.error} retry={scenes.refetch}/> : preview.error ? <ErrorState error={preview.error} retry={preview.refetch}/> : !scene ? <p>No hay una fuente de imagen habilitada para analizar.</p> : preview.data ? <>
              <strong>{number(preview.data.total)} <small>casos seleccionados</small></strong>
              <p>{number(preview.data.available)} disponibles para analizar · {number(preview.data.unavailable)} no disponibles</p>
              {preview.data.unavailable > 0 && <p className="amber-text">Sin geometría: {number(preview.data.sin_geometria)} · Sin coincidencia con el catastro del sistema: {number(preview.data.no_conciliados)} · Fuera de cobertura de imagen: {number(preview.data.fuera_cobertura)} · Recorte demasiado grande: {number(preview.data.supera_limites)}. Se omitirán del lote; no se convertirán en resultados negativos.</p>}
              {preview.data.lineas_sin_resumen > 0 && <p className="amber-text">{number(preview.data.lineas_sin_resumen)} casos provienen de líneas de construcción sin resumen catastral conciliado. Su vigencia requiere verificación.</p>}
              {!preview.data.can_analyze && <p className="field-error">{preview.data.total === 0 ? 'No hay casos para estos filtros.' : preview.data.available === 0 ? 'No hay casos disponibles para analizar en esta selección.' : `Ajustá los filtros: el máximo por comparación es ${number(preview.data.max_parcels)} padrones.`}</p>}
            </> : null}
          </div>
          <div className="cadastre-model"><AnalysisOptions {...analysis}/></div>
          <p className="muted">Imagen: {scene ? `${scene.name} · ${scene.captured_at}` : 'sin fuente disponible'}. La cobertura actual corresponde al vuelo disponible de Minas; otras zonas pueden quedar indeterminadas. El trabajo se procesa en segundo plano.</p>
          {can(user!.role,'analyze') && <button className="primary wide" disabled={!rangeValid || !filtersInSync || !preview.data?.can_analyze || preview.isFetching || !scene || !analysis.model || start.isPending} onClick={() => start.mutate()}><GitCompareArrows size={16}/>{start.isPending ? 'Iniciando comparación…' : 'Comparar selección'}</button>}
          {!can(user!.role,'analyze') && <p className="muted">Tu rol permite consultar, pero no iniciar análisis.</p>}
        </>}
        {batchId && <button className="secondary wide" onClick={reset}><RefreshCw size={16}/> Elegir otra selección</button>}
        <div className="cadastre-legend"><span className="eyebrow">LEYENDA DEL MAPA</span>{summaryOrder.map(key => <div key={key}><i style={{background:outcomes[key].color}}/>{outcomes[key].label}</div>)}</div>
      </aside>
      <div className="cadastre-compare-main">
        {batchId && (detail.isLoading ? <Loading text="Cargando comparación…"/> : detail.error ? <ErrorState error={detail.error} retry={detail.refetch}/> : null)}
        {batch && <section className="surface cadastre-run-progress"><div><span className="eyebrow">LOTE DE COMPARACIÓN</span><h2>Resultado de la selección</h2><p>{number(batch.processed)} de {number(batch.total)} padrones procesados</p>{detail.data?.preview && detail.data.preview.unavailable > 0 && <p>De {number(detail.data.preview.total)} casos seleccionados, {number(detail.data.preview.unavailable)} quedaron fuera por falta de geometría o correspondencia, cobertura insuficiente o tamaño de recorte.</p>}</div><div className="cadastre-progress-value"><Badge value={batch.status}/><strong>{number(batch.total ? batch.processed / batch.total * 100 : 0,1)} %</strong><progress aria-label="Progreso de la comparación" value={batch.processed} max={batch.total || 1}/></div>{active && can(user!.role,'analyze') && <button className="text-button" disabled={batch.cancel_requested || cancel.isPending} onClick={() => cancel.mutate()}><XCircle size={16}/> Cancelar</button>}</section>}
        {batch && <BulkJobErrors jobs={batch.jobs}/>}
        {detail.data?.summary && <div className="cadastre-summary" aria-label="Filtrar resultados de comparación">{summaryOrder.map(key => <button key={key} className={`surface cadastre-summary-card ${outcome === key ? 'selected' : ''}`} onClick={() => {setOutcome(previous => previous === key ? '' : key);setSelected(null)}} aria-pressed={outcome === key}><span>{outcomes[key].label}</span><strong>{number(detail.data.summary[key])}</strong><i style={{background:outcomes[key].color}}/></button>)}</div>}
        <section className="surface cadastre-map-section"><div className="surface-heading"><div><h2>Mapa de comparación</h2><p className="muted">{outcome ? `Mostrando: ${outcomes[outcome].label}` : 'Las discrepancias aparecen destacadas en rojo.'}</p></div>{outcome && <button className="text-button" onClick={() => setOutcome('')}>Mostrar todos</button>}</div><ComparisonMap batchId={batchId} sceneId={batch?.scene_id || scene?.id} bounds={batch?.bounds} outcome={outcome} processed={batch?.processed || 0} active={active} onSelect={setSelected}/></section>
        {selected && <section className="surface cadastre-detail" aria-live="polite"><div><MapPin size={18}/><div><span className="eyebrow">DETALLE DEL PADRÓN</span><h2>Padrón {selected.padron}</h2><p>{selected.locality || 'Localidad no informada'} · {selected.categoria_suelo || 'Categoría sin definir'}</p></div></div><dl><div><dt>Catastro</dt><dd>{declared(selected.declared_building)}</dd></div><div><dt>Resultado IA</dt><dd>{stateNames[selected.model_state || ''] || selected.model_state || 'Pendiente'}</dd></div><div><dt>Comparación</dt><dd>{outcomes[selected.outcome]?.label || 'Pendiente'}</dd></div><div><dt>Huella observada</dt><dd>{selected.m2_huella_detectada == null ? '—' : `${number(selected.m2_huella_detectada,1)} m²`}</dd></div><div><dt>Cobertura de imagen</dt><dd>{selected.coverage == null ? '—' : `${number(selected.coverage * 100,1)} %`}</dd></div></dl>{!selected.tiene_registro_alfanumerico && <p className="cadastre-reference-warning">Sin resumen catastral conciliado: la referencia proviene de líneas o geometría y requiere verificar su vigencia.</p>}{selected.error && <p className="field-error">{selected.error}</p>}</section>}
      </div>
    </div>
    <div className="notice"><Info size={17}/><span>Una discrepancia es un indicio para revisar, no una conclusión automática. Los casos sin declaración, sin imagen o con resultado dudoso se mantienen separados. La categoría territorial es una referencia espacial y puede diferir del ámbito catastral.</span></div>
  </div>
}
