let key=null,doc=null,current=null,timer=null,page=1;
const $=id=>document.getElementById(id);
async function api(url,options={}){const r=await fetch(url,options);const data=await r.json();if(!r.ok)throw Error(data.error||`请求失败 ${r.status}`);return data}
function message(t){$('message').textContent=t}
async function projects(){const list=await api('/api/documents');$('projects').replaceChildren(new Option('选择项目',''));for(const d of list)$('projects').add(new Option(`${d.name} · ${d.state}`,d.id));if(key)$('projects').value=key}
async function load(id){clearTimeout(timer);key=id;current=null;doc=null;await refresh();page=doc.selected_pages[0]||1;showPage();await projects()}
async function refresh(){const id=key;const data=await api(`/api/documents/${id}`);if(key!==id)return;const previous=doc?.state;doc=data;render();if(doc.state==='processing')timer=setTimeout(()=>refresh().catch(e=>message(e.message)),1500);else if(previous==='processing')await projects()}
function render(){
 const ioCount=doc.records.filter(r=>r.address||['PDF表格','PDF通道列','人工补充'].includes(r.method)).length;
 $('stats').textContent=`${ioCount} 条IO/端子记录 · ${doc.records.length-ioCount} 条设备候选 · 已处理 ${doc.processed}/${doc.selected_pages.length} 页 · ${doc.state==='processing'?'提取中':doc.state==='failed'?'提取中断':'提取完成'}`;
 if(doc.state==='complete'&&$('message').textContent.startsWith('已上传'))message('提取完成，请核对记录；未确定的描述会留空，设备候选保留在待核对项。');
 $('export').hidden=doc.state==='processing';$('export').href=`/api/documents/${key}/export`;
 $('add').disabled=doc.state==='processing';$('translate').disabled=doc.state==='processing';
 const failures=Object.entries(doc.errors).map(([n,e])=>`PDF第${n}页失败：${e}`);
 $('report').textContent=[doc.fatal_error||'',...failures,`未检出候选的PDF页（请检查遗漏）：${doc.zero_pages.join(', ')||'无'}`].filter(Boolean).join('\n');
 const query=$('search').value.toLowerCase(),filter=$('filter').value;
 const isIO=r=>r.address||['PDF表格','PDF通道列','人工补充'].includes(r.method);
 const rows=doc.records.filter(r=>(filter!=='io'||isIO(r))&&(filter!=='devices'||!isIO(r))&&(filter!=='pending'||r.status==='待核对')&&(filter!=='page'||r.pdf_page===page)&&[r.address,r.device,r.original,r.translated,r.module].join(' ').toLowerCase().includes(query));
 $('rows').replaceChildren();for(const r of rows){const tr=document.createElement('tr');if(current===r.id)tr.className='selected';for(const val of [r.address||'—',r.device||'未关联',r.original||'—',r.status]){const td=document.createElement('td');td.textContent=val;tr.append(td)}tr.onclick=()=>edit(r);$('rows').append(tr)}
}
function showPage(){if(!key||!doc)return;page=Math.max(1,Math.min(doc.page_count,page));$('page').value=page;$('drawing').src=`/api/documents/${key}/pages/${page}`;$('highlight').hidden=true;render()}
const fields=[['address','IO地址 / IO Address'],['device','现场设备编号 / Device Tag'],['io_type','IO类型 / IO Type'],['module','模块 / Module'],['model','型号 / Model'],['pin','引脚 / Pin'],['original','原文描述 / Original Description'],['translated','中文描述 / Chinese Description'],['reference','图纸引用 / Reference'],['drawing_page','图纸页号 / Drawing Page'],['usage','使用状态 / Usage'],['status','核对状态 / Review Status'],['notes','备注 / Notes']];
function edit(r){if(doc.state==='processing'){message('提取完成后才能编辑');return}current=r.id;page=r.pdf_page;showPage();$('recordtitle').textContent=`记录 ${r.id} · PDF第${r.pdf_page}页 · ${r.method}`;$('fields').replaceChildren();
 for(const [name,label] of fields){const l=document.createElement('label');l.textContent=label;let input;if(name==='status'||name==='usage'){input=document.createElement('select');for(const v of name==='status'?['待核对','已确认','已修正']:['待确认','使用中','备用'])input.add(new Option(v,v))}else input=document.createElement(['original','translated','notes'].includes(name)?'textarea':'input');input.name=name;input.value=r[name]||'';l.append(input);$('fields').append(l)}$('editor').hidden=false;
 const img=$('drawing');img.onload=()=>{if(current!==r.id||page!==r.pdf_page||!r.bbox.length)return;const scale=1.5;const b=r.bbox;const h=$('highlight');h.style.left=`${b[0]*scale/img.naturalWidth*100}%`;h.style.top=`${b[1]*scale/img.naturalHeight*100}%`;h.style.width=`${(b[2]-b[0])*scale/img.naturalWidth*100}%`;h.style.height=`${(b[3]-b[1])*scale/img.naturalHeight*100}%`;h.hidden=false};render()
}
$('upload').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{const form=new FormData(e.target);form.set('force_ocr',e.target.force_ocr.checked?'true':'false');const r=await api('/api/upload',{method:'POST',body:form});$('editor').hidden=true;message('已上传，正在提取。请等待完成后核对。');await load(r.id)}catch(e){message(e.message)}finally{button.disabled=false}};
$('projects').onchange=()=>{if($('projects').value){$('editor').hidden=true;load($('projects').value).catch(e=>message(e.message))}};
$('editor').onsubmit=async e=>{e.preventDefault();try{const r=await api(`/api/documents/${key}/records/${current}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.fromEntries(new FormData(e.target)))});await refresh();edit(r);message('修改已保存；Excel导出会重新生成待核对项和汇总。')}catch(e){message(e.message)}};
$('remove').onclick=async()=>{if(!confirm('删除这条误识别记录？此操作无法自动撤销。'))return;try{await api(`/api/documents/${key}/records/${current}`,{method:'DELETE'});current=null;$('editor').hidden=true;await refresh()}catch(e){message(e.message)}};
$('add').onclick=async()=>{if(!key)return;try{const r=await api(`/api/documents/${key}/records`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pdf_page:page})});await refresh();edit(r)}catch(e){message(e.message)}};
$('prev').onclick=()=>{page--;showPage()};$('next').onclick=()=>{page++;showPage()};$('page').onchange=()=>{page=Number($('page').value)||1;showPage()};$('search').oninput=()=>doc&&render();$('filter').onchange=()=>doc&&render();
$('translate').onclick=async()=>{if(!key)return;$('translate').disabled=true;message('正在本机翻译；原文和已有译文会保留。');try{const r=await api(`/api/documents/${key}/translate`,{method:'POST'});await refresh();message(`已翻译 ${r.translated} 条，跳过或失败 ${r.skipped_or_failed} 条，译文需人工核对。`)}catch(e){message(e.message)}finally{$('translate').disabled=false}};
projects().catch(e=>message(e.message));
$('zoom').onchange=()=>{document.querySelector('.imagewrap').style.width=$('zoom').value+'%'};
