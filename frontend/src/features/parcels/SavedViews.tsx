import { useState } from 'react'
import { Bookmark, Trash2, X } from 'lucide-react'
import { defaultFilters, type Filters } from '../../stores/map'
import { date } from '../../lib/utils'

export type SavedView = {id:string;name:string;created:string;filters:Filters;center:[number,number];zoom:number;mode:string}
export function SavedViews({userId,current,restore,close}:{userId:string;current:Omit<SavedView,'id'|'name'|'created'>;restore:(view:SavedView)=>void;close:()=>void}) {
  const key=`geopadrones-views-${userId}`
  const [name,setName]=useState(''),[views,setViews]=useState<SavedView[]>(()=>{
    try {const stored=JSON.parse(localStorage.getItem(key)||'[]');return Array.isArray(stored)?stored.filter(v=>typeof v.id==='string'&&typeof v.name==='string'&&v.filters&&Array.isArray(v.center)&&v.center.length===2&&v.center.every(Number.isFinite)&&Number.isFinite(v.zoom)).slice(0,20):[]}catch{return []}
  })
  const persist=(next:SavedView[])=>{localStorage.setItem(key,JSON.stringify(next));setViews(next)}
  const save=()=>{if(!name.trim())return;persist([{...current,id:crypto.randomUUID(),created:new Date().toISOString(),name:name.trim().slice(0,80)},...views].slice(0,20));setName('')}
  const load=(view:SavedView)=>{
    const filters={...defaultFilters}
    for(const field of Object.keys(filters) as (keyof Filters)[]) if(typeof view.filters[field]==='string')filters[field]=view.filters[field]
    restore({...view,filters});close()
  }
  return <div className="modal-backdrop"><section role="dialog" aria-modal="true" aria-label="Vistas guardadas" className="modal-card"><button className="icon-button modal-close" aria-label="Cerrar vistas" onClick={close}><X size={18}/></button><span className="eyebrow">TU ESPACIO DE TRABAJO</span><h2>Vistas guardadas</h2><p>Conservá filtros, centro, zoom y modo temático en este navegador. Hasta 20 vistas por usuario.</p><label>Nombre de la vista<input value={name} maxLength={80} onChange={e=>setName(e.target.value)} placeholder="Ej. Minas · posibles discrepancias"/></label><button className="primary wide" onClick={save} disabled={!name.trim()}><Bookmark size={15}/> Guardar vista actual</button><div className="saved-views">{views.length===0?<p className="muted">Todavía no guardaste vistas.</p>:views.map(view=><div key={view.id}><button className="text-button" aria-label={`Restaurar vista ${view.name}`} onClick={()=>load(view)}><Bookmark size={14}/><span>{view.name}<small>{date(view.created)}</small></span></button><button className="icon-button" aria-label={`Eliminar vista ${view.name}`} onClick={()=>persist(views.filter(v=>v.id!==view.id))}><Trash2 size={15}/></button></div>)}</div></section></div>
}
