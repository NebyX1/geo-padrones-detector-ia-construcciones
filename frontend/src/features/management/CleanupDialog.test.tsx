import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'
import api from '../../lib/axios'
import { CleanupDialog } from './CleanupDialog'

vi.mock('../../lib/axios',()=>({default:{post:vi.fn(),get:vi.fn()}}))
vi.mock('../../lib/query-client',()=>({queryClient:{invalidateQueries:vi.fn()}}))
vi.mock('react-hot-toast',()=>({default:{success:vi.fn(),error:vi.fn()}}))

const selection={target:'reviews' as const,mode:'filtered' as const,filters:{state:'SIN_CONSTRUCCION_VISIBLE'}}
const preview={counts:{results:2,reviews:2,exports:1},fingerprint:'verified-scope',active_jobs:0,blocker_ids:[],empty:false}
function show(done=vi.fn(),close=vi.fn()) {
  const client=new QueryClient({defaultOptions:{queries:{retry:false,gcTime:0}}})
  render(<QueryClientProvider client={client}><CleanupDialog selection={selection} close={close} done={done}/></QueryClientProvider>)
  return {done,close}
}

describe('eliminar resultados',()=>{
  beforeEach(()=>vi.resetAllMocks())
  afterEach(()=>cleanup())
  it('requiere la confirmación escrita y conserva el alcance verificado',async()=>{
    vi.mocked(api.post).mockResolvedValueOnce({data:preview}).mockResolvedValueOnce({data:{pending_cleanup:0}})
    const {done,close}=show(),user=userEvent.setup()
    const button=screen.getByRole('button',{name:'Eliminar definitivamente'})
    await screen.findByText('Se invalidarán todas las exportaciones anteriores para que ningún archivo conserve resultados eliminados.')
    expect(button).toBeDisabled()
    await user.type(screen.getByLabelText('Confirmar eliminación'),'ELIMINAR')
    expect(button).toBeEnabled()
    await user.click(button)
    await waitFor(()=>expect(done).toHaveBeenCalledOnce())
    expect(close).toHaveBeenCalledOnce()
    expect(api.post).toHaveBeenCalledWith('/analysis/cleanup',{...selection,fingerprint:'verified-scope',confirmation:'ELIMINAR'})
  })
  it('bloquea el borrado mientras queden trabajos activos',async()=>{
    vi.mocked(api.post).mockResolvedValue({data:{...preview,active_jobs:1,blocker_ids:['job']}})
    show()
    await screen.findByText(/Hay un trabajo activo/)
    expect(screen.getByRole('button',{name:'Eliminar definitivamente'})).toBeDisabled()
    expect(screen.queryByLabelText('Confirmar eliminación')).not.toBeInTheDocument()
  })
})
