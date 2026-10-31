import { useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { ArrowUpRight, CheckSquare, Square } from 'lucide-react'
import { useParcels } from './hooks'
import { useMapStore } from '../../stores/map'
import { Badge, ErrorState, Loading, Empty } from '../../components/ui/Common'
import { number } from '../../lib/utils'
export function ParcelTable() {
  const query = useParcels(), parent = useRef<HTMLDivElement>(null)
  const selected = useMapStore(s => s.selected), select = useMapStore(s => s.select), focusParcel = useMapStore(s => s.focusParcel)
  const items = query.data?.items || []
  const virtual = useVirtualizer({count: items.length, getScrollElement: () => parent.current, estimateSize: () => 43, overscan: 8})
  if (query.isLoading) return <Loading/>
  if (query.error) return <ErrorState error={query.error} retry={query.refetch}/>
  if (!items.length) return <Empty title="Sin padrones para estos filtros">Mové el mapa o ajustá los filtros de búsqueda.</Empty>
  return <div className="parcel-table"><div className="table-grid table-head"><span/><span>Padrón / localidad</span><span>Estado del análisis</span><span>Superficie parcela</span><span>Huella detectada</span><span>Cobertura</span><span/></div><div ref={parent} className="table-scroll" role="table" aria-label="Resultados catastrales"><div style={{height: virtual.getTotalSize(), position: 'relative'}}>{virtual.getVirtualItems().map(v => {const p = items[v.index]; return <div role="row" className={`table-grid table-row ${selected.includes(p.id) ? 'selected' : ''}`} key={p.id} style={{position: 'absolute', top: 0, left: 0, width: '100%', transform: `translateY(${v.start}px)`, height: v.size}}><button className="icon-button" aria-label={`Seleccionar padrón ${p.padron}`} onClick={() => select(p.id, true)}>{selected.includes(p.id) ? <CheckSquare size={16}/> : <Square size={16}/>}</button><button className="parcel-link" onClick={() => focusParcel(p.id)}><strong>{p.padron}</strong><small>{p.locality}</small></button><span><Badge value={p.state}/></span><span>{number(p.m2_parcela)} <small>m²</small></span><span>{number(p.m2_huella_detectada,1)} <small>m²</small></span><span>{p.coverage == null ? '—' : `${number(p.coverage*100)} %`}</span><button className="icon-button" aria-label={`Enfocar padrón ${p.padron}`} onClick={() => focusParcel(p.id)}><ArrowUpRight size={16}/></button></div>})}</div></div>{query.data?.next_offset != null && <small className="table-limit">Se muestran 250 resultados. Refiná la búsqueda para acotar la selección.</small>}</div>
}
