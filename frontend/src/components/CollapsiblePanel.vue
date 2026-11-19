<script setup>
import {ref} from 'vue'
import {readPanelState,writePanelState} from '../services/panelPreferences.js'
const props=defineProps({title:{type:String,required:true},subtitle:{type:String,default:''},defaultOpen:{type:Boolean,default:true},storageKey:{type:String,default:''}})
const expanded=ref(readPanelState(props.storageKey,props.defaultOpen))
function toggle(event){expanded.value=event.currentTarget.open;writePanelState(props.storageKey,expanded.value)}
</script>

<template>
  <details class="collapsible-panel" :open="expanded" @toggle="toggle">
    <summary class="panel-collapse-heading"><span class="panel-collapse-title">{{title}}<small v-if="subtitle">{{subtitle}}</small></span><span class="panel-collapse-hint" aria-hidden="true">{{expanded?'Hide':'Show'}}</span></summary>
    <div class="collapsible-content"><slot /></div>
  </details>
</template>
