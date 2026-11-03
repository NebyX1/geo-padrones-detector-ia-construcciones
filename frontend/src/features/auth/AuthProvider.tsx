import { createContext, useContext, useEffect, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import api from '../../lib/axios'
import { queryClient } from '../../lib/query-client'
import type { User } from '../../types'
type Context = {user: User | null; loading: boolean; localPreview:boolean; refresh: () => Promise<unknown>; logout: () => Promise<void>}
const AuthContext = createContext<Context | null>(null)
export function AuthProvider({children}: {children: ReactNode}) {
  const query = useQuery({queryKey: ['session'], queryFn: async () => (await api.get<{user: User}>('/auth/me')).data.user, retry: false})
  useEffect(() => { const expire = () => { queryClient.setQueryData(['session'], null) }; window.addEventListener('session-expired', expire); return () => window.removeEventListener('session-expired', expire) }, [])
  const logout = async () => { await api.post('/auth/logout'); queryClient.clear(); queryClient.setQueryData(['session'], null) }
  return <AuthContext.Provider value={{user: query.data || null, loading: query.isLoading, localPreview:!!query.data?.is_local_preview, refresh: query.refetch, logout}}>{children}</AuthContext.Provider>
}
// Context hook follows the sample's custom-hook organization.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() { const ctx = useContext(AuthContext); if (!ctx) throw new Error('AuthProvider ausente'); return ctx }
// eslint-disable-next-line react-refresh/only-export-components
export function can(role: string, permission: string) {
  const caps: Record<string, string[]> = {superadmin: ['analyze','import','export','review','users','settings','purge'], admin: ['analyze','import','export','review','users','purge'], analyst: ['analyze','import','export'], reviewer: ['review'], viewer: []}
  return caps[role]?.includes(permission) || false
}
