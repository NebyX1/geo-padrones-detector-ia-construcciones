import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { ArrowRight, ShieldCheck, Mail, LockKeyhole, MoveUpRight, Fingerprint } from 'lucide-react'
import { motion } from 'framer-motion'
import api from '../../lib/axios'
import { useAuth } from './AuthProvider'
import { Brand } from '../../components/ui/Common'
const schema = z.object({email: z.email('Ingrese un correo válido'), password: z.string().min(1, 'Ingrese su contraseña')})
export function Login() {
  const {refresh} = useAuth()
  const [step, setStep] = useState<'login'|'code'|'forgot'|'reset'>(new URLSearchParams(window.location.search).get('reset')?'reset':'login')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [challenge, setChallenge] = useState(new URLSearchParams(window.location.search).get('reset')||'')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const {register, handleSubmit, getValues, formState: {errors}} = useForm<z.infer<typeof schema>>({resolver: zodResolver(schema)})
  const submit = async (data: z.infer<typeof schema>) => { setBusy(true); setError(''); try { await api.post('/auth/login', data); setStep('code') } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }
  const verify = async () => { setBusy(true); setError(''); try { await api.post('/auth/2fa/verify', {code}); await refresh() } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }
  const forgot = async () => { setBusy(true); setError(''); try { const {data} = await api.post('/auth/password/forgot', {email: getValues('email')}); setChallenge(data.challenge_id); setStep('reset') } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }
  const reset = async () => { setBusy(true); setError(''); try { await api.post('/auth/password/reset', {challenge_id: challenge, code, password: newPassword}); setStep('login'); setCode(''); window.history.replaceState({},'',window.location.pathname) } catch (e) { setError((e as Error).message) } finally { setBusy(false) } }
  return <main className="login-page"><section className="login-story"><Brand/><div className="contours" aria-hidden="true"><svg viewBox="0 0 800 900"><g fill="none" stroke="currentColor">{Array.from({length: 18}, (_, i) => <path key={i} d={`M ${-200+i*22} 950 C ${900-i*20} ${700-i*18}, ${-100+i*25} ${400-i*20}, ${900-i*12} ${-150+i*24}`}/>)}</g></svg></div><div className="story-copy"><span className="eyebrow light">INTELIGENCIA TERRITORIAL</span><h1>Una nueva mirada<br/>sobre <em>Lavalleja.</em></h1><p>Cartografía, imágenes aéreas e inteligencia artificial al servicio de una gestión territorial informada.</p><div className="story-chips"><span><LayersIcon/> Información georreferenciada</span><span><ShieldCheck size={15}/> Revisión humana</span></div></div><footer>Intendencia de Lavalleja<span>Plataforma de análisis catastral <MoveUpRight size={14}/></span></footer></section>
    <section className="login-form-side"><motion.div className="login-card" initial={{opacity: 0, y: 12}} animate={{opacity: 1, y: 0}}><span className="login-icon"><Fingerprint size={28}/></span><span className="eyebrow">ACCESO INSTITUCIONAL</span><h2>{step === 'code' ? 'Verificá tu identidad' : step === 'reset' ? 'Restablecé tu acceso' : step === 'forgot' ? 'Recuperá tu contraseña' : 'Bienvenido a GeoPadrones'}</h2><p>{step === 'login' ? 'Ingresá con tu cuenta autorizada para acceder al explorador territorial.' : 'Si tu cuenta está habilitada, recibirás un código de seis dígitos por correo. Vence en 10 minutos.'}</p>
    <form onSubmit={step === 'login' ? handleSubmit(submit) : e => {e.preventDefault(); void (step === 'code' ? verify() : step === 'forgot' ? forgot() : reset())}}>
      {(step === 'login' || step === 'forgot') && <label>Correo electrónico<div className="input-icon"><Mail size={17}/><input {...register('email')} type="email" placeholder="nombre@lavalleja.gub.uy" autoComplete="username" required/></div>{errors.email && <small className="field-error">{errors.email.message}</small>}</label>}
      {step === 'login' && <label>Contraseña<div className="input-icon"><LockKeyhole size={17}/><input {...register('password')} type="password" placeholder="Tu contraseña" autoComplete="current-password" required/></div>{errors.password && <small className="field-error">{errors.password.message}</small>}</label>}
      {(step === 'code' || step === 'reset') && <label>Código de verificación<input aria-label="Código de verificación" className="code-input" inputMode="numeric" pattern="[0-9]{6}" maxLength={6} value={code} onChange={e => setCode(e.target.value.replace(/\D/g,''))} autoComplete="one-time-code" autoFocus required/></label>}
      {step === 'reset' && <label>Nueva contraseña<input type="password" minLength={12} maxLength={256} autoComplete="new-password" value={newPassword} onChange={e => setNewPassword(e.target.value)} required/><small>Al menos 12 caracteres.</small></label>}
      {error && <div className="notice error" role="alert">{error}</div>}
      <button className="primary wide" disabled={busy} type="submit">{busy ? 'Procesando…' : step === 'login' ? 'Ingresar a la plataforma' : step === 'code' ? 'Verificar e ingresar' : step === 'forgot' ? 'Solicitar código' : 'Guardar contraseña'}<ArrowRight size={17}/></button>
    </form><button className="text-button recovery" onClick={() => {setStep(step === 'login' ? 'forgot' : 'login'); setError('')}}>{step === 'login' ? '¿Olvidaste tu contraseña?' : 'Volver al inicio de sesión'}</button><div className="secure-note"><ShieldCheck size={17}/><span>Acceso protegido con verificación en dos pasos.<br/>Las cuentas son administradas por la institución.</span></div></motion.div><p className="login-footnote">La cartografía es informativa y no sustituye una mensura legal.</p></section></main>
}
function LayersIcon() { return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="m3 7 9-5 9 5-9 5zM3 12l9 5 9-5M3 17l9 5 9-5"/></svg> }
