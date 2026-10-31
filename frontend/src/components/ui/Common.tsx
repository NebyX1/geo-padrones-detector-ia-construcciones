import { AlertCircle, LoaderCircle, Layers3, Inbox, Check } from 'lucide-react'
import type { ReactNode } from 'react'
import { labels } from '../../lib/utils'
export function Brand({compact = false}: {compact?: boolean}) { return <div className="brand"><span className="brand-symbol"><Layers3 size={23}/></span>{!compact && <span>GeoPadrones<small>LAVALLEJA · URUGUAY</small></span>}</div> }
export function Loading({text = 'Cargando información…'}: {text?: string}) { return <div className="loading-state" role="status"><LoaderCircle className="spin" size={22}/><span>{text}</span></div> }
export function ErrorState({error, retry}: {error: Error; retry?: () => void}) { return <div className="notice error" role="alert"><AlertCircle size={18}/><div><strong>No se pudo obtener la información</strong><p>{error.message}</p>{retry && <button className="text-button" onClick={retry}>Reintentar</button>}</div></div> }
export function Empty({title, children}: {title: string; children?: ReactNode}) { return <div className="empty-state"><Inbox size={32} strokeWidth={1.3}/><h3>{title}</h3><p>{children}</p></div> }
export function Badge({value}: {value: string}) { const tone = value.includes('ERROR') || value === 'FAILED' || value.includes('NO_DECLARADA') ? 'red' : value.includes('INDETERMINADO') || value.includes('PENDIENTE') || value.includes('REVISION') || value === 'QUEUED' ? 'amber' : value === 'CON_CONSTRUCCION_VISIBLE' || value === 'COMPLETED' || value === 'CONFIRMADO' || value === 'CONCORDANCIA' ? 'green' : 'neutral'; return <span className={`badge-state ${tone}`}><span/>{labels[value] || value}</span> }
export function Success({children}: {children: ReactNode}) { return <div className="notice success"><Check size={18}/>{children}</div> }
