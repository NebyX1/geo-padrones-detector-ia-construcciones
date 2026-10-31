import { screen, render, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { Login } from './Login'
import api from '../../lib/axios'
vi.mock('../../lib/axios',()=>({default:{post:vi.fn()}}))
vi.mock('./AuthProvider',()=>({useAuth:()=>({refresh:vi.fn()})}))
describe('inicio de sesión',()=>{
  beforeEach(()=>vi.clearAllMocks())
  it('valida correo y no envía un formulario incompleto',async()=>{
    render(<Login/>);const user=userEvent.setup()
    await user.click(screen.getByRole('button',{name:'Ingresar a la plataforma'}))
    expect(api.post).not.toHaveBeenCalled()
  })
  it('cambia a verificación al aceptar las credenciales',async()=>{
    vi.mocked(api.post).mockResolvedValueOnce({data:{requires_2fa:true}})
    render(<Login/>);const user=userEvent.setup()
    await user.type(screen.getByLabelText('Correo electrónico'),'analista@example.org')
    await user.type(screen.getByLabelText('Contraseña'),'Test-only-password-2026')
    await user.click(screen.getByRole('button',{name:'Ingresar a la plataforma'}))
    await waitFor(()=>expect(screen.getByLabelText('Código de verificación')).toBeInTheDocument())
    expect(screen.getByText('Verificá tu identidad')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/auth/login',{email:'analista@example.org',password:'Test-only-password-2026'})
  })
})
