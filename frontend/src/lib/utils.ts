import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
export function cn(...inputs: ClassValue[]) { return twMerge(clsx(inputs)) }
export const number = (value: number | null | undefined, digits = 0) => value == null ? '—' : new Intl.NumberFormat('es-UY', {maximumFractionDigits: digits}).format(value)
export const date = (value: string | null | undefined) => value ? new Intl.DateTimeFormat('es-UY', {dateStyle: 'short', timeStyle: 'short', timeZone: 'America/Montevideo'}).format(new Date(value)) : '—'
export const labels: Record<string, string> = {PARTIAL:'Completado con incidencias',CANCELLING:'Cancelando',NO_ANALIZADO: 'Sin analizar', CON_CONSTRUCCION_VISIBLE: 'Construcción visible', SIN_CONSTRUCCION_VISIBLE: 'Sin construcción visible', INDETERMINADO: 'Indeterminado', ERROR_ANALISIS: 'Error de análisis',
  PENDIENTE_REVISION: 'Pendiente de revisión', CONFIRMADO: 'Confirmado', CORREGIDO: 'Corregido', RECHAZADO: 'Rechazado',
  PENDING: 'Pendiente', QUEUED: 'En cola', RUNNING: 'Procesando', COMPLETED: 'Completado', FAILED: 'Falló', CANCELLED: 'Cancelado',
  POSIBLE_CONSTRUCCION_NO_DECLARADA: 'Posible construcción no declarada', CONCORDANCIA: 'Concordancia', DIFERENCIA_DE_SUPERFICIE: 'Diferencia de superficie', CONSTRUCCION_DECLARADA_NO_VISIBLE: 'Declarada, no visible', NO_CONCILIADO: 'Sin conciliar', REVISION_REQUERIDA: 'Requiere revisión'}
export const colors: Record<string, string> = {NO_ANALIZADO: '#71849a', CON_CONSTRUCCION_VISIBLE: '#22a477', SIN_CONSTRUCCION_VISIBLE: '#4383b6', INDETERMINADO: '#e4a23b', ERROR_ANALISIS: '#dc6262'}
export const comparisonColors: Record<string, string> = {POSIBLE_CONSTRUCCION_NO_DECLARADA:'#e15868',CONCORDANCIA:'#22a477',DIFERENCIA_DE_SUPERFICIE:'#e4a23b',CONSTRUCCION_DECLARADA_NO_VISIBLE:'#b68bdb',NO_CONCILIADO:'#71849a',REVISION_REQUERIDA:'#dfaf58'}
