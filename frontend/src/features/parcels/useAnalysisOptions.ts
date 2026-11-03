import { useState } from 'react'
import type { Model } from '../../types'

export type AnalysisDevice = 'cpu' | 'cuda'
type Preferences = {modelId: string; device: AnalysisDevice}

function readPreferences(key: string): Preferences {
  try {
    const saved = JSON.parse(localStorage.getItem(key) || '{}') as Partial<Preferences>
    return {modelId: typeof saved.modelId === 'string' ? saved.modelId : '', device: saved.device === 'cuda' ? 'cuda' : 'cpu'}
  } catch {
    return {modelId: '', device: 'cpu'}
  }
}

export function useAnalysisOptions(models: Model[] | undefined, userId: string) {
  const key = `geopadrones:analysis:${userId}`
  const [preferences, setPreferences] = useState<Preferences>(() => readPreferences(key))
  const enabled = models?.filter(model => model.enabled) || []
  const model = enabled.find(item => item.id === preferences.modelId)
    || enabled.find(item => item.model_id.toLowerCase().includes('flair-inc'))
    || enabled[0]
  const save = (next: Preferences) => {
    setPreferences(next)
    try { localStorage.setItem(key, JSON.stringify(next)) } catch { /* Selection remains valid for this visit. */ }
  }
  return {
    models: enabled, model, device: preferences.device,
    setModelId: (modelId: string) => save({...preferences, modelId}),
    setDevice: (device: AnalysisDevice) => save({...preferences, modelId: model?.id || preferences.modelId, device}),
  }
}
