import { render, screen } from '@testing-library/react'
import type { Job } from '../../types'
import { BulkJobErrors } from './BulkJobErrors'

function job(status: string, error: string | null): Job {
  return {id: crypto.randomUUID(), kind:'analysis', status, error, total:1, processed:0, created_at:'', started_at:null, finished_at:null, cancel_requested:false}
}

it('muestra una sola vez el error de GPU de subtareas fallidas', () => {
  const message = 'GPU NVIDIA no disponible en el procesador de análisis. Configure CUDA o seleccione CPU.'
  render(<BulkJobErrors jobs={[job('FAILED', message), job('FAILED', message), job('COMPLETED', 'No mostrar')]}/>)
  expect(screen.getByRole('alert')).toHaveTextContent('Fallaron 2 subtareas.')
  expect(screen.getAllByText(message)).toHaveLength(1)
  expect(screen.queryByText('No mostrar')).not.toBeInTheDocument()
})

it('indica cuando la API no informó el motivo', () => {
  render(<BulkJobErrors jobs={[job('FAILED', null)]}/>)
  expect(screen.getByRole('alert')).toHaveTextContent('No se informó el motivo.')
})
