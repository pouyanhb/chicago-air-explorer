/* Chicago Air Explorer — independently published Open Air Chicago sensor data.
   UTC-day aggregates are used for historical graphs; never infer local Chicago-day
   compliance, population exposure, or source attribution from these readings. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = {daily:null, recent:null, manifest:null, pollutant:'pm25', period:'90', tab:'overview', selection:[], mapMode:'daily', charts:{}, map:null, layer:null, dayRows:new Map(), idToIndex:new Map(), sensorById:new Map()};
  const COLORS = ['#b2efd1','#edc591','#9bc3ef','#e69da8','#b9a5ed'];
  const KEY = {pm25:2,no2:3};
  const UNITS = {pm25:'µg/m³',no2:'ppb'};
  const htmlEscape = x => String(x ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (n, decimals=1) => Number.isFinite(n) ? Number(n).toFixed(decimals) : '—';
  const mean = a => a.length ? a.reduce((s,v)=>s+v,0)/a.length : null;
  const dateFrom = s => new Date(`${s}T00:00:00Z`);
  const dateFmt = s => s ? new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',year:'numeric',timeZone:'UTC'}).format(dateFrom(s)) : '—';
  const dateSmall = s => s ? new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',timeZone:'UTC'}).format(dateFrom(s)) : '—';
  const localHour = s => s ? new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric',hour:'numeric',timeZone:'America/Chicago',timeZoneName:'short'}).format(new Date(`${s}Z`)) : 'Unavailable';
  const pollLabel = () => state.pollutant==='pm25'?'PM2.5':'NO₂';
  const rgba = (hex, alpha) => {const z=hex.slice(1);const r=parseInt(z.slice(0,2),16),g=parseInt(z.slice(2,4),16),b=parseInt(z.slice(4,6),16);return `rgba(${r},${g},${b},${alpha})`;};
  function loadJson(path) { return fetch(path+'?v='+Math.floor(Date.now()/3600000),{cache:'no-store'}).then(r=>{if(!r.ok)throw new Error(`Missing ${path} (HTTP ${r.status})`);return r.json();}); }
  async function initialize() {
    wireControls(); setupMap();
    try {
      const [d,m] = await Promise.all([loadJson('data/daily.json'),loadJson('data/manifest.json')]);
      if (d.version!==1 || !Array.isArray(d.rows) || !d.rows.length) throw new Error('Published daily readings not yet available.');
      state.daily=d;state.manifest=m;
      try { state.recent=await loadJson('data/recent.json'); } catch(_){ state.recent=null; }
      prepareIndexes(); chooseExamples(); refreshAll();
      const age=(Date.now()-new Date(m.generated_at).getTime())/3600000;
      $('feedStatus').textContent=age>36?'Update is overdue':'Public data connected';
      $('feedDate').textContent=`Latest UTC day: ${m.latest_utc_day||'unknown'}`;
      $('timestampTop').textContent=`Latest published UTC day: ${m.latest_utc_day||'unknown'}`;
      $('footerUpdate').textContent=`Last update check: ${new Date(m.generated_at).toLocaleString('en-US',{dateStyle:'medium',timeStyle:'short'})} · Non-regulatory`;
    } catch(err) {
      $('loadError').hidden=false;
      $('loadError').textContent=`The website is ready, but its public-data snapshot has not been generated yet. Run the “Update Chicago air data and deploy” GitHub Action to populate it. Details: ${err.message}`;
      $('feedStatus').textContent='Awaiting first data import';
      $('feedDate').textContent='No measurements are being displayed';
      renderNoData();
    }
  }
  function prepareIndexes(){
    const d=state.daily;d.sensors.forEach((s,i)=>{state.idToIndex.set(s.id,i);state.sensorById.set(s.id,s);state.dayRows.set(s.id,new Map());});
    d.rows.forEach(([di,si,p,n])=>{const id=d.sensors[si]?.id;if(id!=null)state.dayRows.get(id).set(di,[p,n]);});
  }
  function chooseExamples(){
    if (!state.daily)return;
    const sorted=[...state.daily.sensors].sort((a,b)=>(b.days_pm||0)-(a.days_pm||0));
    const used=new Set();const result=[];
    for(const sensor of sorted){
      if(sensor.days_pm<10)continue;
      const key=sensor.name.replace(/\s+\d+$/,'').toLowerCase();
      if(used.has(key))continue;
      used.add(key);result.push(sensor.id);
      if(result.length>=5)break;
    }
    state.selection=result;
  }
  function daysInPeriod(){
    if(!state.daily)return [];
    const dates=state.daily.dates;
    if(state.period==='all')return dates.map((_,i)=>i);
    const max=dateFrom(dates[dates.length-1]).getTime();const min=max-(Number(state.period)-1)*86400000;
    return dates.map((d,i)=>dateFrom(d).getTime()>=min?i:null).filter(v=>v!==null);
  }
  function valid(val){return typeof val==='number'&&Number.isFinite(val);}
  function pollIndex(){return state.pollutant==='pm25'?0:1;}
  function dailyRowsForSensor(id){return state.dayRows.get(id)||new Map();}
  function getNetwork(){const allowed=new Set(daysInPeriod());return state.daily.network.filter(r=>allowed.has(r[0]));}
  function wireControls(){
    document.querySelectorAll('[data-tab]').forEach(btn=>btn.addEventListener('click',()=>switchTab(btn.dataset.tab)));
    document.querySelectorAll('[data-jump]').forEach(btn=>btn.addEventListener('click',()=>switchTab(btn.dataset.jump)));
    document.querySelectorAll('[data-poll]').forEach(btn=>btn.addEventListener('click',()=>{state.pollutant=btn.dataset.poll;document.querySelectorAll('[data-poll]').forEach(b=>b.classList.toggle('selected',b===btn));refreshAll();}));
    document.querySelectorAll('[data-period]').forEach(btn=>btn.addEventListener('click',()=>{state.period=btn.dataset.period;document.querySelectorAll('[data-period]').forEach(b=>b.classList.toggle('active',b===btn));refreshAll();}));
    $('mapMode').addEventListener('change',e=>{state.mapMode=e.target.value;renderMap();});
    $('sensorSearch').addEventListener('input',showSuggestions);
    $('sensorSearch').addEventListener('focus',showSuggestions);
    document.addEventListener('click',e=>{if(!e.target.closest('.sensor-search'))$('sensorSuggestions').hidden=true;});
    $('resetSensors').addEventListener('click',()=>{chooseExamples();renderCompare();});
    $('clearSensors').addEventListener('click',()=>{state.selection=[];renderCompare();});
    $('exportCompare').addEventListener('click',exportCompareCSV);
  }
  function switchTab(tab){
    state.tab=tab;
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));
    document.querySelectorAll('.panel').forEach(el=>el.classList.toggle('active',el.id===`panel-${tab}`));
    $('sectionLabel').textContent={overview:'OVERVIEW',trends:'LONG-TERM TRENDS',compare:'COMPARE SENSORS',methods:'DATA & METHODS'}[tab];
    if(!state.daily)return;
    if(tab==='overview'){setTimeout(()=>{state.map?.invalidateSize();renderOverview();},25);}
    if(tab==='trends')setTimeout(renderTrends,25);
    if(tab==='compare')setTimeout(renderCompare,25);
    if(tab==='methods')renderMethods();
  }
  function refreshAll(){if(!state.daily)return;renderOverviewStats();
    if(state.tab==='overview'){renderOverview();}
    if(state.tab==='trends')renderTrends();
    if(state.tab==='compare')renderCompare();
    if(state.tab==='methods')renderMethods();
  }
  function renderNoData(){ if(state.map){state.map.invalidateSize();} }
  function setupMap(){
    if(typeof L==='undefined'){ $('map').textContent='Map library could not load. Internet access is required for map tiles.';return; }
    state.map=L.map('map',{zoomControl:false,scrollWheelZoom:false}).setView([41.87,-87.68],10.5);
    L.control.zoom({position:'bottomright'}).addTo(state.map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors © CARTO'}).addTo(state.map);
    state.layer=L.layerGroup().addTo(state.map);
  }
  function chart(id, type, labels, datasets, options={}){
    if(typeof Chart==='undefined')return;
    if(state.charts[id])state.charts[id].destroy();
    const el=$(id);if(!el)return;
    state.charts[id]=new Chart(el,{type,data:{labels,datasets},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:datasets.length>1,position:'bottom',labels:{color:'#a9c0b7',boxWidth:11,font:{size:10}}},tooltip:{backgroundColor:'#172824',titleColor:'#fff',bodyColor:'#c6e1d3',borderColor:'#3d6254',borderWidth:1}},scales:{x:{grid:{display:false},ticks:{color:'#829e98',maxTicksLimit:7,maxRotation:0,font:{size:10}}},y:{grid:{color:'#2d413e'},ticks:{color:'#829e98',font:{size:10}},beginAtZero:true}},...options}});
  }
  function lineDataset(label,values,color,extra={}){return {label,data:values,borderColor:color,backgroundColor:rgba(color,.10),fill:false,pointRadius:0,pointHoverRadius:4,borderWidth:2,tension:.2,spanGaps:false,...extra};}
  function renderOverviewStats(){
    const net=state.daily.network;const idx=state.pollutant==='pm25'?1:2;const countIdx=state.pollutant==='pm25'?3:4;
    const threshold=Math.max(15,Math.floor(state.daily.sensors.length*.15));
    const latest=[...net].reverse().find(r=>r[countIdx]>=threshold) || [...net].reverse().find(r=>valid(r[idx]));
    const rows=getNetwork().filter(r=>valid(r[idx]));
    $('statAvg').textContent=fmt(latest?.[idx]);$('statUnit').textContent=UNITS[state.pollutant];
    $('statCount').textContent=latest?.[countIdx]??'—';$('statDay').textContent=latest?dateSmall(state.daily.dates[latest[0]]):'—';
    $('statAvgSub').textContent=latest?`For ${dateFmt(state.daily.dates[latest[0]])} (UTC)`:'No eligible day';
    $('statPeriod').textContent=fmt(mean(rows.map(r=>r[idx])));
    $('statPeriodUnit').textContent=UNITS[state.pollutant];
    $('statPeriodSub').textContent=`Mean of ${rows.length} available network UTC days`;
    $('overviewUnit').textContent=$('trendUnit').textContent=$('compareUnit').textContent=UNITS[state.pollutant];
  }
  function renderOverview(){renderOverviewStats();if(state.map){state.map.invalidateSize();renderMap();}
    const rows=getNetwork();const col=state.pollutant==='pm25'?1:2;
    chart('overviewChart','line',rows.map(r=>dateSmall(state.daily.dates[r[0]])),[lineDataset(pollLabel(),rows.map(r=>r[col]),'#b4efd4',{fill:true})]);
    $('overviewNote').textContent=`Equal-sensor daily means · ${rows.length} dates · Daily times are UTC · ${pollLabel()} (${UNITS[state.pollutant]})`;
    if(state.recent?.hours?.length){const hrs=state.recent.hours;const last=state.recent.network.slice(-36);const selected=state.pollutant==='pm25'?1:2;
      chart('hourlyChart','line',last.map(r=>localHour(hrs[r[0]])),[lineDataset(pollLabel(),last.map(r=>r[selected]),'#edc591')],{scales:{x:{display:false},y:{display:false}}});
      $('hourlyTag').textContent=`Last stored: ${localHour(hrs[hrs.length-1])}`;
    } else {$('hourlyTag').textContent='Hourly API not yet available';if(state.charts.hourlyChart){state.charts.hourlyChart.destroy();delete state.charts.hourlyChart;}}
  }
  function quantile(values,q){if(!values.length)return null;const sorted=[...values].sort((a,b)=>a-b);return sorted[Math.round(q*(sorted.length-1))];}
  function renderMap(){
    if(!state.layer||!state.daily)return;
    state.layer.clearLayers();$('mapSensorDetail').hidden=true;
    const col=pollIndex();let rows=[];let basis='';
    if(state.mapMode==='hourly'){
      if(state.recent?.map_hour){rows=state.recent.map_rows.map(([id,pm,no])=>({id,value:[pm,no][col]}));basis=`UTC hour: ${state.recent.map_hour.slice(0,16)} · ${localHour(state.recent.map_hour)}`;}
      else {basis='No comparable hourly snapshot available; choose daily.';}
    } else if(state.mapMode==='daily'){
      const cntCol=state.pollutant==='pm25'?3:4;
      const threshold=Math.max(15,Math.floor(state.daily.sensors.length*.15));
      const latest=[...state.daily.network].reverse().find(r=>r[cntCol]>=threshold) || [...state.daily.network].reverse().find(r=>r[cntCol]>0);
      if(latest){const di=latest[0];state.daily.sensors.forEach(s=>{const pair=dailyRowsForSensor(s.id).get(di);if(pair)rows.push({id:s.id,value:pair[col]});});basis=`Published UTC day: ${state.daily.dates[di]}`;}
    } else {
      const days=daysInPeriod();const eligible=Math.max(1,Math.ceil(days.length*.75));
      state.daily.sensors.forEach(s=>{const vals=days.map(i=>dailyRowsForSensor(s.id).get(i)?.[col]).filter(valid);if(vals.length>=eligible)rows.push({id:s.id,value:mean(vals),count:vals.length});});
      basis=`Observed mean over ${days.length} available UTC days; ≥75% reporting required`;
    }
    rows=rows.filter(r=>valid(r.value)&&state.sensorById.has(r.id));
    const v=rows.map(r=>r.value);const low=quantile(v,.25), high=quantile(v,.75);
    for(const r of rows){
      const s=state.sensorById.get(r.id);if(!Number.isFinite(s.lat)||!Number.isFinite(s.lon))continue;
      const color=r.value<=low?'#79c7af':r.value>=high?'#e4a18e':'#f1c68d';
      const circle=L.circleMarker([s.lat,s.lon],{radius:6,weight:1,color:'#142825',fillColor:color,fillOpacity:.94});
      circle.bindTooltip(`${htmlEscape(s.name)}<br>${fmt(r.value)} ${UNITS[state.pollutant]}`,{direction:'top'});
      circle.on('click',()=>{
        const panel=$('mapSensorDetail');panel.hidden=false;
        panel.innerHTML=`<div><b>${htmlEscape(s.name)}</b><span>${pollLabel()}: ${fmt(r.value)} ${UNITS[state.pollutant]} · ${htmlEscape(basis)}${s.coord_warning?' · Location change flagged':''}</span></div><button type="button" id="addMapSensor">Compare this sensor</button>`;
        $('addMapSensor').addEventListener('click',()=>{addSensor(s.id);switchTab('compare');});
      });circle.addTo(state.layer);
    }
    $('mapBasis').textContent=`${rows.length} plotted · ${basis}`;
  }
  function renderTrends(){const rows=getNetwork();const col=state.pollutant==='pm25'?1:2;const ncol=state.pollutant==='pm25'?3:4;const labels=rows.map(r=>dateSmall(state.daily.dates[r[0]]));
    chart('trendsChart','line',labels,[lineDataset(pollLabel(),rows.map(r=>r[col]),'#b4efd4',{fill:true})]);
    chart('coverageChart','bar',labels,[{label:'Reporting sensors',data:rows.map(r=>r[ncol]),backgroundColor:'#678f85',borderRadius:2,maxBarThickness:8}],{plugins:{legend:{display:false}}});
    const days=daysInPeriod(),minDays=Math.max(1,Math.ceil(days.length*.75));
    const vals=state.daily.sensors.map(s=>{const a=days.map(i=>dailyRowsForSensor(s.id).get(i)?.[pollIndex()]).filter(valid);return {s,mean:mean(a),n:a.length};}).filter(x=>x.n>=minDays).sort((a,b)=>b.mean-a.mean);
    $('rankingTable').innerHTML=vals.length?vals.slice(0,18).map(x=>`<tr><td>${htmlEscape(x.s.name)}</td><td>${fmt(x.mean)} ${UNITS[state.pollutant]}</td><td>${x.n} of ${days.length}</td><td>${x.s.coord_warning?'Location changed; review':'Observed sensor only'}</td></tr>`).join(''):'<tr><td colspan="4">Not enough sufficiently complete sensors in this period.</td></tr>';
  }
  function showSuggestions(){if(!state.daily)return;const q=$('sensorSearch').value.trim().toLowerCase();const remaining=state.daily.sensors.filter(s=>!state.selection.includes(s.id)&&(q?s.name.toLowerCase().includes(q)||s.id.toLowerCase().includes(q):true)).slice(0,12);
    $('sensorSuggestions').replaceChildren();if(state.selection.length>=5||!remaining.length){$('sensorSuggestions').hidden=true;return;}
    remaining.forEach(s=>{const btn=document.createElement('button');btn.className='suggestion-btn';btn.type='button';const name=document.createElement('span');name.textContent=s.name;const detail=document.createElement('small');detail.textContent=`${s.days_pm} PM2.5 days`;btn.append(name,detail);btn.addEventListener('click',()=>addSensor(s.id));$('sensorSuggestions').append(btn);});
    $('sensorSuggestions').hidden=false;
  }
  function addSensor(id){if(!state.daily||state.selection.includes(id)||state.selection.length>=5)return;state.selection.push(id);$('sensorSearch').value='';$('sensorSuggestions').hidden=true;renderCompare();}
  function removeSensor(id){state.selection=state.selection.filter(s=>s!==id);renderCompare();}
  function matchedData(){const selected=state.selection.filter(id=>state.dayRows.has(id));const col=pollIndex();const days=daysInPeriod();const shared=days.filter(i=>selected.length&&selected.every(id=>valid(dailyRowsForSensor(id).get(i)?.[col])));
    return {selected,days:shared,series:selected.map(id=>shared.map(i=>dailyRowsForSensor(id).get(i)[col]))};}
  function renderCompare(){if(!state.daily)return;
    const selected=state.selection;$('selectedCount').textContent=`${selected.length} / 5`;
    $('sensorChips').replaceChildren();selected.forEach((id,i)=>{const s=state.sensorById.get(id);if(!s)return;const chip=document.createElement('div');chip.className='sensor-chip';chip.style.borderColor=COLORS[i];const label=document.createElement('span');label.textContent=s.name;const del=document.createElement('button');del.textContent='×';del.setAttribute('aria-label',`Remove ${s.name}`);del.addEventListener('click',()=>removeSensor(id));chip.append(label,del);$('sensorChips').append(chip);});
    const m=matchedData();const labels=m.days.map(i=>dateSmall(state.daily.dates[i]));
    chart('compareChart','line',labels,m.selected.map((id,j)=>lineDataset(state.sensorById.get(id).name,m.series[j],COLORS[j])),{plugins:{legend:{display:true,position:'bottom',labels:{color:'#b1c6bf',font:{size:10},boxWidth:10}}}});
    $('compareNote').textContent=m.selected.length?`${m.days.length} shared valid UTC days across ${m.selected.length} sensors · ${pollLabel()} (${UNITS[state.pollutant]})`:'Select at least one sensor.';
    const averages=m.series.map(mean),group=mean(averages.filter(valid));
    $('compareTable').innerHTML=m.selected.length?m.selected.map((id,j)=>`<tr><td>${htmlEscape(state.sensorById.get(id).name)}</td><td>${fmt(averages[j])} ${UNITS[state.pollutant]}</td><td>${m.days.length}</td><td>${valid(group)&&valid(averages[j])?(averages[j]-group>=0?'+':'')+fmt(averages[j]-group):'—'} ${UNITS[state.pollutant]}</td></tr>`).join(''):'<tr><td colspan="4">Select sensors to begin.</td></tr>';
    renderScatter();
  }
  function correlation(points){if(points.length<3)return null;const mx=mean(points.map(p=>p.x)),my=mean(points.map(p=>p.y));let sx=0,sy=0,sxy=0;for(const p of points){const x=p.x-mx,y=p.y-my;sx+=x*x;sy+=y*y;sxy+=x*y;}return sx>0&&sy>0?sxy/Math.sqrt(sx*sy):null;}
  function renderScatter(){
    const first=state.selection[0];const days=daysInPeriod();let points=[];
    if(first)points=days.map(i=>dailyRowsForSensor(first).get(i)).filter(r=>r&&valid(r[0])&&valid(r[1])).map(r=>({x:r[0],y:r[1]}));
    const r=correlation(points);
    chart('scatterChart','scatter',[],[{label:first?state.sensorById.get(first).name:'Select a sensor',data:points,pointRadius:3,pointBackgroundColor:rgba('#9bc3ef',.85),showLine:false}],{interaction:{mode:'nearest',intersect:true},plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`PM2.5: ${fmt(ctx.raw.x)} µg/m³, NO₂: ${fmt(ctx.raw.y)} ppb`}}},scales:{x:{type:'linear',title:{display:true,text:'PM2.5 (µg/m³)',color:'#a5bdb4'},grid:{color:'#2d413e'},ticks:{color:'#92aaa5'}},y:{title:{display:true,text:'NO₂ (ppb)',color:'#a5bdb4'},grid:{color:'#2d413e'},ticks:{color:'#92aaa5'}}}});
    $('scatterNote').textContent=first?`${state.sensorById.get(first).name}: ${points.length} matched pollutant days · Pearson r = ${valid(r)?fmt(r,2):'not available'}. Association is not causation.`:'Choose a sensor to view PM2.5 versus NO₂ on matching UTC days.';
  }
  function exportCompareCSV(){const m=matchedData();if(!m.days.length)return;const header=['utc_date',...m.selected.map(id=>`${state.sensorById.get(id).name.replaceAll(',',' ')} (${state.pollutant})`)];const lines=[header,...m.days.map((i,k)=>[state.daily.dates[i],...m.series.map(a=>a[k])])];
    const content=lines.map(row=>row.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\n');const blob=new Blob([content],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`chicago-air-${state.pollutant}-matched-utc-days.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function renderMethods(){if(!state.manifest)return;const m=state.manifest;const items=[['Last update check',new Date(m.generated_at).toLocaleString()],['Latest UTC day',m.latest_utc_day||'—'],['Latest recorded UTC hour',m.latest_utc_hour||'Not available'],['Sensors in snapshot',m.sensor_count||'—'],['Daily sensor observations',(m.daily_records||0).toLocaleString()],['Hourly fetch status',m.hourly_refresh_error?'Last hourly attempt failed':'No reported error']];$('provenanceGrid').innerHTML=items.map(([label,v])=>`<div class="provenance-item"><span>${htmlEscape(label)}</span><b>${htmlEscape(v)}</b></div>`).join('');}
  window.addEventListener('DOMContentLoaded', initialize);
})();
