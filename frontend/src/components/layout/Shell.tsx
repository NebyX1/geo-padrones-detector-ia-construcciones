import { useState, useEffect, type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Map, Square, ScanLine, GitCompareArrows, Upload, Download, ClipboardCheck, History, Users, Settings, ChevronDown, Search, Moon, Sun, Bell, LogOut, PanelLeftClose, PanelLeftOpen, ArrowUpRight, WifiOff } from 'lucide-react'
import { Brand } from '../ui/Common'
import { useAuth, can } from '../../features/auth/AuthProvider'
import { useLocalities, useJobs } from '../../features/parcels/hooks'
import { useMapStore } from '../../stores/map'
import toast from 'react-hot-toast'
const links = [
  {to: '/dashboard', name: 'Dashboard', icon: LayoutDashboard},
  {to: '/explorer', name: 'Explorador catastral', icon: Map},
  {to: '/multi-selection', name: 'Selección múltiple', icon: Square},
  {to: '/compare', name: 'Comparar', icon: GitCompareArrows},
  {to: '/analysis', name: 'Análisis con IA', icon: ScanLine, permission: 'analyze'},
  {to: '/comparisons', name: 'Comparar declaraciones', icon: GitCompareArrows},
  {to: '/imports', name: 'Importaciones CSV', icon: Upload, permission: 'import'},
  {to: '/exports', name: 'Resultados y exportaciones', icon: Download, permission: 'export'},
  {to: '/reviews', name: 'Casos para revisar', icon: ClipboardCheck},
  {to: '/history', name: 'Historial de análisis', icon: History},
  {to: '/admin', name: 'Administración', icon: Users, permission: 'users'},
  {to: '/settings', name: 'Configuración', icon: Settings, permission: 'settings'},
]
export function Shell({children}: {children: ReactNode}) {
  const {user, logout, localPreview} = useAuth()
  const [collapsed, setCollapsed] = useState(false), [dark, setDark] = useState(localStorage.getItem('geopadrones-theme') === 'dark')
  const filters = useMapStore(s => s.filters), setFilter = useMapStore(s => s.setFilter)
  const localities = useLocalities(), jobs = useJobs()
  const [search, setSearch] = useState(filters.q)
  const [notifications, setNotifications] = useState(false)
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; localStorage.setItem('geopadrones-theme', dark ? 'dark' : 'light') }, [dark])
  const running = jobs.data?.filter(j => ['PENDING', 'QUEUED', 'RUNNING'].includes(j.status)) || []
  return <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}><aside className="sidebar"><NavLink to="/explorer" aria-label="GeoPadrones inicio"><Brand compact={collapsed}/></NavLink><div className="sidebar-rule"/>{!collapsed && <p className="nav-caption">ESPACIO DE TRABAJO</p>}<nav aria-label="Navegación principal">{links.filter(l => !l.permission || can(user!.role, l.permission)).map(l => <NavLink key={l.to} to={l.to} aria-label={l.name} title={collapsed ? l.name : undefined} className={({isActive}) => `${isActive ? 'active' : ''} ${l.to === '/admin' ? 'nav-separated' : ''}`}><l.icon size={18}/>{!collapsed && <span>{l.name}</span>}{!collapsed && l.to === '/analysis' && <span className="nav-label">IA</span>}</NavLink>)}</nav><div className="sidebar-bottom">{!collapsed && <div className="institution"><div className="institution-line"/><small>INTENDENCIA DE</small><strong>Lavalleja</strong><span>Gestión territorial informada <ArrowUpRight size={13}/></span></div>}<button className="collapse-toggle" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Expandir navegación' : 'Contraer navegación'}>{collapsed ? <PanelLeftOpen size={18}/> : <><PanelLeftClose size={18}/><span>Contraer menú</span></>}</button></div></aside>
  <div className="app-body"><header className="topbar"><div className="workspace-label">Gestión territorial<span>/</span><strong>Lavalleja</strong></div><div className="topbar-actions"><label className="locality-selector"><Map size={15}/><select aria-label="Localidad" value={filters.locality} onChange={e => setFilter('locality', e.target.value)}><option value="">Todas las localidades</option>{localities.data?.map(l => <option value={l.codloccat} key={l.id}>{l.name}</option>)}</select><ChevronDown size={13}/></label><form className="global-search" onSubmit={e => {e.preventDefault(); setFilter('q', search)}}><Search size={16}/><input aria-label="Buscar padrón" placeholder="Buscar un padrón…" value={search} onChange={e => setSearch(e.target.value)}/><kbd>↵</kbd></form><span className={`connection ${jobs.isError ? 'offline' : ''}`} title={jobs.isError ? 'Sin conexión con la API' : `${running.length} procesos activos`}>{jobs.isError ? <WifiOff size={13}/> : <i/>}<span>{jobs.isError ? 'Sin conexión' : running.length ? `${running.length} en proceso` : 'Conectado'}</span></span><button className="icon-button" onClick={() => setDark(!dark)} aria-label={dark ? 'Activar modo claro' : 'Activar modo oscuro'}>{dark ? <Sun size={18}/> : <Moon size={18}/>}</button><div className="notification-wrapper"><button className="icon-button" aria-label="Notificaciones" onClick={() => setNotifications(!notifications)}><Bell size={18}/>{running.length > 0 && <i className="notification-dot"/>}</button>{notifications && <div className="notification-popover"><strong>Actividad de procesos</strong>{running.length ? running.map(j => <p key={j.id}>{j.kind}: {j.processed}/{j.total} · {j.status}</p>) : <p>No hay procesos activos.</p>}</div>}</div><div className="topbar-divider"/><NavLink to="/account" aria-label="Mi cuenta" className="avatar" title={user!.name}>{user!.name.slice(0,2).toUpperCase()}</NavLink>{localPreview?<a className="icon-button" aria-label="Ver login protegido" href="/login"><LogOut size={17}/></a>:<button className="icon-button" aria-label="Cerrar sesión" onClick={() => {void logout().catch(e => toast.error(e.message))}}><LogOut size={17}/></button>}</div></header><main className="workspace">{localPreview&&<div className="local-preview-banner" role="status"><span><strong>Modo de prueba local</strong> · Entrada temporal sin login ni doble factor.</span><a href="/login">Ver login con captcha y 2FA</a></div>}{children}</main><footer className="app-footer"><span><i/> SISTEMA DE INFORMACIÓN TERRITORIAL</span><span>Datos IDE Uruguay · Cartografía informativa <span className="footer-dot">·</span> GeoPadrones 0.1</span></footer></div></div>
}
