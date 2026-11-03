import type { Job, Parcel, ParcelCollection } from '../../types'
export type Bounds=[number,number,number,number]
export type BulkPreview={total:number;max_parcels:number;can_analyze:boolean;parcel_area_m2:number;chunk_count:number;unavailable_or_oversized:number;estimated_pixels:number;bounds:Bounds}
export type BulkBatch={id:string;name:string;bounds:Bounds;total:number;created_at:string;scene_id:string;model_version_id:string;parameters:Record<string,number|string>;selection_filters:{locality:string;q:string};states:Record<string,number>;processed:number;status:string;footprint_m2:number;cancel_requested:boolean;jobs:Job[]}
export type BulkRow=Parcel&{processing_status:string;selection_version_id:string;error:string|null}
export type ResultFilters={state:string;min_area:string;max_area:string;min_coverage:string;sort:string}
export const initialResultFilters:ResultFilters={state:'',min_area:'',max_area:'',min_coverage:'',sort:'footprint_desc'}
export type BulkResults={items:BulkRow[];total_filtered:number;filtered_footprint_m2:number;next_offset:number|null}
export type MapData=ParcelCollection
