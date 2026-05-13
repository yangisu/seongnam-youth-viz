const D = window.SN_DATA || {};
const fmt = n => (n==null||Number.isNaN(Number(n))?'—':Number(n).toLocaleString('ko-KR'));
const pct = n => (n==null||Number.isNaN(Number(n))?'—':(Number(n)>=0?'+':'') + Number(n).toFixed(2) + '%');
const n2 = n => (n==null||Number.isNaN(Number(n))?'—':Number(n).toFixed(2));
function tableHtml(headers, rows){
  return '<thead><tr>'+headers.map(h=>`<th>${h}</th>`).join('')+'</tr></thead><tbody>'+
    rows.map(r=>'<tr>'+r.map(v=>`<td>${v}</td>`).join('')+'</tr>').join('')+'</tbody>';
}

const byRate = [...(D.dong||[])].sort((a,b)=>a['청년_순유출률']-b['청년_순유출률']);
const sectionOrder = ['ch-intro','ch1','ch2','ch4','ch-claim','ch3','ch5','ch0'];
sectionOrder.forEach(id => {
  const el = document.getElementById(id);
  if (el) document.body.appendChild(el);
});

const methodTrace = [
  ['CH1 WHAT', '동별 청년 순유출 hotspot 식별', 'youth_migration + youth_population + geojson', '(전출-전입)/청년인구*100 + 폴리곤 결합', '순유출 고위험 동을 1차 선별'],
  ['CH2 WHERE', '성남 내부 재배치 경로 식별', 'od_youth_intra_seongnam_dong', '동 OD -> 생활권 행렬 + 상위 경로 추출', '내부 이동 집중 통로 파악'],
  ['CH3 VALIDATION', '월별 상관 보조 검증', 'monthly OD + monthly complaints', '월집계 + 3/6/12개월 창 연관검정', '약한 상관 확인 후 중심 해석 축 전환'],
  ['CH4 MAIN EVIDENCE', '개입등급 + 신축/노후 지역군 비교', 'priority + policy_newold_axis/group/topic', '플래그 규칙/점수화 + 축 그룹 집계 + 토픽구성 비교', '정책 우선순위와 지역군별 구조 차이 해석'],
  ['CH4.5 CLAIM CHAIN', '주장-근거 연결 검증', 'claim_chain_*.csv/json', '주장→데이터→처리식→수치→한계 표준화', '논리적 비약/과장 해석 방지'],
  ['CH5 ITERATIVE', '반복형 피처엔지니어링 효과', 'iterative correlations/recommendations', 'iteration별 최고 신호 추적 + 상호작용 분해', '재평가 루프로 신호 강화 확인'],
];
document.getElementById('tbl-method-trace').innerHTML = tableHtml(
  ['분석', '무엇을 분석', '어떤 데이터', '어떻게 처리', '결과 의미'],
  methodTrace
);

// CH1 map
const map = L.map('map', { zoomControl: true, attributionControl: false }).setView([37.42, 127.13], 12);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', {subdomains:'abcd', maxZoom:19}).addTo(map);
const rates = (D.geo?.features||[]).map(f=>f.properties.rate).filter(v=>v!=null);
const vmax = Math.max(...rates.map(v=>Math.abs(v)), 1);
const colorFor = v => {
  if(v==null) return '#444';
  const t=Math.max(-1,Math.min(1,v/vmax));
  if(t>0){const a=t; return `rgb(${Math.round(127*a + 22*(1-a))},${Math.round(29*a + 24*(1-a))},${Math.round(29*a + 36*(1-a))})`;}
  const a=-t; return `rgb(${Math.round(30*a + 22*(1-a))},${Math.round(58*a + 24*(1-a))},${Math.round(138*a + 36*(1-a))})`;
};
let lockedDong=null;
const layer = L.geoJSON(D.geo, {
  style:f=>({color:'#0a0a0f',weight:0.8,fillColor:colorFor(f.properties.rate),fillOpacity:0.92}),
  onEachFeature:(f,l)=>{
    l.bindTooltip(`<b>${f.properties.dong}</b> (${f.properties.sgg_full||''})<br>순유출률: <b>${pct(f.properties.rate)}</b><br>청년 인구: ${fmt(f.properties.youth_pop)}명`,{sticky:true});
    l.on('mouseover',e=>{ if(!lockedDong) showDong(f.properties); e.target.setStyle({weight:2.5,color:'#facc15'});});
    l.on('mouseout',e=>{ if(!lockedDong) e.target.setStyle({weight:0.8,color:'#0a0a0f'});});
    l.on('click',()=>{ lockedDong=(lockedDong===f.properties.dong)?null:f.properties.dong; showDong(f.properties); });
  }
}).addTo(map);
map.fitBounds(layer.getBounds(), {padding:[10,10]});

function showDong(p){
  document.getElementById('dong-name').textContent = p.dong + (lockedDong===p.dong?' (고정)':'');
  document.getElementById('dong-sgg').textContent = p.sgg_full || '';
  const rateEl = document.getElementById('dong-rate');
  rateEl.textContent = pct(p.rate);
  rateEl.className = 'text-6xl font-black mb-6 ' + ((p.rate||0)>0 ? 'text-orange-400' : 'text-sky-400');
  document.getElementById('dong-in').textContent = fmt(p.youth_in);
  document.getElementById('dong-out').textContent = fmt(p.youth_out);
  document.getElementById('dong-pop').textContent = fmt(p.youth_pop);

  const intraTop = (D.od_intra||[])
    .filter(o=>o.origin_dong===p.dong)
    .sort((a,b)=>b.n-a.n)
    .slice(0,5);
  document.getElementById('dong-top-dest').innerHTML = intraTop.length===0
    ? '<li class="text-zinc-600">데이터 없음</li>'
    : intraTop.map(o=>`<li class="flex justify-between"><span>${o.dest_dong}</span><span class="text-zinc-500">${fmt(o.n)}명</span></li>`).join('');
}

// CH2 heatmap
const m = D.od_intra_matrix || [];
const oLabels = [...new Set(m.map(r=>r.origin_cluster))];
const dLabels = [...new Set(m.map(r=>r.dest_cluster))];
const z = oLabels.map(o => dLabels.map(d => {
  const r = m.find(x => x.origin_cluster===o && x.dest_cluster===d);
  return r ? Number(r.n) : 0;
}));
Plotly.newPlot('heat-intra', [{
  type:'heatmap',
  x:dLabels, y:oLabels, z,
  colorscale:'YlOrRd',
  hovertemplate:'출발 %{y}<br>도착 %{x}<br>이동 %{z}명<extra></extra>'
}], {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{tickangle:-30}, yaxis:{autorange:'reversed'},
  margin:{l:90,r:12,t:12,b:80}
},{displayModeBar:false});

const pairs = (D.od_intra_pairs||[]).slice(0,20);
const totalIntra = (D.od_intra||[]).reduce((acc,row)=>acc + Number(row.n||0), 0);
document.getElementById('tbl-pairs').innerHTML = tableHtml(
  ['순위','출발','도착','이동(명)','내부이동 비중(%)'],
  pairs.map((r,i)=>[
    i+1,
    r.origin_cluster,
    r.dest_cluster,
    fmt(r.n),
    totalIntra>0 ? n2(Number(r.n)/totalIntra*100) : '—'
  ])
);
const top3Pairs = pairs.slice(0,3).map(r=>`${r.origin_cluster}→${r.dest_cluster}`).join(', ');
document.getElementById('chapter2-meaning').innerHTML =
  top3Pairs
    ? `상위 이동쌍은 단순 순위가 아니라, 청년 재배치가 실제로 집중되는 “핵심 이동 통로”입니다. TOP3(<b>${top3Pairs}</b>)는 개입 우선 생활권과 연결해 원인-결과 경로를 설명하는 근거가 됩니다.`
    : '현재 월의 유의미한 상위 이동쌍이 충분하지 않습니다.';

// CH3 monthly
const city = (D.monthly_city||[]).slice().sort((a,b)=>String(a.month).localeCompare(String(b.month)));
const monthLab = city.map(r=>String(r.month).slice(0,4)+'-'+String(r.month).slice(4));
Plotly.newPlot('chart-monthly', [
  {type:'bar', x:monthLab, y:city.map(r=>Number(r.youth_net)), name:'순이동(명)', marker:{color:city.map(r=>Number(r.youth_net)>=0?'rgba(56,189,248,0.75)':'rgba(249,115,22,0.75)')}, yaxis:'y1'},
  {type:'scatter', mode:'lines+markers', x:monthLab, y:city.map(r=>Number(r.complaint_count)), name:'민원건수', line:{color:'#facc15',width:2}, marker:{size:6}, yaxis:'y2'}
], {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{gridcolor:'#252837'},
  yaxis:{title:'순이동(명)',gridcolor:'#252837',zerolinecolor:'#666'},
  yaxis2:{title:'민원건수',overlaying:'y',side:'right',showgrid:false},
  legend:{orientation:'h',y:1.1},
  margin:{l:60,r:60,t:10,b:50},
  shapes:[{type:'line',x0:0,x1:1,y0:0,y1:0,xref:'paper',line:{color:'#666',dash:'dash',width:1}}]
},{displayModeBar:false});

const horizonPoints = D.horizon_points || [];
const horizonAssoc = D.horizon_assoc || [];
const hStyles = {
  3: {name:'3개월', color:'rgba(249,115,22,0.72)', symbol:'circle'},
  6: {name:'6개월', color:'rgba(56,189,248,0.72)', symbol:'diamond'},
  12: {name:'12개월', color:'rgba(168,85,247,0.72)', symbol:'square'}
};
const lagTraces = [3,6,12].map(h=>{
  const sub = horizonPoints.filter(r=>Number(r.horizon_months)===h);
  const style = hStyles[h];
  return {
    type:'scatter', mode:'markers', name:style.name,
    x:sub.map(r=>Number(r.complaint_window)),
    y:sub.map(r=>Number(r.outflow_window)),
    text:sub.map(r=>`${r.dong_cluster} (${String(r.end_month).slice(0,4)}-${String(r.end_month).slice(4)})`),
    marker:{
      size:sub.map(()=>8),
      color:style.color,
      symbol:style.symbol,
      line:{width:1,color:'#0a0a0f'}
    },
    hovertemplate:'%{text}<br>민원강도(window): %{x:.2f}<br>순유출률(window): %{y:.2f}%<extra></extra>'
  };
}).filter(t=>t.x.length>0);
Plotly.newPlot('chart-lag', lagTraces, {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{title:'민원강도(총인구 1천명당, window 평균)',gridcolor:'#252837'},
  yaxis:{title:'청년 순유출률(window 평균, %)',gridcolor:'#252837'},
  margin:{l:60,r:10,t:10,b:50},
  legend:{orientation:'h',y:1.1}
},{displayModeBar:false});

const h3 = horizonAssoc.find(r=>Number(r.horizon_months)===3);
const h6 = horizonAssoc.find(r=>Number(r.horizon_months)===6);
const h12 = horizonAssoc.find(r=>Number(r.horizon_months)===12);
function hText(row){
  if (!row || row.status!=='ok') return '데이터 부족';
  const s = Math.abs(Number(row.spearman_r||0));
  const level = s>=0.3 ? '중간 이상' : (s>=0.1 ? '약함' : '매우 약함');
  return `${level} (r=${n2(row.spearman_r)}, p=${n2(row.spearman_p)}, n=${fmt(row.n)})`;
}
document.getElementById('lag-summary').innerHTML =
  `<b>핵심 해석:</b> 3개월=${hText(h3)} / 6개월=${hText(h6)} / 12개월=${hText(h12)}.<br>결론적으로 월별 동행은 보조적 신호이며, 본 분석의 주근거는 CH4의 지역군(신축·재정비/노후·정체) 구조 비교입니다.`;

const assoc = (D.horizon_assoc||[]).map(r=>[
  `${fmt(r.horizon_months)}개월`,
  fmt(r.n),
  r.status==='ok' ? n2(r.spearman_r) : '—',
  r.status==='ok' ? n2(r.slope) : '—',
  r.status==='ok' ? n2(r.r2) : '—',
  r.status==='ok' ? '분석 가능' : '데이터 부족'
]);
document.getElementById('tbl-monthly-assoc').innerHTML = tableHtml(
  ['기간창','표본수','Spearman r','기울기','R²','상태'],
  assoc
);

// CH4 evidence
const c = D.criteria || {};
const th = c.thresholds || {};
document.getElementById('tbl-criteria').innerHTML = tableHtml(
  ['항목','기준값'],
  [
    ['고유출 플래그', `유출률 >= ${n2(th.youth_outflow_rate_q70)}% (70분위)`],
    ['지속유출 플래그', `순유출 월비중 >= ${n2((th.negative_month_share_q70||0)*100)}% (70분위)`],
    ['고민원 플래그', `민원강도 >= ${n2(th.complaints_per_1000_totalpop_q60)} (60분위)`],
    ['A/B/C/D 규칙', '플래그 3/2/1/0개 충족']
  ]
);

const pri = (D.priority||[]).filter(r=>['A_즉시개입','B_우선개입'].includes(r.policy_tier)).slice(0,15);
document.getElementById('tbl-priority').innerHTML = tableHtml(
  ['생활권','등급','근거','유출률(%)','순유출월비중'],
  pri.map(r=>[r.dong_cluster, r.policy_tier, r.tier_reason, n2(r.youth_outflow_rate), n2(Number(r.negative_month_share)*100)+'%'])
);

const allPri = D.priority || [];
const tierOrder = ['A_즉시개입','B_우선개입','C_모니터링','D_유지'];
const tierColor = {'A_즉시개입':'#f97316','B_우선개입':'#f59e0b','C_모니터링':'#38bdf8','D_유지':'#64748b'};
const tierCounts = tierOrder.map(t => allPri.filter(r=>r.policy_tier===t).length);
const abTargets = allPri.filter(r=>['A_즉시개입','B_우선개입'].includes(r.policy_tier)).map(r=>String(r.dong_cluster||''));
const abPreview = abTargets.slice(0,8).join(', ');
document.getElementById('intro-conclusion').innerHTML =
  `이번 분석의 주근거는 <b>신축·재정비 vs 노후·정체 지역군 비교</b>입니다. ` +
  `민원강도-순유출률 월별 상관은 보조 검증으로 축소하고, 정책판단은 지역군 구조 차이와 개입등급으로 수행합니다.`;
document.getElementById('intro-priority').innerHTML =
  abTargets.length
    ? `<b>${abTargets.length}개</b> 생활권이 A/B에 해당합니다. ${abPreview}${abTargets.length>8?' ...':''}`
    : '현재 A/B 우선개입 대상이 식별되지 않았습니다.';
Plotly.newPlot('chart-tier-bar', [{
  type:'bar',
  x:tierOrder, y:tierCounts,
  marker:{color:tierOrder.map(t=>tierColor[t])},
  text:tierCounts.map(v=>String(v)), textposition:'outside',
  hovertemplate:'%{x}<br>%{y}개 생활권<extra></extra>'
}], {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{gridcolor:'#252837'}, yaxis:{title:'생활권 수',gridcolor:'#252837',dtick:1},
  margin:{l:55,r:10,t:20,b:40}
},{displayModeBar:false});

Plotly.newPlot('chart-tier-risk', tierOrder.map(t=>{
  const s = allPri.filter(r=>r.policy_tier===t);
  return {
    type:'scatter', mode:'markers', name:t,
    x:s.map(r=>Number(r.youth_outflow_rate)),
    y:s.map(r=>Number(r.negative_month_share)*100),
    text:s.map(r=>r.dong_cluster),
    marker:{color:tierColor[t], size:s.map(r=>Math.max(9, Number(r.complaints_per_1000_totalpop)*1.5)), line:{width:1,color:'#0a0a0f'}},
    hovertemplate:'%{text}<br>유출률 %{x:.2f}%<br>순유출월비중 %{y:.1f}%<extra></extra>'
  };
}), {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{title:'청년 순유출률(%)',gridcolor:'#252837'},
  yaxis:{title:'순유출 월 비중(%)',gridcolor:'#252837'},
  margin:{l:60,r:10,t:10,b:50},
  shapes:[
    {type:'line',x0:Number(th.youth_outflow_rate_q70||0),x1:Number(th.youth_outflow_rate_q70||0),y0:0,y1:1,yref:'paper',line:{color:'#f59e0b',dash:'dot',width:1}},
    {type:'line',x0:0,x1:1,xref:'paper',y0:Number(th.negative_month_share_q70||0)*100,y1:Number(th.negative_month_share_q70||0)*100,line:{color:'#f59e0b',dash:'dot',width:1}}
  ],
  legend:{orientation:'h',y:-0.2}
},{displayModeBar:false});

const axisOrder = ['신축·재정비', '노후·정체', '혼합/전이'];
const axisColor = {'신축·재정비':'#38bdf8','노후·정체':'#f97316','혼합/전이':'#94a3b8'};
const axisRows = (D.axis_findings || []).slice();
const axisSummary = (D.axis_summary || []).slice();
const axisChartTraces = axisOrder.map(label => {
  const vals = axisRows
    .filter(r => String(r.axis_type) === label)
    .map(r => Number(r.complaints_per_1000_totalpop))
    .filter(v => Number.isFinite(v));
  return {
    type:'box',
    name:label,
    y:vals,
    boxpoints:'all',
    jitter:0.35,
    pointpos:0,
    marker:{size:6,color:axisColor[label] || '#94a3b8',opacity:0.75},
    line:{color:axisColor[label] || '#94a3b8'},
    hovertemplate:`${label}<br>민원강도 %{y:.2f}<extra></extra>`
  };
}).filter(t => t.y.length > 0);
if (axisChartTraces.length){
  Plotly.newPlot('chart-axis-complaint', axisChartTraces, {
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Pretendard',color:'#f4f4f8',size:10},
    xaxis:{gridcolor:'#252837'},
    yaxis:{title:'민원강도(총인구 1천명당)',gridcolor:'#252837'},
    margin:{l:60,r:10,t:10,b:70},
    showlegend:false
  }, {displayModeBar:false});
}
document.getElementById('tbl-axis-findings').innerHTML = tableHtml(
  ['축 그룹','생활권 수','평균 민원강도','평균 유출률(%)','A/B 비중(%)'],
  axisSummary.map(r=>[
    String(r.axis_type || '-'),
    fmt(r.cluster_count),
    n2(r.mean_complaints_per_1000),
    n2(r.mean_outflow_rate),
    n2(r.ab_tier_share_pct)
  ])
);
document.getElementById('tbl-axis-regions').innerHTML = tableHtml(
  ['지역군', '포함 생활권(행정동 클러스터)'],
  axisOrder.map(label => {
    const members = [...new Set(axisRows.filter(r=>String(r.axis_type)===label).map(r=>String(r.dong_cluster||'')))]
      .filter(Boolean)
      .sort((a,b)=>a.localeCompare(b,'ko'));
    return [label, members.length ? members.join(', ') : '—'];
  })
);

const destLabel = {
  seoul_gangnam3: '서울 강남3구',
  seoul_other: '서울 기타',
  gyeonggi_near_core: '경기 인접핵심',
  gyeonggi_other: '경기 기타',
  outside_capital_region: '수도권 외'
};
const axisDestMix = (D.axis_dest_mix || []).slice();
const axisDestConc = (D.axis_dest_conc || []).slice();
const destBuckets = [...new Set(axisDestMix.map(r=>String(r.destination_bucket||'')))].filter(Boolean);
if (axisDestMix.length && destBuckets.length){
  const visibleGroups = ['신축·재정비', '노후·정체', '혼합/전이'];
  const traces = visibleGroups.map(g => {
    const sub = axisDestMix.filter(r=>String(r.axis_group_label||'')===g);
    return {
      type:'bar',
      name:g,
      x:destBuckets.map(b=>destLabel[b] || b),
      y:destBuckets.map(b=>{
        const row = sub.find(r=>String(r.destination_bucket||'')===b);
        return row ? Number(row.bucket_share)*100 : 0;
      }),
      hovertemplate:'%{x}<br>%{y:.2f}%<extra>'+g+'</extra>'
    };
  }).filter(t=>t.y.some(v=>v>0));
  Plotly.newPlot('chart-axis-dest-mix', traces, {
    barmode:'group',
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Pretendard',color:'#f4f4f8',size:10},
    xaxis:{gridcolor:'#252837'},
    yaxis:{title:'유출 비중(%)',gridcolor:'#252837'},
    margin:{l:60,r:10,t:10,b:60},
    legend:{orientation:'h',y:1.1}
  },{displayModeBar:false});
}
document.getElementById('tbl-axis-dest-concentration').innerHTML = tableHtml(
  ['지역군','주요 목적지','주요 목적지 비중(%)','편중도(HHI)'],
  axisDestConc
    .slice()
    .sort((a,b)=>Number(a.axis_group_order||99)-Number(b.axis_group_order||99))
    .map(r=>[
      String(r.axis_group_label || r.axis_group || '-'),
      destLabel[String(r.top_category||'')] || String(r.top_category||'-'),
      n2(Number(r.top_share||0)*100),
      n2(r.hhi)
    ])
);

const topicComp = (D.policy_newold_topic_comp || []).slice();
const topicDiff = topicComp
  .filter(r=>Number.isFinite(Number(r.share_diff_new_minus_old)))
  .sort((a,b)=>Math.abs(Number(b.share_diff_new_minus_old))-Math.abs(Number(a.share_diff_new_minus_old)))
  .slice(0,8);
if (topicDiff.length){
  Plotly.newPlot('chart-axis-topic-diff', [{
    type:'bar',
    orientation:'h',
    y:topicDiff.map(r=>String(r.topic_group)),
    x:topicDiff.map(r=>Number(r.share_diff_new_minus_old)*100),
    marker:{color:topicDiff.map(r=>Number(r.share_diff_new_minus_old)>=0 ? '#38bdf8' : '#f97316')},
    customdata:topicDiff.map(r=>[r.new_redevelopment_topic_share, r.old_stagnant_topic_share]),
    hovertemplate:'%{y}<br>신축-노후 비중차: %{x:.2f}%p<br>신축비중: %{customdata[0]:.3f}<br>노후비중: %{customdata[1]:.3f}<extra></extra>'
  }],{
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Pretendard',color:'#f4f4f8',size:10},
    xaxis:{title:'비중차 (신축·재정비 - 노후·정체, %p)',gridcolor:'#252837'},
    yaxis:{autorange:'reversed',gridcolor:'#252837'},
    margin:{l:110,r:20,t:10,b:50}
  },{displayModeBar:false});
}
const axisContext = D.axis_context_evidence || [];
document.getElementById('tbl-axis-context').innerHTML = tableHtml(
  ['출처', '근거 라벨', '근거 문구', '분석 매핑 축'],
  axisContext.map(r=>[
    String(r.source || '-'),
    String(r.evidence_label || '-'),
    String(r.evidence_text || '-'),
    String(r.mapped_axis || '-')
  ])
);

const topA = allPri.filter(r=>r.policy_tier==='A_즉시개입').slice(0,5).map(r=>r.dong_cluster);
const strongest = (D.policy_relations||[])[0];
document.getElementById('chapter4-conclusion').innerHTML = [
  `개입 등급 분포는 <b>A ${tierCounts[0]}개, B ${tierCounts[1]}개, C ${tierCounts[2]}개, D ${tierCounts[3]}개</b>입니다.`,
  `신축·재정비/노후·정체는 개별 동이 아니라, 동을 묶은 <b>지역군 분류</b>입니다.`,
  axisSummary.length ? `축 비교에서 민원강도 평균이 가장 높은 그룹은 <b>${axisSummary.slice().sort((a,b)=>Number(b.mean_complaints_per_1000)-Number(a.mean_complaints_per_1000))[0].axis_type}</b>입니다.` : '',
  topA.length ? `즉시개입(A) 우선 생활권은 <b>${topA.join(', ')}</b>입니다.` : '즉시개입(A) 생활권은 없습니다.',
  strongest ? `정책지표 중 유출률과 가장 강한 연관은 <b>${strongest.x_variable}</b> (Spearman r=${n2(strongest.spearman_r)}, p=${n2(strongest.spearman_p)})입니다.` : ''
].filter(Boolean).join('<br>');

const claimRowsRaw = (D.claim_chain_rows || []).slice();
const claimRows = claimRowsRaw.map(r => ({
  claim: String(r.claim ?? r.주장 ?? '-'),
  data_used: String(r.data_used ?? r.data ?? r.데이터 ?? '-'),
  processing_expr: String(r.processing_expr ?? r.processing ?? r.처리식 ?? '-'),
  result_value: String(r.result_value ?? r.result ?? r.결과수치 ?? '-'),
  limitation: String(r.limitation ?? r.한계 ?? '-'),
}));
const claimSources = (D.claim_chain_sources || []).filter(Boolean);
document.getElementById('claim-bridge').innerHTML =
  'CH4에서 제시한 지역군 근거를 그대로 결론으로 점프하지 않기 위해, 아래 Claim Chain에 각 주장별 데이터·처리식·수치·한계를 일렬로 공개합니다. ' +
  '즉, “무엇을 근거로 어디까지 말할 수 있는지”를 심사자가 바로 추적할 수 있도록 구성했습니다.';
document.getElementById('tbl-claim-chain').innerHTML = tableHtml(
  ['주장', '데이터', '처리식', '결과수치', '한계'],
  claimRows.length
    ? claimRows.map(r => [r.claim, r.data_used, r.processing_expr, r.result_value, r.limitation])
    : [[
      'claim_chain_*.csv 대기',
      claimSources.length ? claimSources.join(', ') : 'data/processed/claim_chain_*.csv',
      '-',
      '-',
      '현재 입력 파일이 없어 표를 생성하지 못했습니다.'
    ]]
);
document.getElementById('claim-guardrail').innerHTML =
  '<b>상관≠인과</b>: 본 사이트의 상관/회귀 수치는 정책 우선순위 참고 신호이며 인과효과를 단정하지 않습니다.<br>' +
  '<b>지역군 수준 해석</b>: 신축·재정비/노후·정체는 개별 동이 아닌 지역군 평균 경향으로, 개별 동 단위 판정에는 추가 검증이 필요합니다.';

const rel = (D.policy_relations||[]).slice(0,8);
if (rel.length){
  document.getElementById('tbl-tests').innerHTML = tableHtml(
    ['X 변수','Y 변수','Spearman r','p값'],
    rel.map(r=>[r.x_variable, r.y_variable, n2(r.spearman_r), n2(r.spearman_p)])
  );
} else {
  const tests = (D.tests||[]).slice(0,8);
  document.getElementById('tbl-tests').innerHTML = tableHtml(
    ['변수','Spearman r','p값','95% CI'],
    tests.map(r=>[r.variable, n2(r.spearman_r), n2(r.spearman_p), `${n2(r.spearman_ci_low)} ~ ${n2(r.spearman_ci_high)}`])
  );
}

const sens = D.sensitivity || [];
document.getElementById('tbl-sens').innerHTML = tableHtml(
  ['시나리오','TOP10 중복률','최대','최소'],
  sens.map(r=>[r.scenario, n2(Number(r.top10_overlap_with_base)*100)+'%', n2(r.max_rate), n2(r.min_rate)])
);

const vars = c.variables || {};
document.getElementById('tbl-vars').innerHTML = tableHtml(
  ['변수','의미'],
  Object.entries(vars).map(([k,v])=>[k,v])
);

// CH5 iterative loop
const iterSummary = D.iterative_summary || {};
const iterCorr = (D.iterative_corr || []).slice();
const iterReco = (D.iterative_reco || []).slice();
const iterLoop = (D.iterative_loop_progress || []).slice().sort((a,b)=>Number(a.iteration)-Number(b.iteration));

document.getElementById('tbl-iterative-summary').innerHTML = tableHtml(
  ['항목', '값'],
  [
    ['품질 판정', String(iterSummary.quality || '-')],
    ['목표 임계치', iterSummary.threshold == null ? '-' : n2(iterSummary.threshold)],
    ['반복 횟수', iterSummary.iterations_run == null ? '-' : fmt(iterSummary.iterations_run)],
    ['최종 최적 피처', String(iterSummary.best_feature || '-')],
    ['최고 절대 Spearman', iterSummary.best_abs_spearman_r == null ? '-' : n2(iterSummary.best_abs_spearman_r)],
  ]
);

if (iterLoop.length){
  Plotly.newPlot('chart-iter-loop', [{
    type:'scatter',
    mode:'lines+markers',
    x:iterLoop.map(r=>`Iter ${fmt(r.iteration)}`),
    y:iterLoop.map(r=>Number(r.best_abs_spearman_r)),
    marker:{size:9,color:'#facc15'},
    line:{width:3,color:'#f97316'},
    text:iterLoop.map(r=>String(r.best_feature || '-')),
    hovertemplate:'%{x}<br>best abs r=%{y:.3f}<br>feature=%{text}<extra></extra>'
  }], {
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Pretendard',color:'#f4f4f8',size:10},
    xaxis:{gridcolor:'#252837'},
    yaxis:{title:'best abs(Spearman r)',gridcolor:'#252837'},
    margin:{l:60,r:10,t:10,b:45},
    shapes: iterSummary.threshold == null ? [] : [{
      type:'line', x0:0, x1:1, xref:'paper',
      y0:Number(iterSummary.threshold), y1:Number(iterSummary.threshold),
      line:{color:'#38bdf8',dash:'dash',width:1}
    }]
  }, {displayModeBar:false});
}

document.getElementById('tbl-iter-loop').innerHTML = tableHtml(
  ['반복', '최고 피처', '최고 abs r', '이전 대비 Δ', '검토 피처수'],
  iterLoop.map(r=>[
    fmt(r.iteration),
    String(r.best_feature || '-'),
    n2(r.best_abs_spearman_r),
    r.delta_from_prev == null || Number.isNaN(Number(r.delta_from_prev))
      ? '-'
      : (Number(r.delta_from_prev) >= 0 ? '+' : '') + n2(r.delta_from_prev),
    fmt(r.features_tested),
  ])
);

const iterTop = iterCorr
  .sort((a,b)=>Number(b.abs_spearman_r||0)-Number(a.abs_spearman_r||0))
  .slice(0,10);
if (iterTop.length){
  Plotly.newPlot('chart-iter-top', [{
    type:'bar',
    x:iterTop.map(r=>String(r.feature)),
    y:iterTop.map(r=>Number(r.abs_spearman_r)),
    marker:{color:iterTop.map(r=>String(r.stage).includes('engineered') ? '#f97316' : '#38bdf8')},
    customdata:iterTop.map(r=>[r.stage, r.iteration, r.n, r.spearman_r]),
    hovertemplate:'%{x}<br>abs_r=%{y:.3f}<br>stage=%{customdata[0]}<br>iter=%{customdata[1]}<br>n=%{customdata[2]}<br>r=%{customdata[3]:.3f}<extra></extra>'
  }],{
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Pretendard',color:'#f4f4f8',size:10},
    xaxis:{tickangle:-35,gridcolor:'#252837'},
    yaxis:{title:'abs(Spearman r)',gridcolor:'#252837'},
    margin:{l:55,r:10,t:10,b:120}
  },{displayModeBar:false});
}

const bestInteraction = iterCorr.find(r=>String(r.feature||'').includes('__x__'));
if (bestInteraction){
  const parts = String(bestInteraction.feature).split('__x__');
  const left = parts[0];
  const right = parts[1];
  const points = (D.priority||[])
    .filter(r => Number.isFinite(Number(r[left])) && Number.isFinite(Number(r[right])) && Number.isFinite(Number(r.youth_outflow_rate)));
  if (points.length){
    Plotly.newPlot('chart-iter-interaction', [{
      type:'scatter',
      mode:'markers',
      x:points.map(r=>Number(r[left])),
      y:points.map(r=>Number(r[right])),
      text:points.map(r=>String(r.dong_cluster||'')),
      marker:{
        size:points.map(r=>Math.max(8, Math.abs(Number(r.youth_outflow_rate))*2)),
        color:points.map(r=>Number(r.youth_outflow_rate)),
        colorscale:'YlOrRd',
        showscale:true,
        colorbar:{title:'outflow'}
      },
      hovertemplate:'%{text}<br>'+left+': %{x:.3f}<br>'+right+': %{y:.3f}<extra></extra>'
    }],{
      paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
      font:{family:'Pretendard',color:'#f4f4f8',size:10},
      xaxis:{title:left,gridcolor:'#252837'},
      yaxis:{title:right,gridcolor:'#252837'},
      margin:{l:60,r:20,t:10,b:55}
    },{displayModeBar:false});
  }
}

document.getElementById('tbl-iter-reco').innerHTML = tableHtml(
  ['feature', 'recommended visual', 'reason'],
  iterReco.slice(0,8).map(r=>[String(r.feature||'-'), String(r.recommended_visual||'-'), String(r.reason||'-')])
);

if (byRate.length){
  const target = byRate[byRate.length-1].dong;
  const feat = (D.geo?.features||[]).find(f=>f.properties.dong===target);
  if (feat) showDong(feat.properties);
}
