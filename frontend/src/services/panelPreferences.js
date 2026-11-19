// Browser-only presentation preferences; never stores orders, prices or credentials.
const prefix='marketpulse:panel:v1:'
export function readPanelState(key,fallback=true){
 if(!key)return fallback
 try{const value=window.localStorage.getItem(prefix+key);return value==='open'?true:value==='closed'?false:fallback}catch{return fallback}
}
export function writePanelState(key,open){
 if(!key)return
 try{window.localStorage.setItem(prefix+key,open?'open':'closed')}catch{/* Storage may be blocked or full; toggling still works. */}
}
const listeners=new WeakMap()
export const vRememberPanel={
 mounted(element,{value:key}){
  if(!key)return
  element.open=readPanelState(key,element.open)
  const listener=()=>writePanelState(key,element.open)
  listeners.set(element,listener);element.addEventListener('toggle',listener)
 },
 beforeUnmount(element){const listener=listeners.get(element);if(listener)element.removeEventListener('toggle',listener);listeners.delete(element)},
}
