import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { Paperclip } from 'lucide-react'
import api from '../../lib/axios'
import { date } from '../../lib/utils'
export function Evidence({caseId,editable}:{caseId:string;editable:boolean}) {
  const [file,setFile]=useState<File|null>(null),[authorized,setAuthorized]=useState(false),[busy,setBusy]=useState(false)
  const q=useQuery({queryKey:['review-attachments',caseId],queryFn:async()=>(await api.get<{items:{id:string;filename:string;created_at:string}[]}>(`/reviews/${caseId}/attachments`)).data.items})
  const upload=async()=>{if(!file||!authorized)return;setBusy(true);try{const form=new FormData();form.append('file',file);form.append('authorized','true');await api.post(`/reviews/${caseId}/attachments`,form);setFile(null);setAuthorized(false);await q.refetch();toast.success('Evidencia adjunta con procedencia y hash')}catch(e){toast.error((e as Error).message)}finally{setBusy(false)}}
  return <section className="evidence-section"><h3><Paperclip size={16}/> Evidencia adjunta</h3>{q.data?.map(a=><a className="text-button" key={a.id} href={`/api/v1/reviews/${caseId}/attachments/${a.id}`}>{a.filename} · {date(a.created_at)}</a>)}{editable&&<><label>Archivo autorizado (PNG, JPEG o PDF · hasta 8 MB)<input aria-label="Adjuntar evidencia" type="file" accept="image/png,image/jpeg,application/pdf" onChange={e=>setFile(e.target.files?.[0]||null)}/></label><label className="checkbox-label"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/> Dispongo de autorización para adjuntar esta evidencia</label><button className="secondary" disabled={!file||!authorized||busy} onClick={()=>{void upload()}}><Paperclip size={14}/>{busy?'Adjuntando…':'Adjuntar archivo'}</button></>}</section>
}
