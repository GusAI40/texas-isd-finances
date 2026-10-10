/* Conservative painted-data observation; not a 95/5 release certificate. */
const { chromium } = require('@playwright/test');
const { installPublicFixtures, cleanState } = require('./public-fixtures');
const fs = require('fs');
const crypto = require('crypto');
const path = require('path');
const root = path.resolve(__dirname, '../..');
function union(rs) {
 const xs = [...new Set(rs.flatMap(r=>[r.left,r.right]))].sort((a,b)=>a-b); let result=0;
 for(let i=1;i<xs.length;i++) {
  const spans=rs.filter(r=>r.left<xs[i]&&r.right>xs[i-1]).map(r=>[r.top,r.bottom]).sort((a,b)=>a[0]-b[0]);
  let sum=0,end=-Infinity;
  for(const [a,b] of spans){sum+=Math.max(0,b-Math.max(a,end));end=Math.max(end,b);}
  result+=(xs[i]-xs[i-1])*sum;
 }
 return result;
}
(async()=>{
 const { classifyPage }=await import('./measurement-core.mjs');
 const browser=await chromium.launch({headless:true});const cases=[];
 const manifest={analytic_roots:[{selector:'#welcome',required:true},{selector:'.landing-purpose',required:true},{selector:'#chatgpt-setup',required:true}],
 exclusions:[{selector:'style,script',reason:'non-rendered source'},
   {selector:'details:not([open]) > :not(summary)',reason:'closed native disclosure content is not painted'}],prose:['*'],visual_text:[],
 html_marks:[],graphic_roots:['.dallas-map']};
 for(const width of [320,390,430,1440]){
  const height=({320:740,390:844,430:932,1440:900})[width];
  const page=await browser.newPage({viewport:{width,height}});
  await page.emulateMedia({reducedMotion:'reduce'});await cleanState(page);await installPublicFixtures(page);
  await page.goto('http://127.0.0.1:8765/');await page.evaluate(()=>document.fonts.ready);
  const observation=await classifyPage(page,{...manifest,html_marks:[width<700?'.dallas-fill':'.dallas-cell']});
  const geometry=await page.evaluate(()=>{
    const box=selector=>{
      const r=document.querySelector(selector).getBoundingClientRect();
      return {top:r.top,bottom:r.bottom,width:r.width,height:r.height};
    };
    return {chart:box('.dallas-map'),source:box('.landing-caption'),primary:box('#example-dallas'),
      floating_control_visible:getComputedStyle(document.querySelector('.ta-fab')).display!=='none'};
  });
  const crop=rs=>rs.map(r=>({...r,left:Math.max(0,r.left),right:Math.min(width,r.right),top:Math.max(0,r.top),bottom:Math.min(height,r.bottom)})).filter(r=>r.right>r.left&&r.bottom>r.top);
  const score=rs=>{
   const vs=rs.filter(r=>r.kind==='visual'),ts=rs.filter(r=>r.kind==='prose');
   const intersections=vs.flatMap(v=>ts.map(t=>({left:Math.max(v.left,t.left),right:Math.min(v.right,t.right),top:Math.max(v.top,t.top),bottom:Math.min(v.bottom,t.bottom)})))
     .filter(r=>r.right>r.left&&r.bottom>r.top);
   const visual=union(vs)-union(intersections),text=union(ts);
   return{visual_area:visual,text_area:text,visual_share:visual/(visual+text)};
  };
  cases.push({width,height,geometry,initial:score(crop(observation.regions)),full:score(observation.regions),...observation});await page.close();
 }
 await browser.close();
 const record={method:'Closed welcome, product explanation, and setup summary: actual filled four-region Dallas desktop treemap or total-scaled mobile bar fills vs all visible text ranges. Headings, chart labels, buttons and instructions count as text; overlapping text is subtracted from graphic fill, so it is not double-counted. Transparent mobile card tracks, whitespace/card backgrounds and decorative outlines never count. Global masthead, following tickers/finder/report, and unopened disclosure content are outside this landing observation.',
 source_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'static/index.html'))).digest('hex'),cases};
 fs.writeFileSync(path.join(root,'docs/evidence/landing/painted-data-observation.json'),JSON.stringify(record,null,2)+'\n');
 console.log(JSON.stringify(cases.map(({width,height,geometry,initial,full})=>({width,height,geometry,initial,full})),null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
