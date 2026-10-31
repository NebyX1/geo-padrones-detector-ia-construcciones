import { can } from './AuthProvider'
describe('navegación por permisos',()=>{
  it.each(['viewer','reviewer'])('no habilita exportaciones masivas a %s',role=>expect(can(role,'export')).toBe(false))
  it('autoriza revisar sin otorgar administración al revisor',()=>{
    expect(can('reviewer','review')).toBe(true);expect(can('reviewer','users')).toBe(false)
  })
  it('autoriza análisis e importaciones al analista',()=>{
    expect(can('analyst','analyze')).toBe(true);expect(can('analyst','import')).toBe(true);expect(can('analyst','settings')).toBe(false)
  })
})
