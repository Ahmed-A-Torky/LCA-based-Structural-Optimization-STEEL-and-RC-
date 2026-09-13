/* ============================================================
   workspace.js — optimization control, polling, and all views
   ============================================================ */
const META = JSON.parse(document.getElementById('meta').textContent);
const KEY = META.key;

let CURRENT = null;      // last result payload
let POLL = null;         // polling interval
let JOB = null;
let three = null;        // three.js viewer state

/* ---------- sliders ---------- */
function bindSlider(id, valId, fmt){
  const el = document.getElementById(id), out = document.getElementById(valId);
  const upd = () => {
    out.textContent = fmt ? fmt(el.value) : el.value;
    const pct = (el.value - el.min) / (el.max - el.min) * 100;
    el.style.setProperty('--p', pct + '%');
  };
  el.addEventListener('input', upd); upd();
}
bindSlider('pop', 'popVal');
bindSlider('gen', 'genVal');
bindSlider('mut', 'mutVal', v => (+v).toFixed(2));
bindSlider('cx', 'cxVal', v => (+v).toFixed(2));
bindSlider('seed', 'seedVal', v => (+v === 0 ? 'auto' : v));

document.getElementById('advToggle').addEventListener('click', e => {
  e.currentTarget.classList.toggle('open');
  document.getElementById('advBody').classList.toggle('open');
});

/* ---------- run / cancel ---------- */
const runBtn = document.getElementById('runBtn');
const cancelBtn = document.getElementById('cancelBtn');
const progWrap = document.getElementById('progWrap');

runBtn.addEventListener('click', startRun);
document.getElementById('rerunBtn').addEventListener('click', startRun);
cancelBtn.addEventListener('click', cancelRun);
document.getElementById('clearBtn').addEventListener('click', () => location.href = '/');

function gaParams(){
  const seed = +document.getElementById('seed').value;
  const routeEl = document.getElementById('steelRoute');
  let extra = routeEl ? {steel_route: routeEl.value} : {};
  const dM = document.getElementById('dM');
  if(dM){
    extra.design = {M_kNm:+dM.value, L_m:+document.getElementById('dL').value,
      Fy:+document.getElementById('dFy').value,
      Lb_mode:document.getElementById('latMode').value,
      Lb_m:+document.getElementById('dLb').value,
      Cb:+((document.getElementById('dCb')||{value:1}).value)};
  }
  return { ...extra,
    pop_size: +document.getElementById('pop').value,
    n_gen: +document.getElementById('gen').value,
    mutation: +document.getElementById('mut').value,
    crossover: +document.getElementById('cx').value,
    seed: seed === 0 ? null : seed,
  };
}

async function startRun(){
  // reset UI
  document.getElementById('emptyState').style.display = 'none';
  document.getElementById('views').innerHTML = '';
  document.getElementById('viewTabs').style.display = 'none';
  document.getElementById('postCtrl').style.display = 'none';
  CURRENT = null;
  runBtn.disabled = true;
  runBtn.innerHTML = '<span class="spinner"></span> Optimizing…';
  cancelBtn.style.display = 'block';
  progWrap.classList.add('show');
  setProgress(0, 0, 0, null);

  const r = await fetch('/api/optimize/' + KEY, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(gaParams())
  });
  const j = await r.json();
  if (!r.ok || j.error) {
    // e.g. 429 when the public server is busy
    progWrap.classList.remove('show');
    runBtn.disabled = false;
    runBtn.innerHTML = '▶ Optimize';
    cancelBtn.style.display = 'none';
    const es = document.getElementById('emptyState');
    es.style.display = 'block';
    es.innerHTML = '<div class="ico">⏳</div><h3>Server busy</h3><p>' +
      (j.error || 'Please try again in a moment.') + '</p>';
    return;
  }
  JOB = j.job;
  document.getElementById('genTot').textContent = j.n_gen;
  POLL = setInterval(() => poll(j.n_gen), 350);
}

async function poll(nGen){
  if(!JOB) return;
  const r = await fetch('/api/progress/' + JOB);
  if(r.status === 404){ clearInterval(POLL); return; }
  const p = await r.json();
  setProgress(p.gen, nGen, p.gen/nGen*100, p.best_obj, p.best_feasible, p.best_f1);
  if(p.status === 'done' || p.status === 'cancelled' || p.status === 'error'){
    clearInterval(POLL); POLL = null;
    await fetchResult();
  }
}

function setProgress(gen, tot, pct, best, feasible, f1){
  document.getElementById('barFill').style.width = Math.min(100, pct) + '%';
  document.getElementById('pctTxt').textContent = Math.round(Math.min(100,pct)) + '%';
  document.getElementById('genNow').textContent = gen;
  const b = document.getElementById('bestNow');
  const funit = META.key === '6frame_freq' ? 'rad/s' : 'Hz';
  if(META.family === 'frequency' && f1 != null){
    const fTxt = 'f\u2081 ' + f1.toFixed(2) + ' ' + funit;
    if(best == null){ b.textContent = fTxt + ' · searching…'; b.style.color = 'var(--cyan-soft)'; }
    else { b.textContent = fTxt + ' · ' + best.toFixed(1) + ' ' + META.unit; b.style.color = 'var(--green)'; }
  } else if(best == null){ b.textContent = feasible === false ? 'searching…' : '—'; b.style.color = 'var(--fg-faint)'; }
  else { b.textContent = best.toFixed(1) + ' ' + META.unit; b.style.color = 'var(--green)'; }
}

async function cancelRun(){
  if(!JOB) return;
  await fetch('/api/cancel/' + JOB, {method:'POST'});
}

async function fetchResult(){
  const r = await fetch('/api/result/' + JOB);
  if(r.status === 202){ setTimeout(fetchResult, 300); return; }
  const data = await r.json();
  CURRENT = data;
  runBtn.disabled = false;
  runBtn.innerHTML = '▶ Optimize';
  cancelBtn.style.display = 'none';
  progWrap.classList.remove('show');
  document.getElementById('postCtrl').style.display = 'block';
  document.getElementById('viewTabs').style.display = 'flex';
  renderViews();
}

/* ---------- checkbox toggles ---------- */
document.querySelectorAll('#viewTabs input').forEach(cb => {
  cb.addEventListener('change', () => {
    cb.closest('.chk').classList.toggle('active', cb.checked);
    renderViews();
  });
});
function activeViews(){
  return [...document.querySelectorAll('#viewTabs input:checked')].map(c => c.dataset.view);
}

/* ============================================================
   RENDER
   ============================================================ */
function renderViews(){
  if(!CURRENT) return;
  const host = document.getElementById('views');
  const want = activeViews();
  // dispose 3D if hidden
  if(!want.includes('model') && three){ disposeThree(); }
  host.innerHTML = '';
  if(want.includes('results'))  host.appendChild(viewResults());
  if(want.includes('fitness'))  host.appendChild(viewFitness());
  if(want.includes('model'))    host.appendChild(viewModel());
  if(want.includes('sections')) host.appendChild(viewSections());

  if(want.includes('fitness')) drawFitness();
  if(want.includes('model'))   initThree();
}

function block(title, note, innerNode){
  const b = document.createElement('div'); b.className = 'view-block';
  const vh = document.createElement('div'); vh.className = 'vh';
  vh.innerHTML = `<h3>${title}</h3><span class="vh-note">${note||''}</span>`;
  const vc = document.createElement('div'); vc.className = 'vc';
  vc.appendChild(innerNode);
  b.appendChild(vh); b.appendChild(vc);
  return b;
}

/* ---------- results summary ---------- */
function viewResults(){
  const ev = CURRENT.evaluation;
  const wrap = document.createElement('div');
  const feasible = CURRENT.feasible && ev.n_viol === 0;
  const mass = ev.mass;
  const delta = ((mass - CURRENT.ref_mass)/CURRENT.ref_mass*100);
  const isCO2 = META.family === 'co2';
  const objLabel = isCO2 ? 'Embodied CO\u2082' : 'Optimized mass';

  const grid = document.createElement('div'); grid.className = 'result-grid';
  const isFreq = META.family === 'frequency' && CURRENT.freq_target;
  if(isFreq){
    const ft = CURRENT.freq_target;
    const f1 = (ev.freqs && ev.freqs.length >= ft.mode) ? ev.freqs[ft.mode-1] : null;
    const fok = f1 != null && Math.abs(f1-ft.value)/ft.value <= ft.tol + 1e-9;
    grid.innerHTML = `
      <div class="metric ${fok?'ok':''}"><div class="lab">Achieved f${ft.mode}</div>
        <div class="num">${f1==null?'—':f1.toFixed(2)}<span class="unit"> ${ft.unit}</span></div></div>
      <div class="metric amber"><div class="lab">Target (reference)</div>
        <div class="num">${ft.value}<span class="unit"> ${ft.unit} ±${(ft.tol*100).toFixed(0)}%</span></div></div>
      <div class="metric accent"><div class="lab">Optimized mass</div>
        <div class="num">${mass.toFixed(1)}<span class="unit"> ${META.unit}</span></div></div>
      <div class="metric"><div class="lab">Evaluations</div>
        <div class="num">${CURRENT.evaluations.toLocaleString()}</div></div>
    `;
  } else {
    grid.innerHTML = `
    <div class="metric accent"><div class="lab">${objLabel}</div>
      <div class="num">${mass.toFixed(1)}<span class="unit"> ${META.unit}</span></div></div>
    <div class="metric amber"><div class="lab">Reference</div>
      <div class="num">${CURRENT.ref_mass}<span class="unit"> ${META.unit}</span></div></div>
    <div class="metric ${delta<=0?'ok':''}"><div class="lab">Δ vs reference</div>
      <div class="num">${delta>=0?'+':''}${delta.toFixed(1)}<span class="unit">%</span></div></div>
    <div class="metric"><div class="lab">Evaluations</div>
      <div class="num">${CURRENT.evaluations.toLocaleString()}</div></div>
    `;
  }
  wrap.appendChild(grid);
  if(ev.carbon){
    const c = ev.carbon;
    const parts = Object.entries(c.breakdown).map(([k,v])=>`${k} <b>${v.toFixed(0)}</b>`).join(' \u00b7 ');
    const cn = document.createElement('div'); cn.className = 'note';
    cn.innerHTML = `<b>Embodied carbon: ${c.total.toFixed(1)} kg CO\u2082</b> \u2014 ${parts}.
      ${c.material === 'rebar' ? 'Objective is CO\u2082; concrete 224.94 kg/m\u00b3 (BEDEC), rebar'
        : 'Objective is mass; carbon reported for ' + c.material + ' at'} <b>${c.factor.toFixed(2)} kg/kg</b>
      (${c.route} route).`;
    wrap.appendChild(cn);
  }

  // feasibility pill + constraint detail
  const row = document.createElement('div');
  row.style.cssText = 'margin-top:16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center';
  row.innerHTML = `<span class="pill ${feasible?'ok':'warn'}">
      ${feasible?'✓ Feasible':'✗ '+ev.n_viol+' violation'+(ev.n_viol>1?'s':'')}</span>`;

  if(META.family === 'static' && ev.max_disp != null){
    const u = (ev.max_disp).toFixed(3), lim = (ev.disp_limit).toFixed(3);
    const ok = ev.max_disp <= ev.disp_limit;
    row.innerHTML += `<span class="pill ${ok?'ok':'warn'}">max |u| ${u} / ${lim} mm</span>`;
  }
  if(META.family === 'frequency' && ev.targets){
    ev.targets.forEach(t => {
      if(t.value==null) return;
      row.innerHTML += `<span class="pill ${t.ok?'ok':'warn'}">f${t.mode} = ${t.value.toFixed(2)} ${ev.unit} (${t.sense} ${t.target})</span>`;
    });
  }
  if(isCO2 && ev.constraints && ev.constraints.length){
    const gov = ev.constraints.reduce((a,c)=> c.util > a.util ? c : a);
    row.innerHTML += `<span class="pill ${gov.ok?'ok':'warn'}">governing: ${gov.name} @ ${(gov.util*100).toFixed(0)}%</span>`;
  }
  wrap.appendChild(row);

  if(isCO2 && ev.breakdown){
    const bk = ev.breakdown;
    const parts = Object.keys(bk).map(k =>
      `${k.charAt(0).toUpperCase()+k.slice(1)} <b>${bk[k].toFixed(0)}</b>`).join(' \u00b7 ');
    if(ev.breakdown){
    const bnote = document.createElement('div');
      bnote.className = 'note';
      const rt = ev.steel_route, rf = ev.steel_co2_factor;
      let steelTxt = rf != null
        ? `steel <b>${rf.toFixed(2)} kg/kg</b> (${rt} route)` : 'steel 2.82 kg/kg';
      bnote.innerHTML = `Emission breakdown (kg CO\u2082): ${parts}. Concrete 224.94 kg/m\u00b3
        (BEDEC); ${steelTxt}.` + (rt && rt !== 'bedec'
        ? ` <span style="color:var(--amber-soft)">Note: the studio reference was calibrated
        with the default BEDEC route (2.82 kg/kg) \u2014 compare like-for-like runs.</span>` : '');
      wrap.appendChild(bnote);
    }
  }

  // Plain-language interpretation of the delta vs the published reference.
  if(isFreq){
    const ft = CURRENT.freq_target;
    const f1 = (ev.freqs && ev.freqs.length >= ft.mode) ? ev.freqs[ft.mode-1] : null;
    const interp = document.createElement('div');
    interp.className = feasible ? 'note' : 'note amber';
    if(feasible){
      interp.innerHTML = `The optimized structure hits the frequency target:
        f${ft.mode} = <b>${f1.toFixed(2)} ${ft.unit}</b>, within ±${(ft.tol*100).toFixed(0)}% of the
        ${ft.value} ${ft.unit} reference target. Mass is minimized subject to that target —
        this run: <b>${mass.toFixed(1)} kg</b>; published minimum-mass value for context:
        ${CURRENT.ref_mass} kg (${delta>=0?'+':''}${delta.toFixed(1)}%).`;
    } else {
      interp.innerHTML = `No design satisfied the target band within this budget. Closest
        achieved frequency: <b>${f1==null?'—':f1.toFixed(2)} ${ft.unit}</b> vs the
        ${ft.value} ${ft.unit} target — see the frequency convergence chart. More
        generations or a larger population usually closes the gap.`;
    }
    wrap.appendChild(interp);
  } else if(feasible){
    const interp = document.createElement('div');
    interp.className = 'note';
    const refWord = isCO2 ? 'studio reference (best long-run GA design)' : 'published reference';
    if(delta <= 1.0){
      interp.innerHTML = `This feasible design is <b>${delta<=0?'at or below':'within 1% of'}</b>
        the ${refWord} of ${CURRENT.ref_mass} ${META.unit}. Under the loads and
        constraints implemented here, the optimizer found an equal-or-better solution.`;
    } else {
      interp.innerHTML = `The optimizer reached a feasible design <b>${delta.toFixed(1)}% above</b>
        the ${refWord} of ${CURRENT.ref_mass} ${META.unit}. Increasing the
        generations or population usually narrows this gap; some benchmarks plateau a little
        above the gradient-method optimum.`;
    }
    wrap.appendChild(interp);
  } else {
    const interp = document.createElement('div');
    interp.className = 'note amber';
    interp.innerHTML = `No fully feasible design was found within this budget. Try more
      generations or a larger population.`;
    wrap.appendChild(interp);
  }

  if(META.family === 'frequency'){
    const note = document.createElement('div');
    note.className = 'note';
    note.innerHTML = `Modal analysis with consistent mass. Frequencies extracted from
       the generalized eigenproblem (K − ω²M)φ = 0.`;
    wrap.appendChild(note);
  }

  // Download-results button
  const dl = document.createElement('button');
  dl.className = 'btn btn-ghost';
  dl.style.cssText = 'margin-top:16px;width:auto;padding:10px 18px';
  dl.textContent = '⬇ Download results (JSON)';
  dl.addEventListener('click', downloadResults);
  wrap.appendChild(dl);

  return block('Final results', feasible?'optimum found':'best feasible attempt', wrap);
}

function downloadResults(){
  if(!CURRENT) return;
  const ev = CURRENT.evaluation;
  const payload = {
    problem: META.name, key: KEY,
    optimized_mass: ev.mass, reference_mass: CURRENT.ref_mass, unit: META.unit,
    feasible: CURRENT.feasible && ev.n_viol === 0,
    n_violations: ev.n_viol,
    evaluations: CURRENT.evaluations,
    design_variables: CURRENT.best_x,
    group_labels: CURRENT.group_labels,
    members: ev.bars || null,
    design_variables_detail: ev.variables || null,
    constraints: ev.constraints || null,
    co2_breakdown: ev.breakdown || null,
    quantities: ev.quantities || null,
    frequencies: ev.freqs || null,
    frequency_targets: ev.targets || null,
    max_displacement: ev.max_disp ?? null,
    convergence_history: CURRENT.history,
    generated: new Date().toISOString(),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = KEY + '_optimized.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

/* ---------- fitness curve ---------- */
function viewFitness(){
  const c = document.createElement('canvas');
  c.className = 'fit'; c.id = 'fitCanvas'; c.height = 300;
  const wrap = document.createElement('div'); wrap.appendChild(c);
  const lg = document.createElement('div'); lg.className='legend';
  if(META.family === 'frequency' && CURRENT.freq_target){
    const ft = CURRENT.freq_target;
    lg.innerHTML = `<span class="lg"><span class="sw" style="background:var(--cyan)"></span>Best-design f${ft.mode}</span>
       <span class="lg"><span class="sw" style="background:var(--amber)"></span>Target ${ft.value} ${ft.unit} ±${(ft.tol*100).toFixed(0)}%</span>`;
    wrap.appendChild(lg);
    return block('Frequency convergence', 'best-design f' + ft.mode + ' per generation vs target', wrap);
  }
  const objWord = META.family==='co2' ? 'CO\u2082' : 'mass';
  lg.innerHTML = `<span class="lg"><span class="sw" style="background:var(--cyan)"></span>Best feasible ${objWord}</span>
     <span class="lg"><span class="sw" style="background:var(--amber)"></span>Reference optimum</span>`;
  wrap.appendChild(lg);
  return block('Convergence', 'best ' + objWord + ' per generation', wrap);
}
function drawFitness(){
  const c = document.getElementById('fitCanvas'); if(!c) return;
  const dpr = window.devicePixelRatio || 1;
  const W = c.clientWidth, H = 300;
  c.width = W*dpr; c.height = H*dpr;
  const x = c.getContext('2d'); x.scale(dpr,dpr);
  x.clearRect(0,0,W,H);
  const isFreqChart = META.family === 'frequency' && CURRENT.freq_history
                      && CURRENT.freq_history.length && CURRENT.freq_target;
  const hist = isFreqChart ? CURRENT.freq_history : CURRENT.history;
  const ft = CURRENT.freq_target;
  const pad = {l:64, r:18, t:18, b:34};
  const plotW = W-pad.l-pad.r, plotH = H-pad.t-pad.b;

  const vals = hist.filter(v => v!=null);
  const ref = isFreqChart ? ft.value : CURRENT.ref_mass;
  let lo = Math.min(ref, ...vals), hi = Math.max(ref, ...vals);
  if(isFreqChart){ lo = Math.min(lo, ref*(1-ft.tol)); hi = Math.max(hi, ref*(1+ft.tol)); }
  if(!isFinite(lo)){ lo = 0; hi = 1; }
  const span = (hi-lo)||1; lo -= span*0.08; hi += span*0.08;
  const n = hist.length;
  const X = i => pad.l + (n<=1?0:i/(n-1))*plotW;
  const Y = v => pad.t + (1-(v-lo)/(hi-lo))*plotH;

  // grid + y labels
  x.font = '11px "IBM Plex Mono"'; x.textBaseline='middle';
  for(let k=0;k<=4;k++){
    const v = lo+(hi-lo)*k/4, yy = Y(v);
    x.strokeStyle = 'rgba(35,52,79,.6)'; x.lineWidth=1;
    x.beginPath(); x.moveTo(pad.l,yy); x.lineTo(W-pad.r,yy); x.stroke();
    x.fillStyle = '#64758f'; x.textAlign='right';
    x.fillText(v.toFixed((hi-lo) < 20 ? 2 : 0), pad.l-10, yy);
  }
  // x axis label
  x.fillStyle='#64758f'; x.textAlign='center'; x.textBaseline='top';
  x.fillText('generation', pad.l+plotW/2, H-16);

  // reference: frequency target line + tolerance band, or mass reference line
  if(isFreqChart){
    const yT = Y(ref), yU = Y(ref*(1+ft.tol)), yL = Y(ref*(1-ft.tol));
    x.fillStyle = 'rgba(244,164,60,.10)';
    x.fillRect(pad.l, yU, plotW, yL-yU);
    x.strokeStyle = 'rgba(244,164,60,.55)'; x.setLineDash([3,4]); x.lineWidth=1;
    x.beginPath(); x.moveTo(pad.l,yU); x.lineTo(W-pad.r,yU); x.stroke();
    x.beginPath(); x.moveTo(pad.l,yL); x.lineTo(W-pad.r,yL); x.stroke();
    x.strokeStyle = '#f4a43c'; x.setLineDash([6,4]); x.lineWidth=1.6;
    x.beginPath(); x.moveTo(pad.l,yT); x.lineTo(W-pad.r,yT); x.stroke();
    x.setLineDash([]);
    x.fillStyle = '#f4a43c'; x.textAlign='left'; x.textBaseline='bottom';
    x.fillText('target ' + ft.value + ' ' + ft.unit, pad.l+6, yT-3);
  } else {
    x.strokeStyle = '#f4a43c'; x.setLineDash([5,4]); x.lineWidth=1.5;
    x.beginPath(); x.moveTo(pad.l, Y(ref)); x.lineTo(W-pad.r, Y(ref)); x.stroke();
    x.setLineDash([]);
  }

  // best-mass line (skip nulls / leading infeasible)
  x.strokeStyle = '#46c8d6'; x.lineWidth=2.4; x.lineJoin='round';
  x.beginPath(); let started=false;
  hist.forEach((v,i)=>{ if(v==null) return;
    const px=X(i), py=Y(v);
    if(!started){ x.moveTo(px,py); started=true; } else x.lineTo(px,py);
  });
  x.stroke();
  // area fill
  if(started){
    x.lineTo(X(n-1), Y(lo)); x.lineTo(pad.l, Y(lo)); x.closePath();
    const g = x.createLinearGradient(0,pad.t,0,pad.t+plotH);
    g.addColorStop(0,'rgba(70,200,214,.22)'); g.addColorStop(1,'rgba(70,200,214,0)');
    x.fillStyle=g; x.fill();
  }
  // final point
  const lastI = hist.length-1, lastV = hist[lastI];
  if(lastV!=null){
    x.fillStyle='#46c8d6'; x.beginPath(); x.arc(X(lastI),Y(lastV),4.5,0,7); x.fill();
    x.fillStyle='#e8eef7'; x.textAlign='right'; x.textBaseline='bottom';
    const lastTxt = isFreqChart ? ('f'+ft.mode+' = '+lastV.toFixed(2)+' '+ft.unit)
                                : (lastV.toFixed(1)+' '+META.unit);
    x.fillText(lastTxt, W-pad.r, Y(lastV)-8);
  }
}

/* ---------- sections table ---------- */
function viewSections(){
  const ev = CURRENT.evaluation;
  if(META.family === 'co2' || META.family === 'member') return viewSectionsRC(ev);
  const bars = ev.bars || [];
  const labels = CURRENT.group_labels || [];
  const isFreq = META.family === 'frequency';
  const isFrame = META.kind === 'Moment frame' || META.kind === 'Braced frame' || META.kind === 'Portal frame';
  // group by area for the design-variable view if grouped
  const amax = Math.max(...bars.map(b=>b.area));

  const wrap = document.createElement('div');
  const scroll = document.createElement('div'); scroll.className='scroll';
  const t = document.createElement('table'); t.className='tbl';

  let head = `<tr><th>#</th>`;
  if(bars[0] && bars[0].group!=null) head += `<th>Group</th>`;
  if(bars[0] && bars[0].role!=null) head += `<th>Role</th>`;
  head += `<th>Area (mm²)</th><th>Area (cm²)</th>`;
  if(!isFreq) head += `<th>Stress / limit</th><th></th>`;
  else head += `<th>Relative size</th>`;
  head += `</tr>`;

  let rows = '';
  bars.forEach(b=>{
    rows += `<tr>`;
    rows += `<td>${b.id}</td>`;
    if(b.group!=null) rows += `<td style="color:var(--cyan-soft)">${labels[b.group-1]||('G'+b.group)}</td>`;
    if(b.role!=null) rows += `<td style="color:var(--cyan-soft)">${b.role}</td>`;
    rows += `<td>${b.area.toFixed(1)}</td>`;
    rows += `<td>${(b.area/100).toFixed(2)}</td>`;
    if(!isFreq){
      const util = b.limit ? Math.abs(b.sigma)/b.limit : 0;
      const cls = b.viol ? 'viol' : '';
      rows += `<td class="${cls}">${b.sigma.toFixed(1)} / ${b.limit.toFixed(0)} ${b.unit ?? 'MPa'}</td>`;
      rows += `<td class="barcell" style="min-width:120px"><div class="minibar"><i style="width:${Math.min(100,util*100).toFixed(0)}%;${b.viol?'background:var(--danger)':''}"></i></div></td>`;
    } else {
      rows += `<td class="barcell" style="min-width:140px"><div class="minibar"><i style="width:${(b.area/amax*100).toFixed(0)}%"></i></div></td>`;
    }
    rows += `</tr>`;
  });
  t.innerHTML = head + rows;
  scroll.appendChild(t); wrap.appendChild(scroll);

  if(!isFreq){
    const lg = document.createElement('div'); lg.className='legend';
    lg.innerHTML = `<span class="lg"><span class="sw" style="background:linear-gradient(90deg,var(--cyan),var(--amber))"></span>Utilisation (|σ|/limit)</span>
      <span class="lg"><span class="sw" style="background:var(--danger)"></span>Constraint violated</span>`;
    wrap.appendChild(lg);
  }
  return block('Member sections', bars.length + ' members · ' + META.n_vars + ' design variables', wrap);
}

/* ---------- RC design summary: variables + constraint utilisation ---------- */
function viewSectionsRC(ev){
  const wrap = document.createElement('div');

  // design variables
  const t1 = document.createElement('table'); t1.className='tbl';
  let r1 = `<tr><th>Design variable</th><th>Value</th><th>Unit</th></tr>`;
  (ev.variables||[]).forEach(v=>{
    const val = Math.abs(v.value) < 1 ? v.value.toFixed(3) : v.value.toFixed(1);
    r1 += `<tr><td style="color:var(--cyan-soft)">${v.name}</td>
           <td>${val}</td><td>${v.unit||'\u2014'}</td></tr>`;
  });
  t1.innerHTML = r1;
  wrap.appendChild(t1);

  // constraints with utilisation bars
  const hdr = document.createElement('div');
  hdr.style.cssText='margin:18px 0 8px;font-family:var(--font-mono);font-size:.72rem;letter-spacing:.16em;text-transform:uppercase;color:var(--fg-faint)';
  hdr.textContent = 'Constraint utilisation (demand / capacity)';
  wrap.appendChild(hdr);

  const t2 = document.createElement('table'); t2.className='tbl';
  let r2 = `<tr><th>Constraint</th><th>Demand</th><th>Capacity / limit</th><th>Util.</th><th style="min-width:130px"></th></tr>`;
  (ev.constraints||[]).forEach(c=>{
    const cls = c.ok ? '' : 'viol';
    const u = (c.util*100);
    r2 += `<tr>
      <td style="color:var(--cyan-soft)">${c.name}</td>
      <td>${c.demand.toFixed(2)} ${c.unit}</td>
      <td>${c.capacity.toFixed(2)} ${c.unit}</td>
      <td class="${cls}">${u.toFixed(0)}%</td>
      <td class="barcell"><div class="minibar"><i style="width:${Math.min(100,u).toFixed(0)}%;${c.ok?'':'background:var(--danger)'}"></i></div></td>
    </tr>`;
  });
  t2.innerHTML = r2;
  wrap.appendChild(t2);

  if(ev.quantities){
    const q = ev.quantities;
    const items = Object.keys(q).map(k=>`${k.replace(/_/g,' ')}: <b>${q[k].toFixed(2)}</b>`).join(' \u00b7 ');
    const note = document.createElement('div');
    note.className='note'; note.style.marginTop='14px';
    note.innerHTML = `Quantities \u2014 ${items}`;
    wrap.appendChild(note);
  }
  const nCon = (ev.constraints||[]).length;
  if(ev.details && ev.details.length){
    const t3 = document.createElement('table'); t3.className='tbl'; t3.style.marginTop='18px';
    let r3 = `<tr><th>Section property / design detail</th><th>Value</th><th>Unit</th></tr>`;
    ev.details.forEach(d=>{
      r3 += `<tr><td style="color:var(--cyan-soft)">${d.name}</td>
             <td>${d.value}</td><td class="dim">${d.unit||''}</td></tr>`;
    });
    t3.innerHTML = r3;
    const s3 = document.createElement('div'); s3.className='scroll'; s3.appendChild(t3);
    wrap.appendChild(s3);
  }
  return block('Design summary', META.n_vars + ' variables \u00b7 ' + nCon + ' constraints', wrap);
}

/* ============================================================
   3D MODEL  (three.js extruded view)
   ============================================================ */
function viewModel(){
  const host = document.createElement('div');
  const tb = document.createElement('div'); tb.className='toolbar';
  const isCO2 = META.family === 'co2' || META.family === 'member';
  const isMem = META.family === 'member';
  if(isCO2){
    tb.innerHTML = `
      <button class="tb on" data-mode="ghost">${isMem?'Plates':'Concrete'}: ghost</button>
      <button class="tb" data-mode="spin">⟳ Auto-rotate</button>`;
  } else {
    tb.innerHTML = `
      <button class="tb on" data-mode="stress">Colour: stress</button>
      <button class="tb" data-mode="group">Colour: group</button>
      <button class="tb" data-mode="spin">⟳ Auto-rotate</button>`;
  }
  const hostBox = document.createElement('div'); hostBox.id='three-host';
  hostBox.innerHTML = `<div class="vhint">drag to orbit · scroll to zoom</div><div class="hud" id="threeHud"></div>`;
  host.appendChild(tb); host.appendChild(hostBox);
  const note = document.createElement('div'); note.className='note amber';
  note.style.marginTop='14px';
  if(isMem){
    note.innerHTML = `The optimized built-up section is extruded over the full span with
       plate thicknesses to scale; orbit to inspect the flange-to-web proportions.`;
  } else if(isCO2){
    note.innerHTML = `Concrete is drawn translucent so the optimized reinforcement cage is
       visible. Bar count and diameter follow the optimized steel area; cycle the
       Concrete button (ghost → solid → hidden) to inspect the cage.`;
  } else {
    note.innerHTML = `Members are extruded with cross-section scaled to optimized area
       (radius ∝ √A). ${META.family==='frequency' ? 'Cyan spheres mark nonstructural masses.' : 'Warm hues indicate higher utilisation.'}`;
  }
  host.appendChild(note);

  // toolbar handlers (attached after insertion via timeout)
  setTimeout(()=>{
    tb.querySelectorAll('.tb').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        const mode = btn.dataset.mode;
        if(mode==='spin'){ btn.classList.toggle('on'); three.spin = btn.classList.contains('on'); return; }
        if(mode==='ghost'){
          // cycle concrete display: ghost -> solid -> hidden -> ghost
          const states = ['ghost','solid','hidden'];
          three.concState = states[(states.indexOf(three.concState||'ghost')+1)%3];
          btn.textContent = 'Concrete: ' + three.concState;
          applyConcreteState();
          return;
        }
        tb.querySelectorAll('[data-mode=stress],[data-mode=group]').forEach(b=>b.classList.remove('on'));
        btn.classList.add('on'); three.colorMode = mode; recolorThree();
      });
    });
  },0);
  return block('Optimized 3D model', isCO2 ? 'reinforcement cage · interactive' : 'extruded · interactive', host);
}

function applyConcreteState(){
  if(!three || !three.concMeshes) return;
  const st = three.concState || 'ghost';
  three.concMeshes.forEach(m=>{
    m.visible = st !== 'hidden';
    m.material.opacity = st === 'solid' ? 0.92 : 0.32;
  });
}

function disposeThree(){
  if(!three) return;
  cancelAnimationFrame(three.raf);
  if(three.renderer){ three.renderer.dispose(); three.renderer.forceContextLoss?.(); }
  three = null;
}

/* ---------- RC renderer: translucent concrete + rebar cage ---------- */
function initThreeRC(host, model){
  const W = host.clientWidth, H = 460;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, W/H, 0.01, 1e6);
  const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
  renderer.setPixelRatio(window.devicePixelRatio||1);
  renderer.setSize(W, H);
  host.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const d1 = new THREE.DirectionalLight(0xcfe9ff, 0.85); d1.position.set(1,1.4,1); scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xffd9a0, 0.4); d2.position.set(-1,-0.6,-0.8); scene.add(d2);

  // centre on the bounding box of all boxes
  let minx=1e12,maxx=-1e12,miny=1e12,maxy=-1e12,minz=1e12,maxz=-1e12;
  model.boxes.forEach(b=>{
    minx=Math.min(minx,b.cx-b.dx/2); maxx=Math.max(maxx,b.cx+b.dx/2);
    miny=Math.min(miny,b.cy-b.dy/2); maxy=Math.max(maxy,b.cy+b.dy/2);
    minz=Math.min(minz,b.cz-b.dz/2); maxz=Math.max(maxz,b.cz+b.dz/2);
  });
  const cx=(minx+maxx)/2, cy=(miny+maxy)/2, cz=(minz+maxz)/2;
  const ext = model.ext || Math.max(maxx-minx, maxy-miny, maxz-minz) || 1;

  const root = new THREE.Group(); scene.add(root);
  const concMeshes = [];
  model.boxes.forEach(b=>{
    const geo = new THREE.BoxGeometry(b.dx, b.dy, b.dz);
    let mat;
    if(b.role==='soil'){
      mat = new THREE.MeshStandardMaterial({color:0x8a7a5f, transparent:true,
        opacity:0.12, metalness:0.0, roughness:1.0, depthWrite:false});
    } else if(b.role==='column'){
      mat = new THREE.MeshStandardMaterial({color:0x9fb0c8, transparent:true,
        opacity:0.45, metalness:0.05, roughness:0.85, depthWrite:false});
    } else if(b.role==='steel'){
      mat = new THREE.MeshStandardMaterial({color:0x9aa9bd, transparent:true,
        opacity:0.85, metalness:0.55, roughness:0.35});
    } else {
      mat = new THREE.MeshStandardMaterial({color:0x9fb0c8, transparent:true,
        opacity:0.32, metalness:0.05, roughness:0.85, depthWrite:false});
    }
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(b.cx-cx, b.cy-cy, b.cz-cz);
    root.add(mesh);
    // crisp edge outline so the ghost volume reads clearly
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({color: b.role==='soil'?0x6a5d49:0x46c8d6,
        transparent:true, opacity: b.role==='soil'?0.25:0.55}));
    edges.position.copy(mesh.position);
    root.add(edges);
    if(b.role!=='soil'){ concMeshes.push(mesh); }
  });

  const rebarMat = new THREE.MeshStandardMaterial({color:0xc0584a, metalness:0.55, roughness:0.4});
  model.rebars.forEach(rb=>{
    const a = new THREE.Vector3(rb.x1-cx, rb.y1-cy, rb.z1-cz);
    const b2 = new THREE.Vector3(rb.x2-cx, rb.y2-cy, rb.z2-cz);
    const dir = new THREE.Vector3().subVectors(b2,a);
    const len = dir.length(); if(len < 1e-6) return;
    const rr = Math.max(rb.r, ext*0.0035);
    const geo = new THREE.CylinderGeometry(rr, rr, len, 10);
    const mesh = new THREE.Mesh(geo, rebarMat);
    mesh.position.copy(a).add(dir.clone().multiplyScalar(0.5));
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), dir.clone().normalize());
    root.add(mesh);
  });

  camera.position.set(0,0,ext*1.6);
  camera.lookAt(0,0,0);

  three = {scene,camera,renderer,root,meshes:[],host,smax:1,
           colorMode:'none', spin:false, ext, concMeshes, concState:'ghost',
           rot:{x:-0.35,y:0.7}, drag:false, lastX:0,lastY:0, dist:ext*1.6};
  setupControls();
  animate();
  const hud=document.getElementById('threeHud');
  if(hud) hud.innerHTML = `${model.rebars.length} reinforcement bars drawn<br>concrete translucent \u00b7 dims to scale`;
}

function initThree(){
  const host = document.getElementById('three-host');
  if(!host) return;
  disposeThree();
  const model = CURRENT.model;
  if(model.type === 'rc'){ initThreeRC(host, model); return; }
  const W = host.clientWidth, H = 460;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, W/H, 0.01, 1e6);
  const renderer = new THREE.WebGLRenderer({antialias:true, alpha:true});
  renderer.setPixelRatio(window.devicePixelRatio||1);
  renderer.setSize(W, H);
  host.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.62));
  const d1 = new THREE.DirectionalLight(0xcfe9ff, 0.8); d1.position.set(1,1.3,1); scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xffd9a0, 0.45); d2.position.set(-1,-0.5,-0.8); scene.add(d2);

  // compute model centre + scale
  const ns = model.nodes;
  const xs=ns.map(n=>n.x), ys=ns.map(n=>n.y), zs=ns.map(n=>n.z);
  const cx=(Math.min(...xs)+Math.max(...xs))/2;
  const cy=(Math.min(...ys)+Math.max(...ys))/2;
  const cz=(Math.min(...zs)+Math.max(...zs))/2;
  const ext = Math.max(
    Math.max(...xs)-Math.min(...xs),
    Math.max(...ys)-Math.min(...ys),
    Math.max(...zs)-Math.min(...zs)) || 1;

  const root = new THREE.Group(); scene.add(root);
  // model uses (x, y vertical for frames / z vertical for trusses).
  // We map structural up-axis to three.js +Y.
  const vertical = (model.ndm === 2) ? 'y' : 'z';
  function toVec(n){
    if(vertical==='y') return new THREE.Vector3(n.x-cx, n.y-cy, n.z-cz);
    return new THREE.Vector3(n.x-cx, n.z-cz, -(n.y-cy)); // z-up -> y-up
  }
  const nodeMap = {}; ns.forEach(n=> nodeMap[n.id]=n);

  // radius scaling for visual clarity
  const radii = model.members.map(m=>m.radius);
  const rmin=Math.min(...radii), rmax=Math.max(...radii);
  const visMin = ext*0.004, visMax = ext*0.022;
  function visR(r){
    const t = (rmax>rmin) ? (r-rmin)/(rmax-rmin) : 0.5;
    return visMin + t*(visMax-visMin);
  }
  // stress range
  const stresses = model.members.map(m=>m.stress).filter(s=>s!=null).map(Math.abs);
  const smax = stresses.length? Math.max(...stresses):1;

  const meshes = [];
  model.members.forEach(m=>{
    const a = toVec(nodeMap[m.i]), b = toVec(nodeMap[m.j]);
    const dir = new THREE.Vector3().subVectors(b,a);
    const len = dir.length();
    const geo = new THREE.CylinderGeometry(visR(m.radius), visR(m.radius), len, 14);
    const mat = new THREE.MeshStandardMaterial({metalness:0.35, roughness:0.55});
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(a).add(dir.clone().multiplyScalar(0.5));
    mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0), dir.clone().normalize());
    mesh.userData = m;
    root.add(mesh); meshes.push(mesh);
  });

  // node spheres (supports + masses)
  ns.forEach(n=>{
    if(n.fixed){
      const g=new THREE.SphereGeometry(ext*0.012,16,16);
      const mt=new THREE.MeshStandardMaterial({color:0x64758f,metalness:0.3,roughness:0.6});
      const s=new THREE.Mesh(g,mt); s.position.copy(toVec(n)); root.add(s);
    }
    if(n.mass){
      const g=new THREE.SphereGeometry(ext*0.02,18,18);
      const mt=new THREE.MeshStandardMaterial({color:0x46c8d6,emissive:0x16545c,metalness:0.2,roughness:0.4});
      const s=new THREE.Mesh(g,mt); s.position.copy(toVec(n)); root.add(s);
    }
  });

  camera.position.set(ext*0.9, ext*0.7, ext*1.4);
  camera.lookAt(0,0,0);

  three = {scene,camera,renderer,root,meshes,host,smax,
           colorMode:'stress', spin:false, ext,
           rot:{x:-0.3,y:0.6}, drag:false, lastX:0,lastY:0, dist:ext*1.75};
  recolorThree();
  setupControls();
  animate();
  updateHud();
}

function colorForStress(s, smax){
  // 0 -> cyan, 1 -> amber/red
  const t = Math.min(1, Math.abs(s)/(smax||1));
  const c1=[70,200,214], c2=[244,120,40];
  const r=Math.round(c1[0]+(c2[0]-c1[0])*t);
  const g=Math.round(c1[1]+(c2[1]-c1[1])*t);
  const b=Math.round(c1[2]+(c2[2]-c1[2])*t);
  return (r<<16)|(g<<8)|b;
}
const GROUP_COLORS = [0x46c8d6,0xf4a43c,0x5ec98a,0x9b8cff,0xef8e6a,0x6ab0ff,
  0xe6c84f,0xd66ab0,0x7fd6a0,0xc0a0ff,0xff9f6a,0x6ad6cf,0xb0d65e,0xd6a06a,0x8ab0e0,0xe07c9a];
function recolorThree(){
  if(!three) return;
  three.meshes.forEach(mesh=>{
    const m=mesh.userData;
    let col;
    if(three.colorMode==='group' && m.group!=null) col=GROUP_COLORS[(m.group-1)%GROUP_COLORS.length];
    else if(three.colorMode==='group' && m.role) col = m.role.includes('beam')?0xf4a43c:(m.role.includes('brace')?0x5ec98a:0x46c8d6);
    else if(m.stress!=null) col=colorForStress(m.stress, three.smax);
    else col = m.dist?0x46c8d6:0x8ea6c4;
    mesh.material.color.setHex(col);
  });
}

function setupControls(){
  const el = three.renderer.domElement;
  el.style.cursor='grab';
  el.addEventListener('mousedown',e=>{three.drag=true;three.lastX=e.clientX;three.lastY=e.clientY;el.style.cursor='grabbing';});
  window.addEventListener('mouseup',()=>{if(three){three.drag=false; if(three.renderer)three.renderer.domElement.style.cursor='grab';}});
  window.addEventListener('mousemove',e=>{
    if(!three||!three.drag)return;
    three.rot.y += (e.clientX-three.lastX)*0.008;
    three.rot.x += (e.clientY-three.lastY)*0.008;
    three.rot.x=Math.max(-1.4,Math.min(1.4,three.rot.x));
    three.lastX=e.clientX; three.lastY=e.clientY;
  });
  el.addEventListener('wheel',e=>{e.preventDefault();
    three.dist *= (1 + Math.sign(e.deltaY)*0.1);
    three.dist=Math.max(three.ext*0.4, Math.min(three.ext*5, three.dist));
  },{passive:false});
  // touch
  el.addEventListener('touchstart',e=>{if(e.touches.length===1){three.drag=true;three.lastX=e.touches[0].clientX;three.lastY=e.touches[0].clientY;}});
  el.addEventListener('touchmove',e=>{if(!three||!three.drag||e.touches.length!==1)return;
    three.rot.y+=(e.touches[0].clientX-three.lastX)*0.01;
    three.rot.x+=(e.touches[0].clientY-three.lastY)*0.01;
    three.lastX=e.touches[0].clientX; three.lastY=e.touches[0].clientY; e.preventDefault();},{passive:false});
  el.addEventListener('touchend',()=>{if(three)three.drag=false;});
}

function animate(){
  if(!three) return;
  three.raf = requestAnimationFrame(animate);
  if(three.spin && !three.drag) three.rot.y += 0.004;
  const {camera, root} = three;
  root.rotation.x = three.rot.x;
  root.rotation.y = three.rot.y;
  camera.position.set(0,0,three.dist);
  camera.lookAt(0,0,0);
  three.renderer.render(three.scene, camera);
}

function updateHud(){
  const hud=document.getElementById('threeHud'); if(!hud||!three)return;
  const m=CURRENT.model;
  if(m.type==='rc') return;   // RC hud set in initThreeRC
  hud.innerHTML = `${m.members.length} members · ${m.nodes.length} nodes<br>`+
    `radius ∝ √area · ${META.family==='frequency'?'modal':'static'} model`;
}

window.addEventListener('resize', ()=>{
  if(three && three.renderer){
    const host=document.getElementById('three-host'); if(!host)return;
    const W=host.clientWidth;
    three.camera.aspect=W/460; three.camera.updateProjectionMatrix();
    three.renderer.setSize(W,460);
  }
  if(CURRENT && activeViews().includes('fitness')) drawFitness();
});
