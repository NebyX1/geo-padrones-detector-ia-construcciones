import { useMapStore } from './map'
describe('filtros y selección compartidos entre tabla y mapa',()=>{
  beforeEach(()=>useMapStore.getState().clear())
  it('combina filtros sin perder los anteriores',()=>{
    const store=useMapStore.getState();store.setFilter('locality','AA');store.setFilter('state','INDETERMINADO')
    expect(useMapStore.getState().filters).toMatchObject({locality:'AA',state:'INDETERMINADO'})
  })
  it('alterna selección múltiple y enfoca un único padrón desde la tabla',()=>{
    const store=useMapStore.getState();store.select('a');store.select('b',true);store.select('a',true)
    expect(useMapStore.getState().selected).toEqual(['b'])
    store.focusParcel('c');expect(useMapStore.getState()).toMatchObject({selected:['c'],active:'c',focus:'c'})
  })
  it('evita duplicados en una selección por área',()=>{
    useMapStore.getState().selectMany(['a','a','b'])
    expect(useMapStore.getState().selected).toEqual(['a','b'])
  })
})
