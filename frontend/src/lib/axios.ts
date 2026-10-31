import axios, { AxiosError } from 'axios'
export class ApiError extends Error {
  status: number
  requestId?: string
  constructor(message: string, status: number, requestId?: string) { super(message); this.status = status; this.requestId = requestId }
}
const api = axios.create({baseURL: import.meta.env.VITE_API_URL || '/api/v1', withCredentials: true, timeout: 30000})
api.interceptors.request.use(async config => {
  config.headers['X-Request-ID'] = crypto.randomUUID()
  if (!['get', 'head', 'options'].includes(config.method || 'get')) {
    const {data} = await api.get<{csrf_token: string}>('/auth/csrf')
    config.headers['X-CSRFToken'] = data.csrf_token
  }
  return config
})
api.interceptors.response.use(response => response, (error: AxiosError<{error: {message: string; request_id?: string}}>) => {
  const status = error.response?.status || 0
  if (status === 401 && !error.config?.url?.includes('/auth/')) window.dispatchEvent(new Event('session-expired'))
  return Promise.reject(new ApiError(error.response?.data?.error?.message || (status === 0 ? 'No se pudo conectar con el servidor.' : 'No se pudo completar la operación.'), status, error.response?.data?.error?.request_id))
})
export default api
