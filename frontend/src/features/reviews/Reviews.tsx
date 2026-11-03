import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, GeoJSON, Polygon, useMapEvents } from 'react-leaflet'
import { MAP_MAX_ZOOM, STREET_NATIVE_ZOOM, ORTHO_NATIVE_ZOOM } from '../../lib/mapZoom'
import type { MultiPolygon, Polygon as PolygonType } from 'geojson'
import L from 'leaflet'
import { Check, Pencil, Info, Undo2, Trash2, RotateCcw } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../../lib/axios'
import { queryClient } from '../../lib/query-client'
import { useAuth, can } from '../auth/AuthProvider'
import { Evidence } from './Evidence'
import { Link } from 'react-router-dom'
import { useMapStore } from '../../stores/map'
import { Badge, Empty, ErrorState, Loading } from '../../components/ui/Common'
import { number, date, labels } from '../../lib/utils'
import { WorklistFilters, type ListFilters } from '../management/WorklistFilters'
import { CleanupDialog, CleanupNotice, type CleanupSelection } from '../management/CleanupDialog'
import type { Review, ParcelFeature } from '../../types'
function CorrectionDraw({onChange, reset}: {onChange:(geometry:PolygonType)=>void;reset:number}) {
  const [points,setPoints]=useState<L.LatLng[]>([])
  useMapEvents({click:e=>{const next=[...points,e.latlng];setPoints(next);if(next.length>=3)onChange({type:'Polygon',coordinates:[[...next.map(p=>[p.lng,p.lat]),[next[0].lng,next[0].lat]]]})}})
  return <Polygon key={reset} positions={points} pathOptions={{color:'#e4a23b',fillOpacity:0.35}}/>
}
type ListedReview=Review&{locality:string;model_id:string;created_at:string;device:string}
type ReviewPage={items:ListedReview[];total:number;next_offset:number|null}
export function Reviews() {
  const {user}=useAuth(),purge=can(user!.role,'purge'),shared=useMapStore(s=>s.filters)
  const [filters,setFilters]=useState<ListFilters>({status:'PENDIENTE_REVISION'}),[page,setPage]=useState({key:'',offset:0})
  const [selection,setSelection]=useState<{key:string;ids:string[]}>({key:'',ids:[]})
  const [cleanup,setCleanup]=useState<CleanupSelection|null>(null),[activeItem,setActiveItem]=useState<{key:string;review:ListedReview}|null>(null)
  const params={...filters,q:shared.q,locality:shared.locality},key=JSON.stringify(params),offset=page.key===key?page.offset:0
  const selected=selection.key===key?selection.ids:[],active=activeItem?.key===key?activeItem.review:null
  const setActive=(review:ListedReview|null)=>setActiveItem(review?{key,review}:null)
  const [decision,setDecision]=useState('CONFIRMADO'),[state,setState]=useState(''),[reason,setReason]=useState(''),[geometry,setGeometry]=useState<PolygonType|null>(null),[drawing,setDrawing]=useState(false),[reset,setReset]=useState(0),[busy,setBusy]=useState(false)
  const q=useQuery({queryKey:['reviews',params,offset],queryFn:async({signal})=>(await api.get<ReviewPage>('/reviews',{params:{...params,offset,limit:50},signal})).data,refetchInterval:5000})
  const rows=q.data?.items||[],allPage=rows.length>0&&rows.every(row=>selected.includes(row.id))
  const detail=useQuery({queryKey:['review-detail',active?.id],enabled:!!active,queryFn:async()=>(await api.get<{parcel:ParcelFeature;footprints:MultiPolygon[];evidence:{captured_at:string;scene_id:string}|null}>(`/reviews/${active!.id}`)).data})
  const choose=(review:ListedReview)=>{setActive(review);setState(review.state);setDecision('CONFIRMADO');setReason('');setGeometry(null);setDrawing(false);setReset(n=>n+1)}
  const save=async()=>{if(!active)return;setBusy(true);try{await api.patch(`/reviews/${active.id}`,{version:active.version,status:decision,state,observations:reason,geometry});toast.success('Revisión guardada con historial');setActive(null);await q.refetch();await queryClient.invalidateQueries({queryKey:['parcels']});await queryClient.invalidateQueries({queryKey:['parcel']});await queryClient.invalidateQueries({queryKey:['dashboard']});await queryClient.invalidateQueries({queryKey:['analytics']})}catch(e){toast.error((e as Error).message)}finally{setBusy(false)}}
  const toggle=(id:string)=>setSelection({key,ids:selected.includes(id)?selected.filter(value=>value!==id):[...selected,id]})
  const deleted=()=>{setActive(null);setSelection({key:'',ids:[]});setPage({key:'',offset:0})}
  return <div className="standard-page reviews-page">
    <div className="page-heading"><div><span className="eyebrow">VALIDACIÓN Y CRITERIO HUMANO</span><h1>Casos para <em>revisar.</em></h1><p>Filtrá los resultados, revisá la evidencia y eliminá los casos que no quieras conservar.</p></div>{purge&&<button className="secondary" onClick={()=>setCleanup({target:'analysis',mode:'all'})}><RotateCcw size={15}/> Empezar de cero</button>}</div>
    <WorklistFilters kind="reviews" value={filters} change={(field,value)=>setFilters(old=>({...old,[field]:value}))} reset={()=>setFilters({})}/>
    <CleanupNotice enabled={purge}/>
    <div className="surface worklist-review-toolbar"><div><strong>{number(q.data?.total||0)} {q.data?.total===1?'caso filtrado':'casos filtrados'}</strong><small>Resultados de todas las páginas</small></div>{purge&&<div className="worklist-actions"><button className="text-button danger-text" disabled={!selected.length} onClick={()=>setCleanup({target:'reviews',mode:'ids',ids:selected})}><Trash2 size={14}/> Eliminar seleccionados ({selected.length})</button><button className="secondary" disabled={!q.data?.total} onClick={()=>setCleanup({target:'reviews',mode:'filtered',filters:params})}>Eliminar filtrados</button></div>}</div>
    <div className="reviews-layout"><section className="surface review-list">
      {purge&&rows.length>0&&<div className="worklist-select-page"><label className="checkbox-label"><input type="checkbox" aria-label="Seleccionar casos de esta página" checked={allPage} onChange={()=>setSelection({key,ids:allPage?selected.filter(id=>!rows.some(row=>row.id===id)):[...new Set([...selected,...rows.map(row=>row.id)])]})}/> Seleccionar página</label>{!!selected.length&&<button className="text-button" onClick={()=>setSelection({key,ids:[]})}>Limpiar selección</button>}</div>}
      {q.isLoading?<Loading/>:q.error?<ErrorState error={q.error} retry={q.refetch}/>:!rows.length?<Empty title="No hay casos para estos filtros">Limpiá los filtros o iniciá nuevos análisis.</Empty>:rows.map(r=><article className={`review-management-row ${active?.id===r.id?'active':''}`} key={r.id}>
        {purge&&<input type="checkbox" aria-label={`Seleccionar caso ${r.padron}`} checked={selected.includes(r.id)} onChange={()=>toggle(r.id)}/>}
        <button className="review-list-item" onClick={()=>choose(r)}><div><strong>Padrón {r.padron}</strong><span>{r.locality} · {number(r.m2_huella_detectada,1)} m²</span><Badge value={r.state}/><small>{date(r.created_at)}</small></div><span className="muted">v{r.version}{r.needs_reanalysis&&<small>Nueva inferencia solicitada</small>}</span></button>
        {purge&&<button className="icon-button danger-text" aria-label={`Eliminar caso ${r.padron}`} onClick={()=>setCleanup({target:'reviews',mode:'ids',ids:[r.id]})}><Trash2 size={15}/></button>}
      </article>)}
      {!!q.data?.total&&<div className="pagination review-pagination"><button className="secondary" disabled={!offset} onClick={()=>setPage({key,offset:Math.max(0,offset-50)})}>Anterior</button><span>{offset+1}–{offset+rows.length} / {number(q.data.total)}</span><button className="secondary" disabled={q.data.next_offset==null} onClick={()=>setPage({key,offset:q.data!.next_offset!})}>Siguiente</button></div>}
    </section>
<section className="surface review-editor">{!active?<Empty title="Seleccioná un caso">Revisá la ortofoto y la huella antes de decidir.</Empty>:detail.isLoading?<Loading/>:detail.error?<ErrorState error={detail.error}/>:detail.data&&<><div className="surface-heading"><h2>Padrón {active.padron}</h2><span>Imagen: {detail.data.evidence?.captured_at||'Sin evidencia'}</span></div><div className="correction-map"><MapContainer key={active.id} maxZoom={MAP_MAX_ZOOM} bounds={L.geoJSON(detail.data.parcel).getBounds()} boundsOptions={{padding:[35,35],maxZoom:19}}><TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="© OpenStreetMap" maxZoom={MAP_MAX_ZOOM} maxNativeZoom={STREET_NATIVE_ZOOM}/>{detail.data.evidence&&<TileLayer url={`/api/v1/imagery/scenes/${detail.data.evidence.scene_id}/tiles/{z}/{x}/{y}.png`} attribution="IDE Uruguay · diciembre 2025" maxZoom={MAP_MAX_ZOOM} maxNativeZoom={ORTHO_NATIVE_ZOOM}/>}<GeoJSON data={detail.data.parcel} style={{color:'#ac8ce4',fillOpacity:0.05,weight:3}}/>{detail.data.footprints.map((geom,i)=><GeoJSON key={i} data={geom} style={{color:'#22d9a8',fillOpacity:0.35}}/>)}{drawing&&<CorrectionDraw key={reset} reset={reset} onChange={setGeometry}/>}</MapContainer></div>{can(user!.role,'review')?<div className="review-form"><div className="form-columns"><label>Decisión<select value={decision} onChange={e=>setDecision(e.target.value)}><option value="CONFIRMADO">Confirmar resultado automático</option><option value="CORREGIDO">Corregir detección</option><option value="RECHAZADO">Rechazar resultado automático</option></select></label><label>Estado revisado<select value={state} onChange={e=>setState(e.target.value)}>{['CON_CONSTRUCCION_VISIBLE','SIN_CONSTRUCCION_VISIBLE','INDETERMINADO'].map(s=><option key={s} value={s}>{labels[s]}</option>)}</select></label></div><div className="button-row"><button className="secondary" onClick={()=>{setDrawing(true);setDecision('CORREGIDO')}}><Pencil size={15}/> Dibujar huella corregida</button><button className="text-button" onClick={()=>{setGeometry(null);setReset(n=>n+1);setDrawing(false)}}><Undo2 size={14}/> Limpiar corrección</button></div>{drawing&&<p className="muted">Hacé clic para marcar los vértices de la huella; el polígono se cierra automáticamente. La superficie se recorta al padrón y se calcula en el servidor.</p>}<label>Observaciones y motivo<textarea required minLength={3} maxLength={4000} value={reason} onChange={e=>setReason(e.target.value)} placeholder="Describí qué verificaste y el motivo de tu decisión…" rows={3}/></label><button className="text-button" disabled={busy||reason.trim().length<3} onClick={()=>{void api.post(`/reviews/${active.id}/request-analysis`,{observations:reason}).then(async()=>{toast.success('Solicitud registrada para el analista');await q.refetch()}).catch(e=>toast.error(e.message))}}>Solicitar nueva inferencia con este motivo</button><button className="primary" disabled={busy||reason.trim().length<3} onClick={()=>{void save()}}><Check size={16}/>{busy?'Guardando…':'Guardar revisión'}</button></div>:<div className="notice">Tu cuenta tiene acceso de consulta a la evidencia.</div>}<Evidence key={active.id} caseId={active.id} editable={can(user!.role,'review')}/>{can(user!.role,'analyze')&&<Link className="secondary" to="/explorer" onClick={()=>useMapStore.getState().focusParcel(active.parcel_id)}>Abrir padrón para un nuevo análisis</Link>}</>}</section></div><div className="notice"><Info size={17}/><span>Eliminar un caso borra también su detección, revisiones y evidencia asociada. Empezar de cero reinicia todos los análisis de la plataforma.</span></div>
    {cleanup&&<CleanupDialog selection={cleanup} close={()=>setCleanup(null)} done={deleted}/>}
  </div>
}
