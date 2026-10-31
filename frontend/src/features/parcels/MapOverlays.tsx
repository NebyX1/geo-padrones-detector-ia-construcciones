import { useQuery } from '@tanstack/react-query'
import { ImageOverlay, GeoJSON } from 'react-leaflet'
import type { FeatureCollection } from 'geojson'
import api from '../../lib/axios'
import { useMapStore } from '../../stores/map'
export function MaskOverlay({visible,opacity}:{visible:boolean;opacity:number}) {
  const id=useMapStore(s=>s.active)
  const result=useQuery({queryKey:['mask-result',id],enabled:visible&&!!id,queryFn:async()=>(await api.get<{parcel:{properties:{result_id:string|null}}}>(`/parcels/${id}`)).data.parcel.properties.result_id})
  const mask=useQuery({queryKey:['mask-overlay',result.data],enabled:visible&&!!result.data,queryFn:async()=>(await api.get<{bounds:number[];url:string}>(`/analysis/results/${result.data}/overlay.json`)).data,retry:false})
  if(!visible||!mask.data)return null
  const b=mask.data.bounds
  return <ImageOverlay url={mask.data.url} bounds={[[b[1],b[0]],[b[3],b[2]]]} opacity={opacity}/>
}
export function LandUseOverlay({visible}:{visible:boolean}) {
  const bbox=useMapStore(s=>s.bbox)
  const q=useQuery({queryKey:['land-use-map',bbox],enabled:visible&&!!bbox,queryFn:async({signal})=>(await api.get<FeatureCollection>('/land-use/categories',{params:{format:'geojson',bbox},signal})).data})
  if(!visible||!q.data)return null
  return <GeoJSON key={bbox} data={q.data} style={{color:'#a88be2',weight:2,fillOpacity:.04,dashArray:'5,5'}} onEachFeature={(f,l)=>{const text=document.createElement('span');text.textContent=String(f.properties?.categoria||'Categoría de suelo');l.bindTooltip(text,{sticky:true})}}/>
}
