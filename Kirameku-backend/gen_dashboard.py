# -*- coding: utf-8 -*-
"""生成 Understand Anything 风格交互式知识图谱看板（自包含 HTML + 内嵌数据）"""
import json, os

base = r"F:\AI\projects\Kirameku\docs\understand-anything"
with open(os.path.join(base, "knowledge-graph.json"), "r", encoding="utf-8") as f:
    data = json.load(f)

# 分层配色（按 layer）
LAYER_COLORS = {
    # 后端
    "entry": "#e11d48", "config": "#f59e0b", "router": "#7c3aed",
    "api": "#0ea5e9", "service": "#10b981", "model": "#8b5cf6",
    "schema": "#f97316", "utils": "#ef4444", "deps": "#64748b",
    # 前端
    "page": "#22c55e", "layout": "#3b82f6", "component": "#06b6d4",
    "provider": "#a855f7", "data": "#94a3b8", "widget": "#ec4899",
    # 后台
    "view": "#14b8a6", "store": "#eab308",
}

data_json = json.dumps(data, ensure_ascii=False)

html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kirameku 代码知识图谱 · Understand Anything</title>
<style>
:root { --bg:#0b1020; --panel:#111827; --border:#1f2937; --text:#e5e7eb; --muted:#9ca3af; --accent:#38bdf8; }
* { box-sizing:border-box; }
html,body { margin:0; height:100%; background:var(--bg); color:var(--text); font-family:"Segoe UI",system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; overflow:hidden; }
#app { display:flex; height:100vh; }
#canvas-wrap { flex:1; position:relative; }
canvas { display:block; }
#toolbar { position:absolute; top:12px; left:12px; right:12px; display:flex; gap:8px; flex-wrap:wrap; align-items:center; pointer-events:none; }
#toolbar > * { pointer-events:auto; }
#search { background:var(--panel); border:1px solid var(--border); color:var(--text); padding:8px 12px; border-radius:8px; width:280px; font-size:13px; outline:none; }
#search:focus { border-color:var(--accent); }
button { background:var(--panel); border:1px solid var(--border); color:var(--text); padding:8px 12px; border-radius:8px; cursor:pointer; font-size:13px; }
button:hover { border-color:var(--accent); color:var(--accent); }
#stats { font-size:12px; color:var(--muted); }
#legend { position:absolute; bottom:12px; left:12px; background:rgba(17,24,39,.92); border:1px solid var(--border); border-radius:10px; padding:10px 12px; font-size:12px; max-height:46vh; overflow:auto; }
#legend h4 { margin:0 0 6px; font-size:12px; color:var(--muted); }
#legend .row { display:flex; align-items:center; gap:6px; margin:3px 0; }
#legend .dot { width:10px; height:10px; border-radius:50%; flex:0 0 auto; }
#tip { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); color:var(--muted); font-size:14px; pointer-events:none; }
#side { width:360px; background:var(--panel); border-left:1px solid var(--border); padding:18px; overflow:auto; display:none; }
#side.open { display:block; }
#side .close { float:right; background:none; border:none; color:var(--muted); font-size:20px; cursor:pointer; }
#side h2 { margin:0 0 4px; font-size:18px; word-break:break-all; }
#side .layer-tag { display:inline-block; background:#1e293b; color:var(--accent); border-radius:4px; padding:2px 8px; font-size:11px; margin:4px 0 8px; }
#side .path { font-family:Consolas,monospace; font-size:12px; color:var(--muted); word-break:break-all; margin:0 0 10px; }
#side .desc { font-size:13px; line-height:1.6; background:#0f172a; border-radius:8px; padding:10px; margin-bottom:14px; }
#side h3 { font-size:13px; color:var(--muted); margin:14px 0 6px; }
#side ul { list-style:none; margin:0; padding:0; }
#side li { font-size:12px; padding:5px 8px; margin:3px 0; background:#0f172a; border-radius:6px; cursor:pointer; }
#side li:hover { background:#1e293b; }
#side li .edge-type { color:var(--accent); }
</style>
</head>
<body>
<div id="app">
  <div id="canvas-wrap">
    <canvas id="cv"></canvas>
    <div id="toolbar">
      <input id="search" placeholder="搜索文件 / 函数 / 说明…">
      <button id="btn-labels">显示标签</button>
      <button id="btn-reset">重新布局</button>
      <span id="stats"></span>
    </div>
    <div id="legend"></div>
    <div id="tip">加载中…</div>
  </div>
  <div id="side">
    <button class="close" id="btn-close">×</button>
    <h2 id="s-label"></h2>
    <div class="layer-tag" id="s-layer"></div>
    <p class="path" id="s-path"></p>
    <div class="desc" id="s-desc"></div>
    <h3>关联（入/出）</h3>
    <ul id="s-links"></ul>
  </div>
</div>
<script>
const DATA = __DATA__;
const GROUP = (id) => id.startsWith('backend/') ? '后端' : id.startsWith('frontend/') ? '前端' : '后台';
</script>
<script src="data:text/javascript;base64,__ENGINE__"></script>
</body>
</html>
"""

# 引擎 JS（力导向布局 + 交互）
engine = r"""
(function(){
const LAYER_COLORS = __LAYER_COLORS__;
const GROUP_COLORS = { '后端':'#3b82f6', '前端':'#22c55e', '后台':'#f59e0b' };
const cv = document.getElementById('cv');
const ctx = cv.getContext('2d');
const wrap = document.getElementById('canvas-wrap');
const side = document.getElementById('side');
const search = document.getElementById('search');
const tip = document.getElementById('tip');

// 构建节点/边
const g = new Map(); // id -> node
DATA.nodes.forEach(n => { n.x = Math.random()*1200; n.y = Math.random()*800; n.vx=0; n.vy=0; n.color = LAYER_COLORS[n.layer] || '#888'; g.set(n.id, n); });
const edges = DATA.edges.filter(e => g.has(e.source) && g.has(e.target)).map(e => ({...e}));
// 每个节点的邻接表
const adj = new Map();
edges.forEach(e => { 
  (adj.get(e.source) || adj.set(e.source, []).get(e.source)).push(e.target);
  (adj.get(e.target) || adj.set(e.target, []).get(e.target)).push(e.source);
});

// 尺寸
let W=0,H=0, scale=1, tx=0, ty=0;
function resize(){ W=wrap.clientWidth; H=wrap.clientHeight; cv.width=W*devicePixelRatio; cv.height=H*devicePixelRatio; ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0); }
window.addEventListener('resize', resize); resize();

// 布局参数
const nodes = [...g.values()];
const N = nodes.length;
const cx = W/2, cy = H/2;

// 力导向迭代
function step(){
  // 斥力（库仑）
  for(let i=0;i<N;i++){
    for(let j=i+1;j<N;j++){
      let dx=nodes[j].x-nodes[i].x, dy=nodes[j].y-nodes[i].y;
      let d2=dx*dx+dy*dy; if(d2<1){d2=1;dx=Math.random()-0.5;dy=Math.random()-0.5;}
      let d=Math.sqrt(d2);
      let f=1500/d2;
      let fx=dx/d*f, fy=dy/d*f;
      nodes[i].vx-=fx; nodes[i].vy-=fy; nodes[j].vx+=fx; nodes[j].vy+=fy;
    }
  }
  // 弹簧引力（边）
  edges.forEach(e=>{ const a=g.get(e.source), b=g.get(e.target); if(!a||!b)return;
    let dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)||1; let f=(d-90)*0.02;
    let fx=dx/d*f, fy=dy/d*f; a.vx+=fx; a.vy+=fy; b.vx-=fx; b.vy-=fy; });
  // 中心引力
  nodes.forEach(n=>{ n.vx+=(cx-n.x)*0.001; n.vy+=(cy-n.y)*0.001; });
  // 积分
  nodes.forEach(n=>{ n.vx*=0.85; n.vy*=0.85; n.x+=n.vx; n.y+=n.vy; });
}

// 渲染
let showLabels=false, hover=null, selected=null, query='';
function color(){ return query? true:false; }

function screenToWorld(px,py){ return [(px-tx)/scale, (py-ty)/scale]; }

function draw(){
  ctx.clearRect(0,0,W,H);
  ctx.save();
  ctx.translate(tx,ty); ctx.scale(scale,scale);
  // 边
  ctx.lineWidth=0.6/scale;
  edges.forEach(e=>{ const a=g.get(e.source), b=g.get(e.target); if(!a||!b)return;
    const match = query && (a.label.toLowerCase().includes(query) || b.label.toLowerCase().includes(query));
    ctx.strokeStyle = match ? 'rgba(56,189,248,0.9)' : 'rgba(148,163,184,0.18)';
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
  });
  // 节点
  nodes.forEach(n=>{
    const r = (n===hover||n===selected)?7:4.5;
    ctx.beginPath(); ctx.arc(n.x,n.y,r,0,Math.PI*2);
    ctx.fillStyle = n.color; ctx.fill();
    if(n===hover||n===selected){ ctx.lineWidth=2/scale; ctx.strokeStyle='#fff'; ctx.stroke(); }
  });
  // hover 高亮邻接
  if(hover){
    (adj.get(hover.id)||[]).forEach(id=>{ const n=g.get(id); ctx.beginPath(); ctx.arc(n.x,n.y,6,0,Math.PI*2); ctx.strokeStyle='rgba(56,189,248,0.7)'; ctx.lineWidth=1.5/scale; ctx.stroke(); });
  }
  ctx.restore();
  // 标签
  if(showLabels){
    ctx.save(); ctx.translate(tx,ty); ctx.scale(scale,scale);
    ctx.font=(11/scale)+'px sans-serif'; ctx.fillStyle='#cbd5e1'; ctx.textAlign='center';
    nodes.forEach(n=>{ if(scale>0.5) ctx.fillText(n.label, n.x, n.y-8); });
    ctx.restore();
  }
}

function loop(){ for(let k=0;k<3;k++) step(); draw(); requestAnimationFrame(loop); }
loop();

// 画布坐标 <-> 世界坐标
function worldX(px){return (px-tx)/scale;} function worldY(py){return (py-ty)/scale;}
function toScreen(n){const x=n.x*scale+tx, y=n.y*scale+ty; return [x,y];}

// 命中检测
function pick(px,py){ const [wx,wy]=screenToWorld(px,py); let best=null,bd=1e9;
  nodes.forEach(n=>{ let d=(n.x-wx)**2+(n.y-wy)**2; const th=10/scale; if(d<th**2 && d<bd){bd=d;best=n;} }); return best; }

// 交互
let dragging=null, panning=false, lastX=0,lastY=0;
cv.addEventListener('mousedown', e=>{ const r=cv.getBoundingClientRect(); const mx=e.clientX-r.left, my=e.clientY-r.top;
  const n=pick(mx,my);
  if(n){ dragging=n; } else { panning=true; lastX=mx; lastY=my; }
});
window.addEventListener('mousemove', e=>{ const r=cv.getBoundingClientRect(); const mx=e.clientX-r.left, my=e.clientY-r.top;
  if(dragging){ const [wx,wy]=screenToWorld(mx,my); dragging.x=wx; dragging.y=wy; dragging.vx=dragging.vy=0; }
  else if(panning){ tx+=mx-lastX; ty+=my-lastY; lastX=mx; lastY=my; }
  else { hover=pick(mx,my); cv.style.cursor = hover?'pointer':'grab'; }
});
window.addEventListener('mouseup', ()=>{ dragging=null; panning=false; });
cv.addEventListener('wheel', e=>{ e.preventDefault(); const r=cv.getBoundingClientRect(); const mx=e.clientX-r.left, my=e.clientY-r.top;
  const before=screenToWorld(mx,my); const k=e.deltaY<0?1.1:0.9; scale=Math.max(0.2,Math.min(3,scale*k));
  const after=screenToWorld(mx,my); tx+=(after[0]-before[0])*scale; ty+=(after[1]-before[1])*scale; }, {passive:false});

function showSide(n){
  selected=n; side.classList.add('open');
  document.getElementById('s-label').textContent=n.label;
  document.getElementById('s-layer').textContent=GROUP(n.id)+' · '+n.layer;
  document.getElementById('s-path').textContent=n.path;
  document.getElementById('s-desc').textContent=n.desc||'(无说明)';
  const ul=document.getElementById('s-links'); ul.innerHTML='';
  edges.forEach(e=>{ let other=null, dir='';
    if(e.source===n.id){other=e.target;dir='→ ';} else if(e.target===n.id){other=e.source;dir='← ';}
    if(other){ const m=g.get(other); const li=document.createElement('li');
      li.innerHTML='<span class="edge-type">'+dir+e.type+'</span> '+m.label+' <span style="color:#64748b">'+ (e.label||'') +'</span>';
      li.onclick=()=>showSide(m); ul.appendChild(li); }
  });
  if(!ul.children.length) ul.innerHTML='<li style="color:#64748b">无关联</li>';
}
cv.addEventListener('click', e=>{ const r=cv.getBoundingClientRect(); const n=pick(e.clientX-r.left,e.clientY-r.top); if(n) showSide(n); });
document.getElementById('btn-close').onclick=()=>{ side.classList.remove('open'); selected=null; };

// 搜索
let t1=null; const tipEl=tip;
search.addEventListener('input', ()=>{ query=search.value.trim().toLowerCase(); });
// 标签切换
document.getElementById('btn-labels').onclick=()=>{ showLabels=!showLabels; };
document.getElementById('btn-reset').onclick=()=>{ nodes.forEach(n=>{ n.x=Math.random()*W; n.y=Math.random()*H; n.vx=n.vy=0; }); };

// 图例
const legend=document.getElementById('legend');
function buildLegend(){
  let h='<h4>图例 · 分层配色</h4>';
  const layers={};
  nodes.forEach(n=>{ (layers[n.layer]=layers[n.layer]||[]); });
  Object.keys(LAYER_COLORS).forEach(l=>{ if([...g.values()].some(n=>n.layer===l)){
    h+='<div class="row"><span class="dot" style="background:'+LAYER_COLORS[l]+'"></span>'+l+'</div>'; } });
  h+='<hr style="border-color:#1f2937;margin:8px 0">';
  Object.keys(GROUP_COLORS).forEach(grp=>{ h+='<div class="row"><span class="dot" style="background:'+GROUP_COLORS[grp]+'"></span>'+grp+' (域)</div>'; });
  legend.innerHTML=h;
}
buildLegend();

// 统计
document.getElementById('stats').textContent = DATA.nodes.length+' 节点 · '+edges.length+' 边';
tip.remove();
})();
"""

import base64 as b64
engine_filled = engine.replace("__LAYER_COLORS__", json.dumps(LAYER_COLORS, ensure_ascii=False))
engine_b64 = b64.b64encode(engine_filled.encode("utf-8")).decode("ascii")
html = html.replace("__DATA__", data_json).replace("__ENGINE__", engine_b64)

out = os.path.join(base, "index.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
print(f"已写入: {out}  ({os.path.getsize(out)/1024:.1f} KB)")