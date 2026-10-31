import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/axios'
import { useMapStore } from '../../stores/map'
import { number, labels } from '../../lib/utils'
import { Loading, ErrorState } from '../../components/ui/Common'
type Row={label:string;count:number}
type Data=Record<'visible_by_locality'|'footprint'|'occupancy'|'coverage'|'confidence'|'imagery'|'reviews'|'timeline'|'comparisons',Row[]>&{notice:string}
function Chart({title,rows}:{title:string;rows:Row[]}){
  const max=Math.max(1,...rows.map(r=>r.count))
  return <article className="surface analytics-chart"><h3>{title}</h3>{rows.length&&rows.some(r=>r.count)?<div>{rows.map(r=><div className="analytic-bar" key={r.label}><span>{labels[r.label]||r.label}</span><div className="bar-track"><div style={{width:`${r.count/max*100}%`}}/></div><strong>{number(r.count)}</strong></div>)}</div>:<p className="muted">Sin evidencia en este período y localidad.</p>}</article>
}
export function Analytics(){
  const [from,setFrom]=useState(''),[to,setTo]=useState(''),locality=useMapStore(s=>s.filters.locality)
  const q=useQuery({queryKey:['analytics',locality,from,to],queryFn:async({signal})=>(await api.get<Data>('/dashboard/analytics',{params:{locality,from,to},signal})).data})
  const charts:{key:keyof Omit<Data,'notice'>;title:string}[]=[{key:'visible_by_locality',title:'Construcción visible por localidad'},{key:'footprint',title:'Distribución de huellas detectadas'},{key:'occupancy',title:'Ocupación del padrón'},{key:'comparisons',title:'Declaraciones frente a IA'},{key:'timeline',title:'Resultados procesados por día'},{key:'reviews',title:'Estados de revisión'},{key:'imagery',title:'Fecha de captura de la evidencia'},{key:'coverage',title:'Cobertura válida de imagen'},{key:'confidence',title:'Probabilidad media de detecciones'}]
  return <section className="analytics-section"><div className="surface-heading"><h2>Distribuciones y evolución</h2><div className="filter-row"><label>Análisis desde (UTC)<input type="date" value={from} onChange={e=>setFrom(e.target.value)}/></label><label>Análisis hasta (UTC)<input type="date" value={to} onChange={e=>setTo(e.target.value)}/></label></div></div>{q.isLoading?<Loading/>:q.error?<ErrorState error={q.error}/>:q.data&&<><p className="muted">{q.data.notice}</p><div className="analytics-grid">{charts.map(c=><Chart key={c.key} title={c.title} rows={q.data[c.key]}/>)}</div></>}</section>
}
