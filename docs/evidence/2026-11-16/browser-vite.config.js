import {defineConfig} from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({plugins:[vue(),{name:'fixture-banner',transformIndexHtml(html){return html.replace('<body>','<body><div style="padding:12px;background:#49375a;color:white;font:700 13px system-ui;text-align:center">SIMULATED BROWSER TEST FIXTURES — NO REAL MARKET DATA OR TRADES</div>')}}],server:{host:'127.0.0.1',port:5174,strictPort:true,proxy:{'/api':{target:'http://127.0.0.1:8001'},'/ws':{target:'ws://127.0.0.1:8001',ws:true}}}})
