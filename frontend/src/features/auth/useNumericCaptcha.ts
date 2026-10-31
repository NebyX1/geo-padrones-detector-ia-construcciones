import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../../lib/axios'
type Challenge={id:string;question:string;expires_in:number;expiresAt:number}
export function useNumericCaptcha(enabled:boolean) {
  const [challenge,setChallenge]=useState<Challenge|null>(null),[answer,setAnswer]=useState(''),[error,setError]=useState(''),[loading,setLoading]=useState(true)
  const request=useRef<AbortController|null>(null)
  const refresh=useCallback(async()=>{
    request.current?.abort()
    const controller=new AbortController();request.current=controller
    setLoading(true);setChallenge(null);setAnswer('');setError('')
    try {
      const {data}=await api.get<Omit<Challenge,'expiresAt'>>('/auth/captcha',{signal:controller.signal,timeout:10000})
      if(controller.signal.aborted)return
      if(!data.id||!/^\d{1,2} \+ \d{1,2}$/.test(data.question)||!Number.isFinite(data.expires_in)||data.expires_in<=0)throw new Error('Invalid challenge')
      setChallenge({...data,expiresAt:Date.now()+data.expires_in*1000})
    }catch{if(!controller.signal.aborted)setError('No se pudo cargar la verificación. Pulsá «Nueva suma» para reintentar.')}
    finally{if(!controller.signal.aborted)setLoading(false)}
  },[])
  useEffect(()=>{if(!enabled)return;const timer=window.setTimeout(()=>{void refresh()},0);return()=>{window.clearTimeout(timer);request.current?.abort()}},[enabled,refresh])
  return {challenge,answer,setAnswer,error,setError,loading,refresh}
}
