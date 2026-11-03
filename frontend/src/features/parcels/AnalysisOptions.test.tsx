import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { Model } from '../../types'
import { AnalysisOptions } from './AnalysisOptions'
import { useAnalysisOptions } from './useAnalysisOptions'

const models: Model[] = [
  {id:'unet', model_id:'WHU-UNet++', revision:'123456789', enabled:true, sha256:'test', license:'test'},
  {id:'flair', model_id:'FLAIR-INC', revision:'abcdefgh', enabled:true, sha256:'test', license:'test'},
  {id:'disabled', model_id:'No disponible', revision:'123', enabled:false, sha256:'test', license:'test'},
]

function Controls({userId = 'user-1', available = models}: {userId?: string; available?: Model[]}) {
  const options = useAnalysisOptions(available, userId)
  return <AnalysisOptions {...options}/>
}

describe('opciones de análisis', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => cleanup())
  it('prioriza FLAIR y CPU y solo muestra modelos habilitados', () => {
    render(<Controls/>)
    expect(screen.getByLabelText('Modelo de detección')).toHaveValue('flair')
    expect(screen.getByLabelText('Procesador del análisis')).toHaveValue('cpu')
    expect(screen.queryByRole('option', {name:/No disponible/})).not.toBeInTheDocument()
  })
  it('conserva modelo y GPU para el usuario, y recupera FLAIR si el modelo se deshabilita', async () => {
    const user = userEvent.setup()
    const view = render(<Controls/>)
    await user.selectOptions(screen.getByLabelText('Modelo de detección'), 'unet')
    await user.selectOptions(screen.getByLabelText('Procesador del análisis'), 'cuda')
    view.unmount()
    const restored = render(<Controls/>)
    expect(screen.getByLabelText('Modelo de detección')).toHaveValue('unet')
    expect(screen.getByLabelText('Procesador del análisis')).toHaveValue('cuda')
    restored.rerender(<Controls available={models.filter(model => model.id !== 'unet')}/> )
    expect(screen.getByLabelText('Modelo de detección')).toHaveValue('flair')
    restored.unmount()
    render(<Controls userId="user-2"/>)
    expect(screen.getByLabelText('Procesador del análisis')).toHaveValue('cpu')
  })
})
