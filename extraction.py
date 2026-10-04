"""PDF text/table extraction and local Tesseract OCR. Coordinates stay in PDF units."""
import csv
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import fitz

ADDRESS = re.compile(r'^(?:[IQ]\d+_\d+|[IQ](?:W|B|D)?\d+\.\d+|%[IQ](?:X|W|B|D)?\d+(?:\.\d+)?|DI_\d+|DO_\d+|[AT]I?\.?\d+[.+-]?|AO\d*\.\d+|T_\d+)$', re.I)
DEVICE = re.compile(r'^-\d+[A-Z]{1,4}\d+$')

def ocr_words(page, language='eng'):
    if not shutil.which('tesseract'):
        raise RuntimeError('未安装 Tesseract。请安装后重新上传扫描 PDF。')
    with tempfile.TemporaryDirectory() as temp:
        image = Path(temp)/'page.png'
        page.get_pixmap(matrix=fitz.Matrix(3,3), alpha=False).save(image)
        result = subprocess.run(['tesseract',str(image),'stdout','-l',language,'--psm','11','tsv'],capture_output=True,text=True,timeout=120)
        if result.returncode:
            raise RuntimeError('OCR失败：'+result.stderr[-500:])
        words=[]
        for r in csv.DictReader(io.StringIO(result.stdout), delimiter='\t'):
            if not r['text'].strip():continue
            x,y,w,h=[float(r[k])/3 for k in ['left','top','width','height']]
            words.append((x,y,x+w,y+h,r['text'],float(r['conf'])))
        return words

def base_record(page, bbox, method):
    return dict(io_type='',address='',module='',model='',pin='',device='',original='',translated='',usage='待确认',drawing_page='',pdf_page=page,reference='',raw_address='',method=method,status='待核对',notes='',bbox=list(bbox))

def drawing_page_number(page):
    footer=page.get_text(clip=fitz.Rect(page.rect.width*.94,page.rect.height*.95,page.rect.width,page.rect.height))
    found=re.findall(r'\b\d{1,5}\b',footer)
    return found[-1] if found else ''

def text_lines(page):
    return [dict(text=''.join(s['text'] for s in line['spans']).strip(),bbox=line['bbox'],direction=line['dir'])
            for block in page.get_text('dict')['blocks'] if block['type']==0 for line in block['lines']]

def slot_records(page,number):
    """Recognize the documented ROMACO/Schneider column layout conservatively."""
    text=page.get_text();match=re.search(r'-SLOT(\d+)\b',text)
    if not match:return []
    lines=text_lines(page);module='SLOT'+match[1]
    digital=[l for l in lines if re.fullmatch(r'[IQ]\d+_\d+',l['text'])]
    analog=[l for l in lines if re.fullmatch(r'A[IO]\d*\.\d+',l['text'])]
    anchors=sorted(digital or analog,key=lambda l:(l['bbox'][1],l['bbox'][0]))
    if not anchors:return []
    # Narrow to address row inside the PLC module, not a cross-reference elsewhere.
    model_match=re.search(r'TYPE\s+(\S+)',text)
    records=[]
    for a in anchors:
        b=a['bbox'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
        r=base_record(number,b,'PDF通道列')
        r.update(address=a['text'],raw_address=a['text'],module=module,drawing_page=drawing_page_number(page),model=model_match[1] if model_match else '')
        r['io_type']='DI' if a['text'].startswith('I') else 'DO' if a['text'].startswith('Q') else 'AI' if a['text'].startswith('AI') else 'AO'
        others=[(v['bbox'][0]+v['bbox'][2])/2 for v in anchors if v is not a]
        half=min([abs(cx-x)/2 for x in others if abs(cx-x)>1]+[60])
        lower=[l for l in lines if l['direction']==(1.0,0.0) and page.rect.height*.73<l['bbox'][1]<page.rect.height*.91 and abs((l['bbox'][0]+l['bbox'][2])/2-cx)<half and re.search(r'[A-Za-zÀ-ÿ]',l['text']) and not re.search(r'^[-/]|^\d|mm²|SLOT|TM5',l['text'])]
        r['original']='\n'.join(l['text'] for l in sorted(lower,key=lambda l:l['bbox'][1]))
        pins=[l for l in lines if re.fullmatch(r'\d{1,2}',l['text']) and abs(l['bbox'][0]-cx)<16 and abs(l['bbox'][1]-cy)<25]
        if len(pins)==1:r['pin']=pins[0]['text']
        if not digital:
            # AO5.11 etc. are physical connector pin labels in this drawing,
            # not PLC memory addresses. Do not export them as IO addresses.
            r['pin']=a['text'];r['address']='';r['raw_address']=''
            labels=[l for l in lines if l['direction']==(1.0,0.0) and 0<l['bbox'][1]-cy<25 and 0<l['bbox'][0]-b[0]<25]
            if labels:
                label=min(labels,key=lambda l:l['bbox'][1])['text']
                if not r['original']:r['original']=label
                if label=='0V':r['io_type']='公共端子'
        refs=[l['text'] for l in lines if re.search(r'\b[A-Za-z0-9.-]+:[^\s]+\s+\d+\.\d+',l['text']) and abs((l['bbox'][0]+l['bbox'][2])/2-cx)<20]
        r['reference']=' | '.join(dict.fromkeys(refs))
        # Device tags on the channel, excluding cable tags. Cross-references are
        # explicit terminal evidence, but not proof of the final field device.
        devices=[l['text'] for l in lines if DEVICE.fullmatch(l['text']) and not re.fullmatch(r'-\d+W\d+',l['text']) and b[1]+20<l['bbox'][1]<page.rect.height*.72 and 0<cx-l['bbox'][2]<55]
        targets=[]
        for ref in refs:
            for tag in re.findall(r'\b(\d+[A-Z]{1,4}\d+):',ref):
                if not re.fullmatch(r'\d+(?:X|XC|W)\d+',tag):targets.append('-'+tag)
        r['device']=' | '.join(dict.fromkeys(devices or targets))
        spare=bool(re.search(r'\b(reserve|scorta)\b',r['original'],re.I))
        if spare:r['usage']='备用';r['translated']='备用'
        r['notes']='按通道列提取；仍需对照电路核对'
        if targets and not devices:r['notes']+='；DEVICE来自交叉引用端点，需确认是否为最终现场设备'
        if not r['device'] and not spare:r['notes']+='；现场设备未确定'
        if not digital:r['notes']+='；模拟量地址可能是信号/公共端子，不等同于独立通道'
        records.append(r)
    return records

def build_io_index(pdf):
    """Use authoritative I/O tables anywhere in the same document as evidence."""
    index={}
    for i,page in enumerate(pdf):
        text=page.get_text()
        if 'Indirizzo / Address' not in text or 'Scheda / Board' not in text:continue
        rows,_=extract_page(page,i+1)
        for r in rows:
            if r['method']=='PDF表格':
                if r['address']:index.setdefault((r['module'].lstrip('-'),r['address']),[]).append(r)
                if re.fullmatch(r'A[IO]\d*\.\d+',r['pin']):index.setdefault((r['module'].lstrip('-'),'@pin:'+r['pin']),[]).append(r)
    return index

def enrich_records(records,index):
    for r in records:
        if r['method']!='PDF通道列':continue
        matches=index.get((r['module'],r['address'] or '@pin:'+r['pin']),[])
        if len(matches)!=1:
            r['notes']+='；I/O LIST未找到唯一对应项'
            continue
        source=matches[0]
        # Conflicting pin numbers invalidate a silent table description replacement.
        if r['pin'] and source['pin'] and r['pin']!=source['pin']:
            r['notes']+='；Pin与I/O LIST冲突，请核对'
            continue
        r['pin']=r['pin'] or source['pin'];r['model']=source['model'] or r['model']
        if source['original']:
            normalize=lambda value: ''.join(value.split()).casefold()
            if r['original'] and normalize(r['original'])!=normalize(source['original']):
                r['notes']+='；原图列描述与I/O LIST存在差异，以列表作初稿，需人工核对；列描述原文：'+r['original']
            r['original']=source['original']
        r['notes']+=f"；描述交叉校验来源：I/O LIST PDF第{source['pdf_page']}页，图纸{source['drawing_page']}，引用{source['reference']}"
        if re.search(r'\b(reserve|scorta)\b',r['original'],re.I):r['usage']='备用';r['translated']='备用'
    return records


def extract_page(page, number, force_ocr=False, language='eng'):
    text=page.get_text()
    native=page.get_text('words')
    # A header or page footer alone is not adequate text coverage for a diagram.
    interior=[w for w in native if page.rect.height*.08<w[1]<page.rect.height*.88]
    raster_area=sum(fitz.Rect(image['bbox']).get_area() for image in page.get_image_info())
    use_ocr=force_ocr or (len(interior)<8 and (not native or raster_area>page.rect.get_area()*.2))
    if not use_ocr and 'Indirizzo / Address' in text and 'Scheda / Board' in text:
        tables=[t for t in page.find_tables().tables if t.col_count==5 and any('Indirizzo' in str(c) for row in t.extract()[:2] for c in row)]
        records=[]
        for table in tables:
            data=table.extract(); title=str(data[0][0] or '')
            model=title.split('Board',1)[-1].strip()
            kind=next((k for phrase,k in [('DIGITAL INPUTS','DI'),('DIGITAL OUTPUTS','DO'),('ANALOG INPUTS','AI'),('ANALOG OUTPUTS','AO')] if phrase in title),'其他/待分类')
            footer=page.get_text(clip=fitz.Rect(page.rect.width*.88,page.rect.height*.945,page.rect.width,page.rect.height))
            drawing=re.findall(r'\b\d{3,4}\b',footer)
            for index,row in enumerate(data[2:],2):
                board,pin,addr,desc,ref=[(v or '').strip() for v in row]
                if not any(row):continue
                r=base_record(number,table.rows[index].bbox,'PDF表格')
                r.update(io_type=kind,module=board,model=model,pin=pin,address=re.sub(r'^([IQ]\d+)\s+(\d+)\s*_$',r'\1_\2',addr),raw_address=addr,original=desc,reference=ref,drawing_page=drawing[-1] if drawing else '')
                spare=bool(re.search(r'\b(reserve|scorta)\b',desc,re.I))
                r['usage']='备用' if spare else '待确认'
                r['translated']='备用' if spare else ''
                r['notes']='表格记录可能包含电源和公共端子；需核对'
                if not spare:r['notes']+='；现场DEVICE尚未与电路图关联'
                records.append(r)
        if records:return records,'text'
    if not use_ocr:
        structured=slot_records(page,number)
        if structured:return structured,'text'
    words=ocr_words(page,language) if use_ocr else native
    method='OCR候选' if use_ocr else 'PDF文字候选'
    records=[]
    for word in words:
        raw=word[4].strip()
        token=raw
        # Correct confusable numeric glyphs only after an explicit I/Q prefix.
        if use_ocr and re.fullmatch(r'[IQ][0-9lLOo]+_[0-9lLOo]+',token):
            token=token[0]+token[1:].translate(str.maketrans({'l':'1','L':'1','O':'0','o':'0'}))
        if not (ADDRESS.fullmatch(token) or DEVICE.fullmatch(token)):continue
        r=base_record(number,word[:4],method)
        if ADDRESS.fullmatch(token):r['address']=token;r['raw_address']=raw
        else:r['device']=token
        # Nearby text is evidence, not an asserted electrical association.
        near=[w for w in words if abs(w[1]-word[1])<25 and abs(w[0]-word[0])<160]
        r['original']=''
        r['context']=' '.join(w[4] for w in sorted(near,key=lambda w:(round(w[1]/5),w[0])))
        r['notes']='候选：未能可靠关联描述；附近文字只作证据，需人工确认'
        if r['context']:r['notes']+='；附近文字：'+r['context']
        if use_ocr:r['notes']+=f'；OCR置信度 {word[5]:.0f}'
        if token!=raw:r['notes']+='；已修正疑似数字字符，请核对提取原文'
        records.append(r)
    return records,'ocr' if use_ocr else 'text'
