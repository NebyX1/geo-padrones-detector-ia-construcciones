import { useQuery } from '@tanstack/react-query'
import api from '../../lib/axios'
import { useMapStore } from '../../stores/map'
import type { Parcel, ParcelCollection, Locality, Scene, Model, Job, DashboardData } from '../../types'
export function useLocalities() { return useQuery({queryKey: ['localities'], queryFn: async () => (await api.get<{items: Locality[]}>('/localities')).data.items}) }
export function useScenes() { return useQuery({queryKey: ['scenes'], queryFn: async () => (await api.get<{items: Scene[]}>('/imagery/scenes')).data.items}) }
export function useModels() { return useQuery({queryKey: ['models'], queryFn: async () => (await api.get<{items: Model[]}>('/models')).data.items}) }
export function usePreferences() { return useQuery({queryKey: ['preferences'], queryFn: async () => (await api.get<{settings:{theme_colors?:Record<string,string>;default_thresholds?:Record<string,number>}}>('/preferences')).data.settings}) }
export function useJobs() { return useQuery({queryKey: ['jobs'], queryFn: async () => (await api.get<{items: Job[]}>('/analysis/jobs')).data.items, refetchInterval: 4000}) }
export function useDashboard() { const locality = useMapStore(s => s.filters.locality); return useQuery({queryKey: ['dashboard', locality], queryFn: async () => (await api.get<DashboardData>('/dashboard', {params: {locality}})).data, refetchInterval: 15000}) }
export function useParcels(geometry = false) {
  const filters = useMapStore(s => s.filters), bbox = useMapStore(s => s.bbox)
  return useQuery({queryKey: ['parcels', filters, bbox, geometry], queryFn: async ({signal}) => (await api.get<ParcelCollection & {items: Parcel[]}>('/parcels', {params: {...filters, bbox: bbox || undefined, limit: geometry ? 1000 : 250, format: geometry ? 'geojson' : undefined}, signal})).data, enabled: !geometry || Boolean(bbox)})
}
