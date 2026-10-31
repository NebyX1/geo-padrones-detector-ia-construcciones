import type { Feature, MultiPolygon } from 'geojson'
export type Role = 'superadmin' | 'admin' | 'analyst' | 'reviewer' | 'viewer'
export type User = {id: string; email: string; name: string; role: Role; is_active: boolean}
export type ParcelState = 'NO_ANALIZADO' | 'CON_CONSTRUCCION_VISIBLE' | 'SIN_CONSTRUCCION_VISIBLE' | 'INDETERMINADO' | 'ERROR_ANALISIS'
export type Parcel = {id: string; coddepto: string; codloccat: string; padron: string; locality: string; state: ParcelState; comparison_state?: string;
  m2_parcela: number; m2_huella_detectada: number | null; occupancy: number | null; coverage: number | null;
  confidence: number | null; building_count: number | null; review_id: string | null; review_status: string; result_id: string | null}
export type ParcelFeature = Feature<MultiPolygon, Parcel>
export type ParcelCollection = {type: 'FeatureCollection'; features: ParcelFeature[]; truncated: boolean; next_offset: number | null}
export type Locality = {id: string; codloccat: string; name: string; count: number; bbox: number[] | null}
export type Scene = {id: string; name: string; captured_at: string; resolution_m: number; source: string; metadata: {bounds_wgs84: number[]}}
export type Model = {id: string; model_id: string; revision: string; enabled: boolean; sha256: string; license: string}
export type Job = {id: string; kind: string; status: string; total: number; processed: number; error: string | null; created_at: string; started_at: string | null; finished_at: string | null; cancel_requested: boolean}
export type Batch = {id: string; filename: string; status: string; summary: Record<string, number>; job_id: string | null}
export type Review = {id: string; needs_reanalysis?: boolean; parcel_id: string; result_id: string; padron: string; state: ParcelState; status: string; version: number; m2_huella_detectada: number | null}
export type Comparison = {id: string; parcel_id: string | null; key: {padron: string; codloccat: string}; state: string; declared_building: boolean | null; declared_m2: number | null; difference_m2: number | null; warning: string | null}
export type DashboardData = {total_parcels: number; analyzed: number; with_buildings: number; without_buildings: number; indeterminate: number; footprint_m2: number;
  analyzed_pct: number; imports: number; discrepancies: number; pending_reviews: number; running_jobs: number; states: Record<string, number>; localities: {name: string; total: number; analyzed: number}[]; validation: string}
