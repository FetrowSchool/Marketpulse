import {mount} from '@vue/test-utils'
import {defineComponent} from 'vue'
import {afterEach,it,expect,vi} from 'vitest'
import {readPanelState,writePanelState,vRememberPanel} from '../src/services/panelPreferences.js'
afterEach(()=>{vi.restoreAllMocks();localStorage.clear()})
it('handles malformed and blocked storage without breaking the dashboard',()=>{
 localStorage.setItem('marketpulse:panel:v1:example','invalid')
 expect(readPanelState('example',false)).toBe(false)
 vi.spyOn(Storage.prototype,'getItem').mockImplementation(()=>{throw new Error('blocked')})
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('full')})
 expect(readPanelState('example',true)).toBe(true)
 expect(()=>writePanelState('example',false)).not.toThrow()
})
it('restores independent nested disclosure states after refresh',async()=>{
 const Host=defineComponent({directives:{rememberPanel:vRememberPanel},template:'<details v-remember-panel="\'positions\'" open><summary>Positions</summary><input></details>'})
 let wrapper=mount(Host)
 wrapper.element.open=false;await wrapper.trigger('toggle');wrapper.unmount()
 wrapper=mount(Host)
 expect(wrapper.element.open).toBe(false)
 expect(readPanelState('orders',true)).toBe(true)
 wrapper.unmount()
})
