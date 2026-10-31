import { useState } from 'react'
import { X, Mail } from 'lucide-react'
import toast from 'react-hot-toast'
import api from '../../lib/axios'
import type { User } from '../../types'
export function UserEditor({user,close,refresh}:{user:User;close:()=>void;refresh:()=>Promise<unknown>}) {
  const [name,setName]=useState(user.name),[email,setEmail]=useState(user.email),[busy,setBusy]=useState(false),[confirmReset,setConfirmReset]=useState(false)
  const save=async()=>{setBusy(true);try{await api.patch(`/users/${user.id}`,{name,email});await refresh();toast.success('Datos de la cuenta actualizados');close()}catch(e){toast.error((e as Error).message)}finally{setBusy(false)}}
  const reset=async()=>{setBusy(true);try{await api.post(`/users/${user.id}/reset-access`);toast.success('Recuperación enviada y sesiones revocadas');close()}catch(e){toast.error((e as Error).message)}finally{setBusy(false)}}
  return <div className="modal-backdrop"><form className="modal-card" role="dialog" aria-modal="true" aria-label="Editar usuario" onSubmit={e=>{e.preventDefault();void save()}}><button type="button" className="icon-button modal-close" onClick={close} aria-label="Cerrar edición"><X size={18}/></button><h2>Editar cuenta</h2><label>Nombre<input value={name} onChange={e=>setName(e.target.value)} minLength={2} maxLength={120} required/></label><label>Correo<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label><button className="primary wide" disabled={busy}>Guardar datos</button><div className="layer-divider"/>{confirmReset?<><p>Se enviará una recuperación a {user.email} y se revocarán las sesiones de la cuenta.</p><div className="button-row"><button type="button" className="secondary" onClick={()=>setConfirmReset(false)}>Volver</button><button type="button" className="danger" disabled={busy} onClick={()=>{void reset()}}>Confirmar recuperación</button></div></>:<button type="button" className="text-button" disabled={!user.is_active} onClick={()=>setConfirmReset(true)}><Mail size={15}/> Enviar recuperación de acceso</button>}</form></div>
}
