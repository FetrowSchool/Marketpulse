import {mount} from '@vue/test-utils'
import {it,expect} from 'vitest'
import {defineComponent,ref} from 'vue'
import CollapsiblePanel from '../src/components/CollapsiblePanel.vue'

it('retains entered form state while hiding and reopening, including a status refresh',async()=>{
 const Host=defineComponent({components:{CollapsiblePanel},props:['subtitle'],setup(){return {draft:ref('')}},template:'<CollapsiblePanel title="Simulated account" :subtitle="subtitle"><input aria-label="Draft order" v-model="draft"></CollapsiblePanel>'})
 const wrapper=mount(Host)
 await wrapper.get('input').setValue('12')
 wrapper.element.open=false;await wrapper.trigger('toggle')
 expect(wrapper.get('summary').text()).toContain('Show')
 await wrapper.setProps({subtitle:'Cash $8,000'})
 expect(wrapper.element.open).toBe(false)
 expect(wrapper.get('input').element.value).toBe('12')
 wrapper.element.open=true;await wrapper.trigger('toggle')
 expect(wrapper.get('summary').text()).toContain('Hide')
 expect(wrapper.get('input').element.value).toBe('12')
 wrapper.unmount()
})
it('supports initially collapsed metadata without removing content',()=>{
 const wrapper=mount(CollapsiblePanel,{props:{title:'Details',defaultOpen:false},slots:{default:'<p>Recorded timestamp</p>'}})
 expect(wrapper.element.open).toBe(false)
 expect(wrapper.get('p').text()).toBe('Recorded timestamp')
 wrapper.unmount()
})
it('remembers disclosure state across remounts without using dynamic titles as keys',async()=>{
 localStorage.clear()
 let wrapper=mount(CollapsiblePanel,{props:{title:'AAPL chart',storageKey:'test-chart'}})
 wrapper.element.open=false;await wrapper.trigger('toggle');wrapper.unmount()
 wrapper=mount(CollapsiblePanel,{props:{title:'MSFT chart',storageKey:'test-chart'}})
 expect(wrapper.element.open).toBe(false)
 wrapper.element.open=true;await wrapper.trigger('toggle');wrapper.unmount()
 wrapper=mount(CollapsiblePanel,{props:{title:'AAPL chart',storageKey:'test-chart'}})
 expect(wrapper.element.open).toBe(true)
 wrapper.unmount();localStorage.clear()
})
