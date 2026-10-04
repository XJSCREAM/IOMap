import json
import os
import threading
import uuid
from pathlib import Path
import fitz
from flask import Flask,abort,jsonify,render_template,request,send_file
from extraction import base_record,extract_page,build_io_index,enrich_records
from workbook import export_workbook
from translate_excel import LocalTranslator,english_description

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('IOMAP_DATA_DIR',str(ROOT/'data')))
app=Flask(__name__);app.config['MAX_CONTENT_LENGTH']=100*1024*1024
LOCK=threading.RLock();TRANSLATE_LOCK=threading.Lock()
FIELDS={'io_type','address','module','model','pin','device','original','translated','usage','drawing_page','reference','status','notes'}

def folder(key):
    try: uuid.UUID(key)
    except ValueError:abort(404)
    return DATA/key

def read(key):
    path=folder(key)/'document.json'
    if not path.exists():abort(404)
    return json.loads(path.read_text())

def save(key,doc):
    path=folder(key)/'document.json';tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(doc,ensure_ascii=False));tmp.replace(path)

def process(key,force,language):
    try:
        with fitz.open(folder(key)/'source.pdf') as pdf:
            index=build_io_index(pdf) if not force else {}
            with LOCK:doc=read(key);selected=doc['selected_pages']
            for number in selected:
                try:
                    records,mode=extract_page(pdf[number-1],number,force,language)
                    enrich_records(records,index)
                    error=None
                except Exception as exc:records=[];mode='failed';error=str(exc)
                with LOCK:
                    doc=read(key)
                    for r in records:r['id']=len(doc['records'])+1;doc['records'].append(r)
                    if error:doc['errors'][str(number)]=error
                    elif not records:doc['zero_pages'].append(number)
                    doc['processed']+=1;doc['modes'][mode]=doc['modes'].get(mode,0)+1;save(key,doc)
        with LOCK:doc=read(key);doc['state']='complete';save(key,doc)
    except Exception as exc:
        with LOCK:doc=read(key);doc['state']='failed';doc['fatal_error']=str(exc);save(key,doc)

@app.get('/')
def index():return render_template('index.html')

@app.get('/api/documents')
def documents():
    result=[]
    if DATA.exists():
        with LOCK:
            for path in DATA.glob('*/document.json'):
                d=json.loads(path.read_text());result.append({k:d[k] for k in ['id','name','state','page_count']})
    return jsonify(result)

@app.post('/api/upload')
def upload():
    incoming=request.files.get('file')
    if not incoming: return jsonify(error='请选择PDF文件'),400
    payload=incoming.read()
    if not payload.startswith(b'%PDF-'):return jsonify(error='文件不是PDF'),400
    try:
        with fitz.open(stream=payload,filetype='pdf') as pdf:
            if pdf.needs_pass:return jsonify(error='请先解除PDF密码保护'),400
            count=len(pdf)
            if count<1 or count>1000:return jsonify(error='支持1至1000页PDF'),400
            raw=request.form.get('pages','').strip()
            if raw:
                match=__import__('re').fullmatch(r'(\d+)(?:-(\d+))?',raw)
                if not match:raise ValueError('页码格式为151-185或166')
                start=int(match[1]);end=int(match[2] or start)
                if not 1<=start<=end<=count:raise ValueError('页码超出PDF范围')
                selected=list(range(start,end+1))
            else:selected=list(range(1,count+1))
    except Exception as exc:return jsonify(error=str(exc)),400
    key=str(uuid.uuid4());dir=folder(key);dir.mkdir(parents=True)
    (dir/'source.pdf').write_bytes(payload)
    doc=dict(id=key,name=Path(incoming.filename or 'drawing.pdf').name,state='processing',page_count=count,selected_pages=selected,processed=0,records=[],errors={},zero_pages=[],modes={})
    with LOCK:save(key,doc)
    thread=threading.Thread(target=process,args=(key,request.form.get('force_ocr')=='true',request.form.get('language','eng')),daemon=True);thread.start()
    return jsonify(id=key),202

@app.get('/api/documents/<key>')
def get_document(key):
    with LOCK:return jsonify(read(key))

@app.get('/api/documents/<key>/pages/<int:number>')
def image(key,number):
    with LOCK:doc=read(key)
    if not 1<=number<=doc['page_count']:abort(404)
    with fitz.open(folder(key)/'source.pdf') as pdf:
        pix=pdf[number-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False)
        return app.response_class(pix.tobytes('png'),mimetype='image/png')

@app.patch('/api/documents/<key>/records/<int:record_id>')
def update(key,record_id):
    changes=request.get_json()
    if not isinstance(changes,dict) or set(changes)-FIELDS:return jsonify(error='无效字段'),400
    if any(not isinstance(v,str) or len(v)>10000 for v in changes.values()):return jsonify(error='字段必须是文本且不超过10000字符'),400
    if 'status' in changes and changes['status'] not in ['待核对','已确认','已修正']:return jsonify(error='无效核对状态'),400
    if 'usage' in changes and changes['usage'] not in ['待确认','使用中','备用']:return jsonify(error='无效使用状态'),400
    with LOCK:
        d=read(key)
        if d['state']=='processing':return jsonify(error='提取完成后才能编辑'),409
        r=next((r for r in d['records'] if r['id']==record_id),None)
        if not r:abort(404)
        r.update(changes);save(key,d)
    return jsonify(r)

@app.post('/api/documents/<key>/records')
def add(key):
    with LOCK:
        d=read(key)
        if d['state']=='processing':return jsonify(error='提取完成后才能编辑'),409
        try:number=int(request.get_json().get('pdf_page',1))
        except (TypeError,ValueError):return jsonify(error='无效页码'),400
        if not 1<=number<=d['page_count']:return jsonify(error='无效页码'),400
        r=base_record(number,[],'人工补充');r['id']=max([x['id'] for x in d['records']]+[0])+1
        d['records'].append(r);save(key,d)
    return jsonify(r),201

@app.delete('/api/documents/<key>/records/<int:record_id>')
def delete(key,record_id):
    with LOCK:
        d=read(key)
        if d['state']=='processing':return jsonify(error='提取完成后才能编辑'),409
        d['records']=[r for r in d['records'] if r['id']!=record_id];save(key,d)
    return jsonify(ok=True)

@app.get('/api/documents/<key>/export')
def export(key):
    with LOCK:d=read(key)
    if d['state']=='processing':return jsonify(error='请等待提取完成'),409
    return send_file(export_workbook(d),as_attachment=True,download_name='IOMap_B.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post('/api/documents/<key>/translate')
def translate(key):
    with LOCK:d=read(key)
    if d['state']=='processing':return jsonify(error='请等待提取完成'),409
    if not TRANSLATE_LOCK.acquire(blocking=False):return jsonify(error='翻译正在运行，请稍后重试'),409
    try:
        try:translator=LocalTranslator(ROOT/'models/en_zh',ROOT/'.cache/translations.json')
        except Exception as exc:return jsonify(error=str(exc)),503
        count=0;failed=0
        for row in d['records']:
            if row['translated'] or not row['original']:continue
            try:
                if row['method']!='PDF表格' and '描述交叉校验来源' not in row['notes']:raise ValueError('候选文本需要先人工整理为明确英文描述')
                value=translator.translate(english_description(row['original']))
                if not value.strip():raise ValueError('模型返回空译文')
                with LOCK:
                    current=read(key);r=next((r for r in current['records'] if r['id']==row['id']),None)
                    if r and not r['translated'] and r['original']==row['original']:
                        r['translated']=value;r['notes']+='；译文待人工核对';save(key,current);count+=1
            except Exception:failed+=1
        return jsonify(translated=count,skipped_or_failed=failed)
    finally:TRANSLATE_LOCK.release()

@app.errorhandler(413)
def too_large(error):return jsonify(error='文件超过100MB限制'),413

if __name__=='__main__':
    # Interrupted jobs cannot be silently reported as finished after a restart.
    if DATA.exists():
        for path in DATA.glob('*/document.json'):
            d=json.loads(path.read_text())
            if d['state']=='processing':d['state']='failed';d['fatal_error']='上次提取被中断，请重新上传';save(d['id'],d)
    app.run(host='127.0.0.1',port=int(os.environ.get('IOMAP_PORT','5000')),threaded=True)
