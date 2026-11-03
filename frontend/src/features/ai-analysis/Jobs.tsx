import { Link } from 'react-router-dom'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ScanLine, Map, XCircle, Clock, Cpu, Info, Trash2, RotateCcw } from 'lucide-react'
import api from '../../lib/axios'
import { useModels, useScenes } from '../parcels/hooks'
import { Badge, ErrorState, Loading, Empty } from '../../components/ui/Common'
import { useAuth, can } from '../auth/AuthProvider'
import { number, date } from '../../lib/utils'
import { useMapStore } from '../../stores/map'
import { WorklistFilters, type ListFilters } from '../management/WorklistFilters'
import { CleanupDialog, CleanupNotice, type CleanupSelection } from '../management/CleanupDialog'
import type { Job } from '../../types'
import toast from 'react-hot-toast'

type ListedJob=Job&{model_id?:string|null;device?:string|null}
type Page={items:ListedJob[];total:number;next_offset:number|null}

export function Jobs({history = false}: {history?: boolean}) {
  const models=useModels(),scenes=useScenes(),{user}=useAuth(),purge=can(user!.role,'purge')&&!history
  const [filters,setFilters]=useState<ListFilters>({}),[page,setPage]=useState({key:'',offset:0})
  const [selection,setSelection]=useState<{key:string;ids:string[]}>({key:'',ids:[]})
  const [cancel,setCancel]=useState<string|null>(null),[cleanup,setCleanup]=useState<CleanupSelection|null>(null)
  const shared=useMapStore(s=>s.filters),params={...filters,q:shared.q,locality:shared.locality,...(!history?{kind:'analysis'}:{})}
  const key=JSON.stringify(params),offset=page.key===key?page.offset:0,selected=selection.key===key?selection.ids:[]
  const jobs=useQuery({queryKey:['jobs-list',params,offset],queryFn:async({signal})=>(await api.get<Page>('/analysis/jobs',{params:{...params,offset,limit:50},signal})).data,refetchInterval:4000})
  const rows=jobs.data?.items||[]
  const change=(field:string,value:string)=>setFilters(old=>({...old,[field]:value}))
  const toggle=(id:string)=>setSelection({key,ids:selected.includes(id)?selected.filter(value=>value!==id):[...selected,id]})
  const allPage=rows.length>0&&rows.every(row=>selected.includes(row.id))
  const cancelJob=async()=>{try{await api.post(`/analysis/jobs/${cancel}/cancel`);toast.success('Cancelación solicitada');setCancel(null);await jobs.refetch()}catch(e){toast.error((e as Error).message)}}
  const deleted=()=>{setSelection({key:'',ids:[]});setPage({key:'',offset:0})}
  return <div className="standard-page">
    <div className="page-heading"><div><span className="eyebrow">{history?'TRAZABILIDAD OPERATIVA':'INTELIGENCIA ARTIFICIAL'}</span><h1>{history?'Historial de':'Análisis de'} <em>{history?'procesos.':'construcciones.'}</em></h1><p>Buscá trabajos, revisá su progreso y administrá los resultados de tus análisis.</p></div><div className="button-row worklist-heading-actions">{purge&&<button className="secondary" onClick={()=>setCleanup({target:'analysis',mode:'all'})}><RotateCcw size={15}/> Empezar de cero</button>}<Link className="primary" to="/explorer"><Map size={16}/> Seleccionar padrones</Link></div></div>
    {!history&&<div className="analysis-info-grid"><article className="surface model-summary"><Cpu size={23}/><div><span className="eyebrow">MODELOS DE SEGMENTACIÓN</span><h3>Modelos habilitados</h3>{models.data?.filter(model=>model.enabled).map(model=><p key={model.id}>{model.model_id} · {model.revision.slice(0,12)}</p>)}<small>El modelo y el procesador se eligen al iniciar cada análisis.</small></div></article><article className="surface model-summary"><Clock size={23}/><div><span className="eyebrow">FUENTE DE IMAGEN</span><h3>{scenes.data?.[0]?.name||'Sin escena registrada'}</h3><p>{scenes.data?.[0]?`Captura ${scenes.data[0].captured_at} · Inferencia a 20 cm`:'Se requiere cobertura oficial georreferenciada.'}</p></div></article></div>}
    <WorklistFilters kind="jobs" value={filters} change={change} reset={()=>setFilters({})}/>
    <CleanupNotice enabled={can(user!.role,'purge')}/>
    <section className="surface"><div className="surface-heading"><div><h2>{history?'Todos los procesos':'Trabajos de análisis'}</h2><span className="muted">{number(jobs.data?.total||0)} {jobs.data?.total===1?'trabajo':'trabajos'} con estos filtros</span></div>{purge&&<div className="worklist-actions"><button className="text-button danger-text" disabled={!selected.length} onClick={()=>setCleanup({target:'analysis',mode:'ids',ids:selected})}><Trash2 size={14}/> Eliminar seleccionados ({selected.length})</button><button className="secondary" disabled={!jobs.data?.total} onClick={()=>setCleanup({target:'analysis',mode:'filtered',filters:params})}>Eliminar filtrados</button></div>}</div>
    {purge&&rows.length>0&&<div className="worklist-select-page"><label className="checkbox-label"><input type="checkbox" aria-label="Seleccionar trabajos de esta página" checked={allPage} onChange={()=>setSelection({key,ids:allPage?selected.filter(id=>!rows.some(row=>row.id===id)):[...new Set([...selected,...rows.map(row=>row.id)])]})}/> Seleccionar esta página</label>{!!selected.length&&<button className="text-button" onClick={()=>setSelection({key,ids:[]})}>Limpiar selección</button>}</div>}
    {jobs.isLoading?<Loading/>:jobs.error?<ErrorState error={jobs.error} retry={jobs.refetch}/>:!rows.length?<Empty title="No hay trabajos para estos filtros">Podés limpiar los filtros o iniciar nuevos análisis desde el explorador.</Empty>:<div className="job-list">{rows.map(j=><article className="job-row" key={j.id}>
      {purge&&<input type="checkbox" aria-label={`Seleccionar trabajo ${j.id}`} checked={selected.includes(j.id)} onChange={()=>toggle(j.id)}/>}
      <span className="job-icon"><ScanLine size={19}/></span><div className="job-description"><strong>{j.kind==='analysis'?'Análisis de construcciones':j.kind==='import'?'Conciliación CSV':j.kind==='comparison'?'Comparación de declaraciones':'Exportación de resultados'}</strong><small>{date(j.created_at)} · {j.id.slice(0,8)}</small>{j.model_id&&<small>{j.model_id} · {j.device==='cuda'?'GPU NVIDIA':'CPU'}</small>}{j.error&&<p className="field-error">{j.error}</p>}</div><div className="job-progress"><div><span>{number(j.processed)} / {number(j.total)}</span><strong>{j.total?number(j.processed/j.total*100):'—'} %</strong></div><progress max={j.total||1} value={j.processed}/></div><Badge value={j.status}/>
      {can(user!.role,'analyze')&&['RUNNING','PENDING','QUEUED'].includes(j.status)&&<button className="icon-button" aria-label={`Cancelar trabajo ${j.id}`} onClick={()=>setCancel(j.id)} disabled={j.cancel_requested}><XCircle size={18}/></button>}
      {purge&&<button className="icon-button danger-text" aria-label={`Eliminar trabajo ${j.id}`} onClick={()=>setCleanup({target:'analysis',mode:'ids',ids:[j.id]})}><Trash2 size={17}/></button>}
    </article>)}</div>}
    {(jobs.data?.total||0)>0&&<div className="pagination"><button className="secondary" disabled={!offset} onClick={()=>setPage({key,offset:Math.max(0,offset-50)})}>Anterior</button><span>{offset+1}–{offset+rows.length} de {number(jobs.data?.total)}</span><button className="secondary" disabled={jobs.data?.next_offset==null} onClick={()=>setPage({key,offset:jobs.data!.next_offset!})}>Siguiente</button></div>}</section>
    <div className="notice"><Info size={17}/><span>Los resultados automáticos requieren revisión. Las eliminaciones definitivas están disponibles para administradores.</span></div>
    {cancel&&<div className="modal-backdrop"><div className="modal-card" role="dialog" aria-modal="true" aria-label="Confirmar cancelación"><h2>Cancelar proceso</h2><p>El worker se detendrá en el próximo punto seguro. Los resultados ya guardados permanecerán hasta que los elimines.</p><div className="button-row"><button className="secondary" onClick={()=>setCancel(null)}>Volver</button><button className="danger" onClick={()=>void cancelJob()}>Solicitar cancelación</button></div></div></div>}
    {cleanup&&<CleanupDialog selection={cleanup} close={()=>setCleanup(null)} done={deleted}/>}
  </div>
}
