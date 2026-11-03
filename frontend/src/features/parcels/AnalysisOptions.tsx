import type { Model } from '../../types'
import type { AnalysisDevice } from './useAnalysisOptions'

type Props = {
  models: Model[]
  model: Model | undefined
  device: AnalysisDevice
  setModelId: (id: string) => void
  setDevice: (device: AnalysisDevice) => void
}

export function AnalysisOptions({models, model, device, setModelId, setDevice}: Props) {
  return <>
    <label>Modelo de detección
      <select aria-label="Modelo de detección" value={model?.id || ''} onChange={e => setModelId(e.target.value)} disabled={!models.length}>
        {!models.length && <option value="">No hay modelos habilitados</option>}
        {models.map(item => <option key={item.id} value={item.id}>{item.model_id} · {item.revision.slice(0, 8)}</option>)}
      </select>
    </label>
    <label>Procesador del análisis
      <select aria-label="Procesador del análisis" value={device} onChange={e => setDevice(e.target.value as AnalysisDevice)}>
        <option value="cpu">CPU</option>
        <option value="cuda">GPU NVIDIA</option>
      </select>
      <small>La GPU debe estar disponible en el servidor donde se ejecuta el análisis. La elección se recuerda en este navegador.</small>
    </label>
  </>
}
