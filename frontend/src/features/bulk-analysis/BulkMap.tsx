import { useEffect, useRef, useState } from 'react'
import { MapContainer,TileLayer,GeoJSON,Rectangle,ScaleControl,useMap,useMapEvents } from 'react-leaflet'
import { useQuery } from '@tanstack/react-query'
import L from 'leaflet'
import type { MultiPolygon } from 'geojson'
import api from '../../lib/axios'
import { ApiError } from '../../lib/axios'
import { useLocalities } from '../parcels/hooks'
import { colors,labels } from '../../lib/utils'
import { MAP_MAX_ZOOM, STREET_NATIVE_ZOOM, ORTHO_NATIVE_ZOOM } from '../../lib/mapZoom'
import type { Bounds,BulkBatch,MapData,ResultFilters } from './types'

function Viewport({change}:{change:(value:string)=>void}){
  const map=useMapEvents({moveend:()=>{const b=map.getBounds();change([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()].join(','))}})
  useEffect(()=>{const b=map.getBounds();change([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()].join(','))},[map,change])
  return null
}
function Fit({bounds}:{bounds:Bounds|null}){
  const map=useMap(),west=bounds?.[0],south=bounds?.[1],east=bounds?.[2],north=bounds?.[3]
  useEffect(()=>{if(west!=null&&south!=null&&east!=null&&north!=null)map.fitBounds([[south,west],[north,east]],{padding:[30,30],maxZoom:19})},[map,west,south,east,north])
  return null
}
function DrawRectangle({enabled,finish,cancel}:{enabled:boolean;finish:(bounds:Bounds)=>void;cancel:()=>void}){
  const anchor=useRef<L.LatLng|null>(null),press=useRef<L.LatLng|null>(null),dragged=useRef(false)
  const [draft,setDraft]=useState<L.LatLngBounds|null>(null)
  const map=useMapEvents({
    mousedown:event=>{if(enabled&&event.originalEvent.button===0){press.current=event.latlng;dragged.current=false}},
    mousemove:event=>{if(!enabled)return;const origin=anchor.current||press.current;if(!origin)return;if(press.current&&map.latLngToContainerPoint(press.current).distanceTo(map.latLngToContainerPoint(event.latlng))>=4)dragged.current=true;setDraft(L.latLngBounds(origin,event.latlng))},
    mouseup:event=>{
      if(!enabled||!press.current)return
      const first=anchor.current||press.current
      if(dragged.current||anchor.current){const b=L.latLngBounds(first,event.latlng);if(map.latLngToContainerPoint(first).distanceTo(map.latLngToContainerPoint(event.latlng))>=4){finish([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()]);anchor.current=null;setDraft(null)}}
      else anchor.current=press.current
      press.current=null;dragged.current=false
    },
  })
  useEffect(()=>{
    if(!enabled)return
    const container=map.getContainer(),dragging=map.dragging.enabled(),doubleZoom=map.doubleClickZoom.enabled()
    map.dragging.disable();map.doubleClickZoom.disable();container.classList.add('bulk-drawing')
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape')cancel()}
    const outside=(event:MouseEvent)=>{if(press.current&&!container.contains(event.target as Node))cancel()}
    window.addEventListener('keydown',escape);window.addEventListener('mouseup',outside)
    return()=>{if(dragging)map.dragging.enable();if(doubleZoom)map.doubleClickZoom.enable();container.classList.remove('bulk-drawing');window.removeEventListener('keydown',escape);window.removeEventListener('mouseup',outside);anchor.current=null;press.current=null}
  },[enabled,map,cancel])
  return enabled&&draft?<Rectangle bounds={draft} interactive={false} pathOptions={{color:'#7859ad',weight:2,dashArray:'6,4',fillOpacity:.12}}/>:null
}
function Focus({id,batchId}:{id:string|null;batchId:string|undefined}){
  const map=useMap()
  const q=useQuery({queryKey:['bulk-focus',batchId,id],enabled:!!id&&!!batchId,queryFn:async()=>(await api.get<MapData>('/parcels',{params:{format:'geojson',ids:id,bulk_id:batchId}})).data})
  useEffect(()=>{if(q.data?.features.length)map.fitBounds(L.geoJSON(q.data.features[0]).getBounds(),{padding:[60,60],maxZoom:19})},[map,q.data])
  return null
}
function Footprints({reviewId}:{reviewId:string|null}){
  const q=useQuery({queryKey:['bulk-footprints',reviewId],enabled:!!reviewId,queryFn:async()=>(await api.get<{footprints:MultiPolygon[]}>(`/reviews/${reviewId}`)).data})
  return <>{q.data?.footprints.map((geometry,i)=><GeoJSON key={`${reviewId}-${i}`} data={geometry} style={{color:'#20d9ac',weight:2,fillOpacity:.4}}/>)}</>
}
export function BulkMap({bounds,drawing,finish,cancel,batch,filters,locality,q,sceneId,focusId,reviewId}:{bounds:Bounds|null;drawing:boolean;finish:(b:Bounds)=>void;cancel:()=>void;batch:BulkBatch|undefined;filters:ResultFilters;locality:string;q:string;sceneId:string|undefined;focusId:string|null;reviewId:string|null}){
  const [bbox,setBbox]=useState(''),localities=useLocalities()
  const query=useQuery({queryKey:['bulk-map',batch?.id,bbox,filters,locality,q,batch?.processed,batch?.status],enabled:!!bbox,retry:(count,error)=>count<2&&error instanceof ApiError&&(error.status===0||error.status>=500),retryDelay:1000,refetchInterval:batch&&['QUEUED','RUNNING','CANCELLING'].includes(batch.status)?5000:false,queryFn:async({signal})=>(await api.get<MapData>('/parcels',{params:{bbox,format:'geojson',limit:1000,locality,q,...(batch?{bulk_id:batch.id,...filters}:{})},signal})).data})
  const localityBounds=localities.data?.find(item=>item.codloccat===locality)?.bbox as Bounds|undefined
  const mapBounds=bounds||localityBounds||null
  return <div className="bulk-map"><MapContainer center={[-34.3758,-55.2377]} zoom={16} maxZoom={MAP_MAX_ZOOM} bounds={mapBounds?[[mapBounds[1],mapBounds[0]],[mapBounds[3],mapBounds[2]]]:undefined} boundsOptions={{padding:[30,30],maxZoom:19}} preferCanvas><TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='© OpenStreetMap' maxZoom={MAP_MAX_ZOOM} maxNativeZoom={STREET_NATIVE_ZOOM}/>{sceneId&&<TileLayer url={`/api/v1/imagery/scenes/${sceneId}/tiles/{z}/{x}/{y}.png`} opacity={.9} updateWhenIdle updateWhenZooming={false} keepBuffer={1} attribution="Ortofoto: IDE Uruguay · Minas diciembre 2025" maxZoom={MAP_MAX_ZOOM} maxNativeZoom={ORTHO_NATIVE_ZOOM}/>}<Viewport change={setBbox}/><Fit bounds={mapBounds}/><Focus id={focusId} batchId={batch?.id}/><ScaleControl/>{query.data&&<GeoJSON key={`${batch?.id}-${query.data.features.map(f=>`${f.id}:${f.properties.state}:${f.properties.m2_huella_detectada}`).join('|')}`} data={query.data} interactive={!drawing} style={feature=>{const p=feature!.properties;return {color:p.id===focusId?'#fff':colors[p.state],fillColor:colors[p.state],fillOpacity:p.id===focusId ? .4 : .12,weight:p.id===focusId?3:1.2}}} onEachFeature={(feature,layer)=>{const text=document.createElement('span');text.textContent=`Padrón ${feature.properties.padron} · ${labels[feature.properties.state]}`;layer.bindTooltip(text,{sticky:true})}}/>}{bounds&&!drawing&&<Rectangle bounds={[[bounds[1],bounds[0]],[bounds[3],bounds[2]]]} interactive={false} pathOptions={{color:'#7859ad',weight:3,dashArray:'7,5',fillOpacity:.035}}/>}<Footprints reviewId={reviewId}/><DrawRectangle key={drawing?'drawing':'idle'} enabled={drawing} finish={finish} cancel={cancel}/></MapContainer><div className="bulk-map-caption">{drawing?'Arrastrá para dibujar un rectángulo o marcá sus dos esquinas. Esc cancela.':`${query.data?.features.length||0} contornos en vista · la selección se calcula completa en el servidor`}</div>{query.isError&&<div className="map-error" role="alert">{query.error.message} <button className="text-button" onClick={()=>void query.refetch()}>Reintentar contornos</button></div>}</div>
}
