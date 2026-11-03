import { Info } from 'lucide-react'
import type { Job } from '../../types'

export function BulkJobErrors({jobs}: {jobs: Job[]}) {
  const failed = jobs.filter(job => job.status === 'FAILED')
  if (!failed.length) return null
  const messages = [...new Set(failed.map(job => job.error?.trim().slice(0, 300) || 'No se informó el motivo.'))]
  return <div className="notice error" role="alert">
    <Info size={17}/>
    <div><strong>{failed.length === 1 ? 'Falló una subtarea.' : `Fallaron ${failed.length} subtareas.`}</strong>
      {messages.map(message => <p key={message}>{message}</p>)}
    </div>
  </div>
}
