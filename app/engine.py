import io, re, subprocess, tempfile, unicodedata
import fitz
from PIL import Image

def normalize(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).upper()

def ocr(image, lang='por+eng'):
    with tempfile.TemporaryDirectory() as tmp:
        path=tmp+'/page.png'; image.save(path)
        result=subprocess.run(['tesseract',path,'stdout','-l',lang,'--psm','3'],capture_output=True,text=True,timeout=120)
        if result.returncode: raise RuntimeError('Falha no OCR: '+result.stderr[-500:])
        return result.stdout

def read_page(page, lang):
    text=page.get_text()
    if len(text.strip())>60: return text,0
    pix=page.get_pixmap(matrix=fitz.Matrix(2,2))
    im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
    angle=0
    with tempfile.TemporaryDirectory() as tmp:
        path=tmp+'/osd.png'; im.save(path)
        r=subprocess.run(['tesseract',path,'stdout','--psm','0'],capture_output=True,text=True,timeout=45)
        m=re.search(r'Rotate: (\d+)',r.stdout)
        if m: angle=int(m.group(1))
    text=ocr(im.rotate(-angle,expand=True),lang)
    def score(value):
        return len(re.findall(r'\b(?:GUIA|NOME|DADOS|CONSULTA|PACIENTE|MEDICO|SOLICITACAO|EXAMES|PRESTADOR|CARTEIRA|CONTRATADO|PROFISSIONAL|ASSINATURA)\b',normalize(value)))
    if score(text)<4:
        candidates=[(text,angle)]
        for a in (90,180,270):
            if a!=angle: candidates.append((ocr(im.rotate(-a,expand=True),lang),a))
        text,angle=max(candidates,key=lambda x:score(x[0]))
    return text,angle

def fields(text):
    t=normalize(text); lines=[s.strip() for s in t.splitlines() if s.strip()]
    guide=bool(re.search(r'GUIA DE (CONSULTA|SERVI[CG]O)|GUIA.*SP/SADT|GUIA.*SP.?SADT|\(SP/SADT\)',t))
    kind='guia' if guide else ('laudo' if re.search(r'LAUDO|CONCLUSAO|IMPRESSAO DIAGNOSTICA',t) else 'pedido')
    number=''; name=''
    # Different operators use either provider guide or operator authorization number.
    for pattern in [r'(?:NUMERO|N[°ºO]?\.?).*GUIA.*PRESTADOR[^\n]*?\b(\d{5,})\b',r'GUIA.*PRESTADOR\s*\n\s*(\d{5,})',r'GUIA.*OPERADORA[^\n]*?\b(\d{5,})\b']:
        m=re.search(pattern,t)
        if m: number=m.group(1); break
    if not number and guide:
        for line in lines[:18]:
            m=re.search(r'\b\d{7,}\b',line)
            if m: number=m.group(); break
    for i,line in enumerate(lines):
        m=re.search(r'(?:\b(?:7|17|10)\s*[-—:]?\s*NOM[EIO]+\b|NOME DO BENEFICIARIO|NOME DO PACIENTE|PACIENTE\s*:)',line)
        if m:
            candidate=line[m.end():].strip(' :-')
            candidate=re.sub(r'\b(?:8|9|10)\s*[-—].*','',candidate).strip()
            if len(candidate.split())<2:
                for nextline in lines[i+1:i+8]:
                    if re.fullmatch(r'[A-Z][A-Z \'.|()-]+',nextline) and len(nextline.split())>=2 and not re.search(r'DADOS|NOME|VALIDADE|CARTEIRA|SOCIAL|ATENDIMENTO',nextline):
                        candidate=nextline; break
            candidate=re.sub(r'^\d+\s*[-—:]\s*','',candidate)
            if len(candidate.split())>=2 and not re.search(r'CARTEIRA|CONTRATADO|ATENDIMENTO|BENEFICIARIO',candidate): name=candidate.strip("| .[]()'"); break
    return {'kind':kind,'number':number,'name':name}

def suggest(pages,mode):
    groups=[]
    for p in pages:
        if p['kind']=='guia' or not groups or mode=='guides':
            groups.append({'pages':[p['page']], 'number':p['number'],'name':p['name'],'approved':False})
        else: groups[-1]['pages'].append(p['page'])
    return groups

def filename(group,mode):
    words=group['name'].strip().split()
    short=' '.join([words[0],words[-1]]) if len(words)>1 else ' '.join(words)
    title=f"{group['number']} {'Pedido Médico ' if mode!='guides' else ''}{short}"
    return re.sub(r'[\x00-\x1f/\\:*?"<>|]','_',title).strip(' .')+'.pdf'

def validate(groups,count):
    used=[]
    for g in groups:
        if not g.get('approved'): raise ValueError('Revise e aprove todos os grupos.')
        if not re.fullmatch(r'\d+',g.get('number','')): raise ValueError('Informe um número de guia válido.')
        if len(g.get('name','').split())<2: raise ValueError('Informe nome e sobrenome do paciente.')
        if not g.get('pages'): raise ValueError('Grupo sem páginas.')
        for p in g['pages']:
            if type(p)!=int or not 1<=p<=count: raise ValueError('Página inválida.')
            used.append(p)
    if sorted(used)!=list(range(1,count+1)): raise ValueError('Cada página deve aparecer exatamente uma vez.')
