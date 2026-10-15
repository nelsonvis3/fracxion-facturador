import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
const evidence='/tmp/fracxion-enterprise-audit-20261014/evidence';
mkdirSync(`${evidence}/screenshots`,{recursive:true});
const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH});
const context=await browser.newContext({reducedMotion:'reduce',viewport:{width:1440,height:1000}});
const api='http://127.0.0.1:8001';
const csrf=await context.request.get(`${api}/api/auth/csrf/`);
const login=await context.request.post(`${api}/api/auth/login/`,{headers:{'X-CSRFToken':(await csrf.json()).csrfToken,Origin:'http://127.0.0.1:3010'},data:{email:'owner@e2e.example',password:'SyntheticE2EPassword2026!'}});
if(login.status()!==200) throw Error(`login: ${login.status()} ${await login.text()}`);
const page=await context.newPage();
const result={viewports:[],keyboard:{},pageErrors:[],responses5xx:[],accessibility:[]};
page.on('pageerror',e=>result.pageErrors.push(e.message));
page.on('response',r=>{if(r.status()>=500)result.responses5xx.push({status:r.status(),path:new URL(r.url()).pathname});});
const base='/dashboard/00000000-0000-4000-8000-000000000001';
for(const width of [1440,768,390]) {
 await page.setViewportSize({width,height:1000});
 for(const route of ['', '/customers','/products','/invoices','/invoices/new','/payments','/audit']) {
  await page.goto(`http://127.0.0.1:3010${base}${route}`);
  await page.locator('h1:visible').waitFor();
  await page.waitForLoadState('networkidle');
  const overflow=await page.evaluate(()=>({document:document.documentElement.scrollWidth,viewport:innerWidth}));
  result.viewports.push({width,route:route||'overview',...overflow,ok:overflow.document<=width+1});
  if(width===390 || route==='/invoices') await page.screenshot({path:`${evidence}/screenshots/${width}-${route.replaceAll('/','-')||'overview'}.png`,fullPage:true});
  if(width===1440) {
   await page.addScriptTag({path:'node_modules/axe-core/axe.min.js'});
   const axe=await page.evaluate(async()=>window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}}));
   result.accessibility.push({route:route||'overview',violations:axe.violations.map(v=>({id:v.id,impact:v.impact,description:v.description,helpUrl:v.helpUrl,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:axe.incomplete.map(v=>v.id)});
  }
 }
}
await page.goto(`http://127.0.0.1:3010${base}/products`);
const trigger=page.getByRole('button',{name:'Nuevo producto',exact:true});
await trigger.focus();
await page.keyboard.press('Enter');
const dialog=page.getByRole('dialog');
await dialog.waitFor();
result.keyboard.modalOpensWithEnter=await dialog.isVisible();
result.keyboard.focusInitiallyInside=await dialog.evaluate(d=>d.contains(document.activeElement));
let contained=true;
for(let n=0;n<24;n++) {await page.keyboard.press('Tab');contained=contained&&await dialog.evaluate(d=>d.contains(document.activeElement));}
result.keyboard.tabFocusContained=contained;
await page.addScriptTag({path:'node_modules/axe-core/axe.min.js'});
const modalAxe=await page.evaluate(async()=>window.axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}}));
result.accessibility.push({route:'products/modal-mobile',violations:modalAxe.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:modalAxe.incomplete.map(v=>v.id)});
await page.screenshot({path:`${evidence}/screenshots/390-product-modal.png`,fullPage:true});
await page.keyboard.press('Escape');
result.keyboard.escapeCloses=(await dialog.count())===0;
result.keyboard.focusReturnsToTrigger=await trigger.evaluate(e=>document.activeElement===e);
writeFileSync(`${evidence}/browser-observations.json`,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({viewportChecks:result.viewports.length,overflow:result.viewports.filter(x=>!x.ok),keyboard:result.keyboard,pageErrors:result.pageErrors,responses5xx:result.responses5xx,violations:result.accessibility.map(x=>({route:x.route,violations:x.violations.map(v=>v.id)}))},null,2));
await browser.close();
