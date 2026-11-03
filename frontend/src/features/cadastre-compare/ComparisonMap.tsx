import { useEffect, useState } from 'react'
import { GeoJSON, MapContainer, ScaleControl, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { useQuery } from '@tanstack/react-query'
import type { Feature, FeatureCollection, Geometry } from 'geojson'
import api from '../../lib/axios'
import { MAP_MAX_ZOOM, ORTHO_NATIVE_ZOOM, STREET_NATIVE_ZOOM } from '../../lib/mapZoom'
import { number } from '../../lib/utils'
import { outcomes } from './outcomes'

export type ComparisonProperties = {
  id: string; padron: string | number; locality: string | null; categoria_suelo: string | null;
  declared_building: boolean | null; model_state: string | null; outcome: string;
  m2_huella_detectada: number | null; coverage: number | null; error: string | null;
  result_id: string | null; parcel_id: string | null;
  tiene_registro_alfanumerico: boolean; lineas_sin_resumen: boolean;
}
type ComparisonFeature = Feature<Geometry, ComparisonProperties>
type MapData = FeatureCollection<Geometry, ComparisonProperties> & {truncated?: boolean}

function Viewport({change}: {change: (bbox: string) => void}) {
  const map = useMapEvents({moveend: () => {const b = map.getBounds(); change([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()].join(','))}})
  useEffect(() => {const b = map.getBounds(); change([b.getWest(),b.getSouth(),b.getEast(),b.getNorth()].join(','))}, [map,change])
  return null
}

function Fit({bounds}: {bounds?: number[] | null}) {
  const map = useMap()
  const key = bounds?.join(',')
  useEffect(() => {
    if (!key) return
    const b = key.split(',').map(Number)
    if (b.length === 4 && b.every(Number.isFinite)) map.fitBounds([[b[1],b[0]],[b[3],b[2]]], {padding: [30,30],maxZoom: 17})
  }, [map,key])
  return null
}

export function ComparisonMap({batchId,sceneId,bounds,outcome,processed,active,onSelect}: {
  batchId: string; sceneId?: string; bounds?: number[] | null; outcome: string; processed: number; active: boolean;
  onSelect: (properties: ComparisonProperties) => void
}) {
  const [bbox,setBbox] = useState('')
  const query = useQuery({
    queryKey: ['catastro-compare-map',batchId,bbox,outcome,processed], enabled: Boolean(batchId && bbox),
    queryFn: async ({signal}) => (await api.get<MapData>(`/catastro-comparar/runs/${batchId}/features`, {params: {bbox,...(outcome ? {outcome} : {})},signal})).data,
    refetchInterval: active ? 5000 : false,
  })
  const version = query.data?.features.map(f => `${f.id}:${f.properties.outcome}:${f.properties.model_state}`).join('|')
  return <div className="cadastre-map">
    <MapContainer center={[-34.3758,-55.2377]} zoom={12} maxZoom={MAP_MAX_ZOOM} preferCanvas>
      <TileLayer url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="© OpenStreetMap" maxZoom={MAP_MAX_ZOOM} maxNativeZoom={STREET_NATIVE_ZOOM}/>
      {sceneId && <TileLayer url={`/api/v1/imagery/scenes/${sceneId}/tiles/{z}/{x}/{y}.png`} opacity={0.88} attribution="Ortofoto: IDE Uruguay" maxZoom={MAP_MAX_ZOOM} maxNativeZoom={ORTHO_NATIVE_ZOOM}/>}
      <Viewport change={setBbox}/><Fit bounds={bounds}/><ScaleControl/>
      {query.data && <GeoJSON key={`${batchId}-${version}`} data={query.data} style={feature => {
        const p = (feature as ComparisonFeature).properties, color = outcomes[p.outcome]?.color || outcomes.pendiente.color
        return {color,fillColor:color,fillOpacity:p.outcome === 'discrepancia' ? .52 : .2,weight:p.outcome === 'discrepancia' ? 3 : 1.5}
      }} onEachFeature={(feature,layer) => {
        const p = (feature as ComparisonFeature).properties, tooltip = document.createElement('span')
        tooltip.textContent = `Padrón ${p.padron} · ${outcomes[p.outcome]?.label || 'Pendiente'}`
        layer.bindTooltip(tooltip,{sticky:true}); layer.on('click',() => onSelect(p))
      }}/>}
    </MapContainer>
    <div className="cadastre-map-caption">{!batchId ? 'El mapa mostrará los casos después de iniciar la comparación.' : <>{number(query.data?.features.length)} contornos en esta vista{query.data?.truncated ? ' · Acercá el mapa para ver todos los casos' : ''}. Hacé clic en un padrón para ver el detalle.</>}</div>
    {query.isError && <div className="map-error" role="alert">{query.error.message} <button className="text-button" onClick={() => void query.refetch()}>Reintentar</button></div>}
  </div>
}
