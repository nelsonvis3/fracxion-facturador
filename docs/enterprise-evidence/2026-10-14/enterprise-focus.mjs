import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH});
const context=await browser.newContext({reducedMotion:'reduce',viewport:{width:390,height:844}});
const api='http://127.0.0.1:8001';
const csrf=await (await context.request.get(`${api}/api/auth/csrf/`)).json();
const response=await context.request.post(`${api}/api/auth/login/`,{headers:{'X-CSRFToken':csrf.csrfToken,Origin:'http://127.0.0.1:3010'},data:{email:'owner@e2e.example',password:'SyntheticE2EPassword2026!'}});
if(response.status()!==200)throw Error(`Login ${response.status()}`);
const page=await context.newPage();
await page.goto('http://127.0.0.1:3010/dashboard/00000000-0000-4000-8000-000000000001/products');
await page.waitForLoadState('networkidle');
const trigger=page.getByRole('button',{name:'Nuevo producto',exact:true});
const results=[];
async function focusState(){return page.evaluate(()=>{const e=document.activeElement;return {tag:e?.tagName,label:e?.getAttribute('aria-label')||e?.textContent?.slice(0,45),insideDialog:!!e?.closest('dialog'),trigger:e?.textContent==='Nuevo producto'};});}
for(const close of ['Escape','Cancelar','Cerrar formulario']) {
 await trigger.focus();await page.keyboard.press('Enter');
 const dialog=page.getByRole('dialog');await dialog.waitFor();
 const record={close,initial:await focusState(),tab:[],shiftTab:[]};
 for(let i=0;i<20;i++){await page.keyboard.press('Tab');record.tab.push(await focusState());}
 for(let i=0;i<20;i++){await page.keyboard.press('Shift+Tab');record.shiftTab.push(await focusState());}
 await trigger.evaluate(e=>e.focus());record.backgroundFocusAttempt=await focusState();
 if(close==='Escape')await page.keyboard.press('Escape');else await dialog.getByRole('button',{name:close,exact:true}).click();
 await dialog.waitFor({state:'detached'});
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
 record.afterClose=await focusState();
 record.returnedToTrigger=await trigger.evaluate(e=>e===document.activeElement);
 results.push(record);
}
writeFileSync('/tmp/fracxion-enterprise-audit-20261014/evidence/focus-observations.json',JSON.stringify(results,null,2)+'\n');
console.log(JSON.stringify(results.map(x=>({close:x.close,returnedToTrigger:x.returnedToTrigger,afterClose:x.afterClose,backgroundFocusAttempt:x.backgroundFocusAttempt,outsideDuringTab:[...x.tab,...x.shiftTab].filter(y=>!y.insideDialog).map(y=>y.tag)})),null,2));
await browser.close();
