import { create } from 'zustand'
export const defaultFilters = {q:'',locality:'',state:'',min_area:'',max_area:'',department:'',padron_from:'',padron_to:'',min_coverage:'',min_confidence:'',min_occupancy:'',max_occupancy:'',min_buildings:'',max_buildings:'',image_from:'',image_to:'',analyzed_from:'',analyzed_to:'',model_version_id:'',batch_id:'',land_use:'',assigned_to:'',has_notes:'',review_status:'',comparison_id:'',comparison_state:''}
export type Filters = typeof defaultFilters
type MapStore = {filters: Filters; selected: string[]; active: string | null; focus: string | null; bbox: string;
  setFilter: (key: keyof Filters, value: string) => void; setBbox: (bbox: string) => void;
  select: (id: string, multiple?: boolean) => void; selectMany: (ids: string[]) => void; clear: () => void; focusParcel: (id: string) => void}
export const useMapStore = create<MapStore>((set) => ({
  filters: {...defaultFilters}, selected: [], active: null, focus: null, bbox: '',
  setFilter: (key, value) => set(s => ({filters: {...s.filters, [key]: value}})), setBbox: bbox => set({bbox}),
  select: (id, multiple = false) => set(s => ({active: id, selected: multiple ? (s.selected.includes(id) ? s.selected.filter(x => x !== id) : [...s.selected, id]) : [id]})),
  selectMany: ids => set({selected: [...new Set(ids)], active: ids[0] || null}), clear: () => set({selected: [], active: null}),
  focusParcel: id => set({focus: id, active: id, selected: [id]}),
}))
