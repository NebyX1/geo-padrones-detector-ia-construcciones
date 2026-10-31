import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth, can } from '../features/auth/AuthProvider'
import { Login } from '../features/auth/Login'
import { Shell } from '../components/layout/Shell'
import { Loading, Empty } from '../components/ui/Common'
const Account = lazy(() => import('../features/auth/Account').then(m => ({default:m.Account})))
const BulkAnalysis = lazy(() => import('../features/bulk-analysis/BulkAnalysis').then(m => ({default:m.BulkAnalysis})))
const Explorer = lazy(() => import('../features/parcels/Explorer').then(m => ({default:m.Explorer})))
const Dashboard = lazy(() => import('../features/dashboard/Dashboard').then(m => ({default:m.Dashboard})))
const Jobs = lazy(() => import('../features/ai-analysis/Jobs').then(m => ({default:m.Jobs})))
const Imports = lazy(() => import('../features/csv-import/Imports').then(m => ({default:m.Imports})))
const Comparisons = lazy(() => import('../features/comparisons/Comparisons').then(m => ({default:m.Comparisons})))
const Exports = lazy(() => import('../features/exports/Exports').then(m => ({default:m.Exports})))
const Reviews = lazy(() => import('../features/reviews/Reviews').then(m => ({default:m.Reviews})))
const Admin = lazy(() => import('../features/administration/Admin').then(m => ({default:m.Admin})))
const Settings = lazy(() => import('../features/administration/Settings').then(m => ({default:m.Settings})))
function Permission({capability,children}:{capability:string;children:ReactNode}) {const {user}=useAuth();return can(user!.role,capability)?children:<Empty title="Acceso restringido">Tu rol no permite realizar esta operación.</Empty>}
export default function App() {
  const {user,loading}=useAuth()
  if(loading)return <div className="boot-screen"><Loading text="Conectando con GeoPadrones…"/></div>
  if(!user||window.location.pathname==='/login')return <Login/>
  return <BrowserRouter><Shell><Suspense fallback={<Loading/>}><Routes><Route path="/" element={<Navigate to="/explorer" replace/>}/><Route path="/explorer" element={<Explorer/>}/><Route path="/multi-selection" element={<BulkAnalysis/>}/><Route path="/account" element={<Account/>}/><Route path="/dashboard" element={<Dashboard/>}/><Route path="/analysis" element={<Permission capability="analyze"><Jobs/></Permission>}/><Route path="/history" element={<Jobs history/>}/><Route path="/imports" element={<Permission capability="import"><Imports/></Permission>}/><Route path="/comparisons" element={<Comparisons/>}/><Route path="/exports" element={<Permission capability="export"><Exports/></Permission>}/><Route path="/reviews" element={<Reviews/>}/><Route path="/admin" element={<Permission capability="users"><Admin/></Permission>}/><Route path="/settings" element={<Permission capability="settings"><Settings/></Permission>}/><Route path="*" element={<Navigate to="/explorer" replace/>}/></Routes></Suspense></Shell></BrowserRouter>
}
