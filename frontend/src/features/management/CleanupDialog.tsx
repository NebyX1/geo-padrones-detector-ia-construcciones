import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, X } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../../lib/axios'
import { queryClient } from '../../lib/query-client'
import { Loading, ErrorState } from '../../components/ui/Common'
import { number } from '../../lib/utils'

export type CleanupSelection = {target:'analysis'|'reviews';mode:'ids'|'filtered'|'all';ids?:string[];filters?:Record<string,string>}
type Preview = {counts:Record<string,number>;fingerprint:string;active_jobs:number;blocker_ids:string[];empty:boolean}
const names:Record<string,string> = {analyses:'Trabajos eliminados',results:'Resultados de IA',reviews:'Casos de revisión',review_actions:'Revisiones guardadas',attachments:'Adjuntos',comparison_runs:'Comparaciones vinculadas',exports:'Exportaciones anteriores',batches:'Lotes afectados',audit_records:'Registros de actividad vinculados'}

export function CleanupDialog({selection,close,done}:{selection:CleanupSelection;close:()=>void;done:()=>void}) {
  const [confirmation,setConfirmation]=useState(''),[busy,setBusy]=useState(false),[cancelling,setCancelling]=useState(false)
  const preview=useQuery({queryKey:['cleanup-preview',selection],queryFn:async({signal})=>(await api.post<Preview>('/analysis/cleanup/preview',selection,{signal})).data,retry:false,staleTime:0,refetchOnMount:'always',refetchInterval:q=>q.state.data?.active_jobs?4000:false})
  const remove=async()=>{
    if(!preview.data)return
    setBusy(true)
    try {
      const {data}=await api.post<{pending_cleanup:number}>('/analysis/cleanup',{...selection,fingerprint:preview.data.fingerprint,confirmation})
      toast.success(data.pending_cleanup?'Registros eliminados. La limpieza de archivos continúa en segundo plano.':'Registros y archivos eliminados.')
      await queryClient.invalidateQueries()
      done();close()
    } catch(e) {toast.error((e as Error).message);setConfirmation('');void preview.refetch()}
    finally {setBusy(false)}
  }
  const cancelActive=async()=>{
    setCancelling(true)
    try {
      const ids=preview.data?.blocker_ids||[],attempts:PromiseSettledResult<unknown>[]=[]
      for(let index=0;index<ids.length;index+=5) attempts.push(...await Promise.allSettled(ids.slice(index,index+5).map(id=>api.post(`/analysis/jobs/${id}/cancel`))))
      if(attempts.some(result=>result.status==='rejected')) toast.error('Algunos trabajos ya terminaron o no pudieron cancelarse; se actualizará la lista.')
      else toast.success('Cancelación solicitada. Esperá a que los trabajos terminen para eliminar.')
      void preview.refetch()
    } catch(e) {toast.error((e as Error).message)}
    finally {setCancelling(false)}
  }
  return <div className="modal-backdrop"><section className="modal-card cleanup-dialog" role="dialog" aria-modal="true" aria-labelledby="cleanup-title">
    <button className="modal-close icon-button" aria-label="Cerrar eliminación" disabled={busy} onClick={close}><X size={18}/></button>
    <AlertTriangle size={25}/><span className="eyebrow">ELIMINACIÓN DEFINITIVA</span>
    <h2 id="cleanup-title">{selection.mode==='all'&&selection.target==='analysis'?'Empezar de cero':'Eliminar casos y resultados'}</h2>
    <p>{selection.mode==='ids'?'Se eliminarán los registros seleccionados y sus datos relacionados.':selection.mode==='filtered'?'Se eliminarán todos los registros que coinciden con los filtros, incluidas las demás páginas.':'Se eliminarán todos los análisis y sus datos relacionados de la plataforma.'}</p>
    {preview.isFetching?<Loading text="Comprobando el alcance…"/>:preview.error?<ErrorState error={preview.error} retry={preview.refetch}/>:preview.data&&<>
      <dl className="cleanup-counts">{Object.entries(preview.data.counts).filter(([,count])=>count>0).map(([key,count])=><div key={key}><dt>{names[key]||key}</dt><dd>{number(count)}</dd></div>)}</dl>
      {preview.data.empty?<p>No hay registros para eliminar.</p>:<>
        <p>Se borran también las máscaras, huellas, observaciones y adjuntos asociados. Los padrones, las fuentes de datos y los modelos quedan disponibles para nuevos análisis.</p>
        {!!preview.data.counts.exports&&<p className="field-error">Se invalidarán todas las exportaciones anteriores para que ningún archivo conserve resultados eliminados.</p>}
        {preview.data.active_jobs>0?<div className="notice error"><div><p>{preview.data.active_jobs===1?'Hay un trabajo activo que puede generar o utilizar estos resultados. Primero debe terminar o cancelarse.':`Hay ${number(preview.data.active_jobs)} trabajos activos que pueden generar o utilizar estos resultados. Primero deben terminar o cancelarse.`}</p><button className="secondary" disabled={cancelling} onClick={()=>void cancelActive()}>{cancelling?'Solicitando…':'Cancelar trabajos activos'}</button></div></div>:<label>Escribí ELIMINAR para confirmar<input aria-label="Confirmar eliminación" value={confirmation} onChange={e=>setConfirmation(e.target.value)} autoComplete="off" placeholder="ELIMINAR"/></label>}
      </>}
    </>}
    <div className="button-row"><button className="secondary" onClick={close} disabled={busy}>Volver</button><button className="danger" disabled={busy||preview.isFetching||!preview.data||preview.data.empty||preview.data.active_jobs>0||confirmation!=='ELIMINAR'} onClick={()=>void remove()}>{busy?'Eliminando…':'Eliminar definitivamente'}</button></div>
  </section></div>
}

export function CleanupNotice({enabled}:{enabled:boolean}) {
  const query=useQuery({queryKey:['cleanup-status'],enabled,queryFn:async()=>(await api.get<{pending_cleanup:number}>('/analysis/cleanup/status')).data,refetchInterval:q=>q.state.data?.pending_cleanup?4000:false})
  return query.data?.pending_cleanup?<div className="notice">Limpieza de archivos en segundo plano: {number(query.data.pending_cleanup)} elementos pendientes. Los registros ya se eliminaron.</div>:null
}
