import { screen, render, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { Login } from './Login'
import api from '../../lib/axios'
vi.mock('../../lib/axios',()=>({default:{post:vi.fn(),get:vi.fn()}}))
vi.mock('./AuthProvider',()=>({useAuth:()=>({refresh:vi.fn()})}))
describe('inicio de sesión',()=>{
  beforeEach(()=>{vi.resetAllMocks();vi.mocked(api.get).mockResolvedValue({data:{id:'11111111-1111-4111-8111-111111111111',question:'3 + 4',expires_in:600}})})
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
    await user.type(await screen.findByLabelText('Resultado del captcha'),'7')
    await user.click(screen.getByRole('button',{name:'Ingresar a la plataforma'}))
    await waitFor(()=>expect(screen.getByLabelText('Código de verificación')).toBeInTheDocument())
    expect(screen.getByText('Verificá tu identidad')).toBeInTheDocument()
    expect(api.post).toHaveBeenCalledWith('/auth/login',{email:'analista@example.org',password:'Test-only-password-2026',captcha_id:'11111111-1111-4111-8111-111111111111',captcha_answer:'7'})
  })
  it('renueva el captcha tras error y conserva las credenciales',async()=>{
    vi.mocked(api.post).mockRejectedValueOnce(new Error('Captcha incorrecto o vencido.'))
    render(<Login/>);const user=userEvent.setup()
    await user.type(screen.getByLabelText('Correo electrónico'),'analista@example.org')
    await user.type(screen.getByLabelText('Contraseña'),'Test-only-password-2026')
    await user.type(await screen.findByLabelText('Resultado del captcha'),'5')
    await user.click(screen.getByRole('button',{name:'Ingresar a la plataforma'}))
    await waitFor(()=>expect(api.get).toHaveBeenCalledTimes(2))
    expect(screen.getByLabelText('Correo electrónico')).toHaveValue('analista@example.org')
    expect(screen.getByLabelText('Contraseña')).toHaveValue('Test-only-password-2026')
    expect(screen.getByLabelText('Resultado del captcha')).toHaveValue('')
  })
})
