"""Shared look and small chart helpers for every tool page. No external libraries or fonts."""

CSS = r"""
:root{--bg:#f4f1fa;--card:#fff;--ink:#1c1530;--muted:#6b6385;--line:#e8e3f3;--brand:#5b21b6;--brand2:#7c3aed;
--accent:#0ea5e9;--good:#059669;--bad:#dc2626;--warn:#d97706;--shadow:0 1px 2px #1c15300d,0 8px 24px #1c15300f}
@media (prefers-color-scheme:dark){:root{--bg:#120e1f;--card:#1b1530;--ink:#f1edfb;--muted:#a79fc4;--line:#2d2548;
--brand:#a78bfa;--brand2:#8b5cf6;--shadow:0 1px 2px #0006,0 8px 24px #0004}}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink);
background-image:radial-gradient(900px 300px at 85% -50px,#7c3aed26,transparent),radial-gradient(700px 260px at 0 -40px,#0ea5e91f,transparent);
background-repeat:no-repeat}
header{background:linear-gradient(120deg,#3b0f8c,#5b21b6 55%,#7c3aed);color:#fff;padding:22px 28px 26px;position:relative;overflow:hidden}
header:after{content:"";position:absolute;right:-60px;top:-80px;width:260px;height:260px;border-radius:50%;background:#ffffff14}
header .row{max-width:1040px;margin:0 auto;display:flex;align-items:center;gap:14px;position:relative;z-index:1}
.logo{width:42px;height:42px;border-radius:12px;background:#ffffff24;display:grid;place-items:center;font-size:22px}
header h1{margin:0;font-size:22px;letter-spacing:-.2px}header p{margin:2px 0 0;opacity:.85;font-size:13px}
#back{margin-left:auto;color:#fff;text-decoration:none;font-size:13px;background:#ffffff22;padding:7px 12px;border-radius:20px;display:none}
main{max-width:1040px;margin:-14px auto 40px;padding:0 20px;position:relative;z-index:2}
.card{background:var(--card);border-radius:16px;padding:20px 22px;margin-bottom:16px;box-shadow:var(--shadow);border:1px solid var(--line)}
.card h2,.card h3{margin:0 0 12px;font-size:16px}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end}
.controls>div{display:flex;flex-direction:column;gap:4px}
label{font-size:12px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
input,select{font:inherit;padding:9px 12px;border:1px solid var(--line);border-radius:10px;background:var(--card);color:var(--ink);min-width:110px}
input:focus,select:focus{outline:2px solid var(--brand2);outline-offset:1px}
button{font:inherit;font-weight:600;padding:10px 18px;border:0;border-radius:10px;cursor:pointer;color:#fff;
background:linear-gradient(120deg,var(--brand),var(--brand2));box-shadow:0 4px 12px #7c3aed40;transition:transform .12s,box-shadow .12s}
button:hover{transform:translateY(-1px);box-shadow:0 6px 16px #7c3aed55}button.ghost{background:transparent;color:var(--brand);box-shadow:none;border:1px solid var(--line)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:var(--shadow)}
.stat .k{font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.stat .v{font-size:26px;font-weight:750;margin-top:4px;letter-spacing:-.5px}.stat .s{font-size:12px;color:var(--muted);margin-top:2px}
.good{color:var(--good)}.bad{color:var(--bad)}.warn{color:var(--warn)}
table{border-collapse:collapse;width:100%;font-size:14px}
th{font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:var(--muted);text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:9px 10px;border-bottom:1px solid var(--line)}tr:last-child td{border-bottom:0}tbody tr:hover td{background:#7c3aed0d}
.num{text-align:right;font-variant-numeric:tabular-nums}
.badge{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:700}
.badge.green{background:#05966922;color:var(--good)}.badge.red{background:#dc262622;color:var(--bad)}
.badge.grey{background:#8883;color:var(--muted)}.badge.purple{background:#7c3aed22;color:var(--brand)}
.chart{position:relative}.chart svg{width:100%;height:auto;display:block;overflow:visible}
.tip{position:absolute;pointer-events:none;background:#1c1530ee;color:#fff;padding:8px 10px;border-radius:10px;font-size:12px;
display:none;white-space:nowrap;z-index:5;box-shadow:0 6px 20px #0005}
.legend{display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px}
.err{color:var(--bad);font-weight:600;margin:8px 0 0}.muted{color:var(--muted);font-size:13px}
.empty{padding:28px;text-align:center;color:var(--muted)}
.skeleton{height:120px;border-radius:12px;background:linear-gradient(90deg,var(--line),#7c3aed14,var(--line));background-size:200% 100%;animation:sh 1.2s infinite}
@keyframes sh{to{background-position:-200% 0}}
footer{max-width:1040px;margin:0 auto 30px;padding:0 20px;color:var(--muted);font-size:12px}
footer b{color:var(--brand)}
pre{background:var(--bg);padding:10px;border-radius:10px;overflow:auto}
@media(max-width:640px){header{padding:16px}.stat .v{font-size:22px}}
"""

JS = r"""
const $=(s,r=document)=>r.querySelector(s);
const fmt=(n,d=2)=>Number(n).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
const pct=(x,d=2)=>(x*100).toFixed(d)+'%';
const signed=(x,d=2)=>(x>=0?'+':'')+(x*100).toFixed(d)+'%';
const tone=x=>x>=0?'good':'bad';
const COLORS=['#7c3aed','#0ea5e9','#f59e0b','#10b981','#ef4444','#ec4899','#14b8a6','#6366f1'];
const stat=(k,v,s='',t='')=>`<div class="stat"><div class="k">${k}</div><div class="v ${t}">${v}</div><div class="s">${s}</div></div>`;
const setError=(m)=>{const e=$('#e');if(e)e.textContent=m||''};
const loading=(el)=>{el.innerHTML='<div class="skeleton"></div>'};
const css=(v)=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();

/* Line chart with gradient area, grid, axis labels and a hover read-out.
   series: [{name, values, color?, area?, dashed?}]  opts: {h, format, bands:[{y,label}], zero:true} */
function lineChart(el,labels,series,opts={}){
  const W=760,H=opts.h||300,L=58,R=14,T=14,B=30,fmtY=opts.format||(v=>fmt(v));
  const all=series.flatMap(s=>s.values).filter(v=>v!=null&&isFinite(v));
  if(!all.length){el.innerHTML='<div class="empty">No data to show.</div>';return}
  let lo=Math.min(...all),hi=Math.max(...all);(opts.bands||[]).forEach(b=>{lo=Math.min(lo,b.y);hi=Math.max(hi,b.y)});
  if(opts.min!=null)lo=opts.min;if(opts.max!=null)hi=opts.max;
  const pad=(hi-lo||1)*.08;if(opts.min==null)lo-=pad;if(opts.max==null)hi+=pad;
  const n=labels.length,x=i=>L+(n<2?0:i*(W-L-R)/(n-1)),y=v=>T+(1-(v-lo)/(hi-lo||1))*(H-T-B);
  const uid='g'+Math.random().toString(36).slice(2,7);let g='',defs='';
  for(let k=0;k<=4;k++){const v=lo+(hi-lo)*k/4,yy=y(v);g+=`<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="${css('--line')}" stroke-width="1"/><text x="${L-8}" y="${yy+4}" text-anchor="end" font-size="11" fill="${css('--muted')}">${fmtY(v)}</text>`}
  const ticks=Math.min(5,n);for(let k=0;k<ticks;k++){const i=Math.round(k*(n-1)/Math.max(1,ticks-1));g+=`<text x="${x(i)}" y="${H-8}" text-anchor="${k==0?'start':k==ticks-1?'end':'middle'}" font-size="11" fill="${css('--muted')}">${labels[i]}</text>`}
  (opts.bands||[]).forEach(b=>{g+=`<line x1="${L}" x2="${W-R}" y1="${y(b.y)}" y2="${y(b.y)}" stroke="#d97706" stroke-dasharray="4 4"/><text x="${W-R}" y="${y(b.y)-4}" text-anchor="end" font-size="11" fill="#d97706">${b.label||''}</text>`)});
  series.forEach((s,si)=>{const c=s.color||COLORS[si%COLORS.length];let d='',pen=false,first=-1,last=-1;
    s.values.forEach((v,i)=>{if(v==null||!isFinite(v)){pen=false;return}d+=(pen?'L':'M')+x(i).toFixed(1)+' '+y(v).toFixed(1);pen=true;if(first<0)first=i;last=i});
    if(s.area!==false&&si===0&&opts.area!==false&&first>=0){defs+=`<linearGradient id="${uid}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c}" stop-opacity=".30"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></linearGradient>`;
      g+=`<path d="${d} L${x(last)} ${H-B} L${x(first)} ${H-B}Z" fill="url(#${uid})"/>`}
    g+=`<path d="${d}" fill="none" stroke="${c}" stroke-width="2.2" stroke-linejoin="round" ${s.dashed?'stroke-dasharray="5 4"':''}/>`});
  el.innerHTML=`<div class="chart"><svg viewBox="0 0 ${W} ${H}"><defs>${defs}</defs>${g}<line class="cur" y1="${T}" y2="${H-B}" stroke="${css('--muted')}" stroke-dasharray="3 3" style="display:none"/><rect class="hit" x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="transparent"/></svg><div class="tip"></div></div>`+
    (series.length>1?`<div class="legend">${series.map((s,i)=>`<span><i style="background:${s.color||COLORS[i%COLORS.length]}"></i>${s.name}</span>`).join('')}</div>`:'');
  const svg=$('svg',el),tip=$('.tip',el),cur=$('.cur',el),hit=$('.hit',el);
  hit.addEventListener('mousemove',e=>{const r=svg.getBoundingClientRect(),px=(e.clientX-r.left)/r.width*W,i=Math.max(0,Math.min(n-1,Math.round((px-L)/((W-L-R)/Math.max(1,n-1)))));
    cur.setAttribute('x1',x(i));cur.setAttribute('x2',x(i));cur.style.display='';tip.style.display='block';
    tip.innerHTML=`<b>${labels[i]}</b>`+series.map((s,si)=>s.values[i]==null?'':`<div><span style="color:${s.color||COLORS[si%COLORS.length]}">&#9679;</span> ${s.name}: ${fmtY(s.values[i])}</div>`).join('');
    const tx=x(i)/W*r.width;tip.style.left=(tx>r.width*.65?tx-tip.offsetWidth-12:tx+12)+'px';tip.style.top='10px'});
  hit.addEventListener('mouseleave',()=>{tip.style.display='none';cur.style.display='none'});
}

/* Horizontal bars, green for positive and red for negative values. */
function barChart(el,labels,values,opts={}){
  const f=opts.format||(v=>fmt(v)),m=Math.max(...values.map(Math.abs),1e-9);
  el.innerHTML=labels.map((l,i)=>{const v=values[i],w=Math.abs(v)/m*46;
    return `<div style="display:grid;grid-template-columns:90px 1fr 80px;align-items:center;gap:10px;margin:8px 0"><b>${l}</b>
    <div style="position:relative;height:22px;background:var(--bg);border-radius:8px"><div style="position:absolute;top:0;bottom:0;border-radius:8px;${v>=0?'left:50%':'right:50%'};width:${w}%;background:${v>=0?'linear-gradient(90deg,#10b981,#34d399)':'linear-gradient(270deg,#ef4444,#f87171)'}"></div>
    <div style="position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:var(--line)"></div></div><span class="num ${tone(v)}">${f(v)}</span></div>`}).join('');
}

/* Donut chart with a legend. items: [{label,value}] */
function donut(el,items){
  const tot=items.reduce((a,b)=>a+b.value,0);if(!tot){el.innerHTML='<div class="empty">Nothing here yet.</div>';return}
  let a0=-Math.PI/2,paths='';const R=70,r=44,c=90;
  items.forEach((it,i)=>{const a1=a0+it.value/tot*2*Math.PI,big=a1-a0>Math.PI?1:0;
    const p=(rad,a)=>[c+rad*Math.cos(a),c+rad*Math.sin(a)];const [x0,y0]=p(R,a0),[x1,y1]=p(R,a1-.001),[x2,y2]=p(r,a1-.001),[x3,y3]=p(r,a0);
    paths+=`<path d="M${x0} ${y0}A${R} ${R} 0 ${big} 1 ${x1} ${y1}L${x2} ${y2}A${r} ${r} 0 ${big} 0 ${x3} ${y3}Z" fill="${COLORS[i%COLORS.length]}"><title>${it.label} ${pct(it.value/tot,1)}</title></path>`;a0=a1});
  el.innerHTML=`<div style="display:flex;align-items:center;gap:22px;flex-wrap:wrap"><svg viewBox="0 0 180 180" width="180">${paths}</svg><div class="legend" style="flex-direction:column;gap:8px;font-size:14px;color:var(--ink)">${items.map((it,i)=>`<span><i style="background:${COLORS[i%COLORS.length]}"></i>${it.label} <b>${pct(it.value/tot,1)}</b></span>`).join('')}</div></div>`;
}

if(document.referrer&&!document.referrer.startsWith(location.origin)){const b=$('#back');if(b){b.href=document.referrer;b.style.display='inline-block'}}
"""

LOGO = "&#128200;"  # chart emoji
