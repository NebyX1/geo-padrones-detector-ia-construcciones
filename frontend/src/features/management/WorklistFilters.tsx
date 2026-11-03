import { Search, RotateCcw } from 'lucide-react'
import { useLocalities, useModels } from '../parcels/hooks'
import { useMapStore } from '../../stores/map'
import { labels } from '../../lib/utils'

export type ListFilters = Record<string,string>
export function WorklistFilters({kind,value,change,reset}:{kind:'jobs'|'reviews';value:ListFilters;change:(key:string,value:string)=>void;reset:()=>void}) {
  const localities=useLocalities(),models=useModels(),shared=useMapStore(s=>s.filters),setShared=useMapStore(s=>s.setFilter)
  return <section className="surface worklist-filters" aria-label="Filtros de casos">
    <label className="worklist-search"><span><Search size={13}/> Padrón o localidad</span><input aria-label="Filtrar por padrón o localidad" value={shared.q} onChange={e=>setShared('q',e.target.value)} placeholder="Buscar en toda la lista…"/></label>
    <label>Localidad<select aria-label="Filtrar localidad" value={shared.locality} onChange={e=>setShared('locality',e.target.value)}><option value="">Todas las localidades</option>{localities.data?.map(l=><option key={l.id} value={l.codloccat}>{l.name}</option>)}</select></label>
    <label>{kind==='jobs'?'Estado del trabajo':'Estado de revisión'}<select aria-label={kind==='jobs'?'Estado del trabajo':'Estado de revisión'} value={value.status||''} onChange={e=>change('status',e.target.value)}><option value="">Todos</option>{(kind==='jobs'?['PENDING','QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED']:['PENDIENTE_REVISION','CONFIRMADO','CORREGIDO','RECHAZADO']).map(s=><option key={s} value={s}>{labels[s]}</option>)}</select></label>
    <label>Modelo<select aria-label="Filtrar modelo" value={value.model_version_id||''} onChange={e=>change('model_version_id',e.target.value)}><option value="">Todos los modelos</option>{models.data?.map(m=><option key={m.id} value={m.id}>{m.model_id}</option>)}</select></label>
    {kind==='jobs'?<label>Procesador<select aria-label="Filtrar procesador" value={value.device||''} onChange={e=>change('device',e.target.value)}><option value="">CPU y GPU</option><option value="cpu">CPU</option><option value="cuda">GPU NVIDIA</option></select></label>:<>
      <label>Detección<select aria-label="Filtrar detección" value={value.state||''} onChange={e=>change('state',e.target.value)}><option value="">Todos los resultados</option>{['CON_CONSTRUCCION_VISIBLE','SIN_CONSTRUCCION_VISIBLE','INDETERMINADO','ERROR_ANALISIS'].map(s=><option key={s} value={s}>{labels[s]}</option>)}</select></label>
      <label>Huella desde (m²)<input aria-label="Filtrar huella mínima" type="number" min="0" value={value.min_area||''} onChange={e=>change('min_area',e.target.value)}/></label>
      <label>Huella hasta (m²)<input aria-label="Filtrar huella máxima" type="number" min="0" value={value.max_area||''} onChange={e=>change('max_area',e.target.value)}/></label>
    </>}
    <label>Desde<input aria-label="Fecha desde" type="date" value={value.date_from||''} onChange={e=>change('date_from',e.target.value)}/></label>
    <label>Hasta<input aria-label="Fecha hasta" type="date" value={value.date_to||''} onChange={e=>change('date_to',e.target.value)}/></label>
    <button className="text-button" onClick={()=>{reset();setShared('q','');setShared('locality','')}}><RotateCcw size={14}/> Limpiar filtros</button>
  </section>
}
