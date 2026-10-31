import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, ChevronLeft, ChevronRight } from 'lucide-react'
import api from '../../lib/axios'
import { Badge, Loading, ErrorState } from '../../components/ui/Common'
type Row={id:string;row:number;key:{coddepto:string;codloccat:string;padron:string};issues:string[];declared_building:boolean|null;declared_m2:number|null}
export function BatchDetails({id,close}:{id:string;close:()=>void}) {
  const [offset,setOffset]=useState(0)
  const q=useQuery({queryKey:['batch-detail',id,offset],queryFn:async()=>(await api.get<{filename:string;status:string;items:Row[]}>(`/imports/${id}`,{params:{offset,limit:50}})).data})
  return <div className="modal-backdrop"><section className="modal-card advanced-filters" role="dialog" aria-modal="true" aria-label="Detalle de importación"><button className="icon-button modal-close" onClick={close} aria-label="Cerrar detalle de importación"><X size={18}/></button><h2>{q.data?.filename||'Detalle de importación'}</h2>{q.isLoading?<Loading/>:q.error?<ErrorState error={q.error}/>:<><Badge value={q.data!.status}/><div className="csv-preview"><table><thead><tr><th>Fila</th><th>Clave catastral</th><th>Declaración</th><th>Incidencias</th></tr></thead><tbody>{q.data!.items.map(r=><tr key={r.id}><td>{r.row}</td><td>{r.key.coddepto} / {r.key.codloccat} / {r.key.padron}</td><td>{r.declared_building==null?'Sin dato':r.declared_building?'Con construcción':'Sin construcción'}</td><td>{r.issues.length?r.issues.join(' · '):'Conciliado'}</td></tr>)}</tbody></table></div><div className="button-row"><button className="secondary" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}><ChevronLeft size={14}/> Anterior</button><button className="secondary" disabled={q.data!.items.length<50} onClick={()=>setOffset(offset+50)}>Siguiente <ChevronRight size={14}/></button></div></>}</section></div>
}
