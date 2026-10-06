import base64, hashlib, hmac, http.cookies, io, json, os, secrets, threading, time, zipfile
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import fitz
from engine import read_page, fields, suggest, filename, validate

ROOT=Path(os.getenv('DATA_DIR','/data')); ROOT.mkdir(parents=True,exist_ok=True)
USER=os.getenv('APP_USER','admin'); PASSWORD=os.getenv('APP_PASSWORD','')
if len(PASSWORD)<12: raise SystemExit('Configure APP_PASSWORD com pelo menos 12 caracteres.')
LANG=os.getenv('OCR_LANG','por+eng'); MAX=int(os.getenv('MAX_UPLOAD_MB','100'))*1024*1024
sessions={}; jobs={}; lock=threading.Lock(); worker=threading.Semaphore(1)

def process(jid):
    job=jobs[jid]
    try:
        with worker:
            job['status']='processing'; pages=[]
            with fitz.open(ROOT/jid/'source.pdf') as doc:
                for i,p in enumerate(doc):
                    text,angle=read_page(p,LANG)
                    pages.append({'page':i+1,'text':text,'rotation':angle,**fields(text)})
                    job['done']=i+1
            job.update(pages=pages,groups=suggest(pages,job['mode']),status='ready')
    except Exception: job.update(status='error',error='Não foi possível ler o PDF. Confira se não está protegido e tente novamente.')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,status,data,ctype='application/json',headers=None):
        if ctype=='application/json': data=json.dumps(data,ensure_ascii=False).encode()
        if isinstance(data,str): data=data.encode()
        self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(data))); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY')
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)
    def auth(self):
        c=http.cookies.SimpleCookie(); c.load(self.headers.get('Cookie','')); token=c.get('session')
        s=sessions.get(token.value) if token else None
        return s if s and s['expires']>time.time() else None
    def body(self):
        n=int(self.headers.get('Content-Length','0'))
        if n>MAX: raise ValueError('Arquivo excede o limite configurado.')
        return self.rfile.read(n)
    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/': return self.send(200,Path(__file__).with_name('index.html').read_bytes(),'text/html; charset=utf-8')
        s=self.auth()
        if not s: return self.send(401,{'error':'Faça login.'})
        if path=='/api/me': return self.send(200,{'user':USER,'csrf':s['csrf']})
        parts=path.strip('/').split('/')
        if len(parts)>=3 and parts[:2]==['api','jobs']:
            jid=parts[2]; job=jobs.get(jid)
            if not job: return self.send(404,{'error':'Lote não encontrado.'})
            if len(parts)==3: return self.send(200,job)
            if len(parts)==5 and parts[3]=='page':
                try:
                    i=int(parts[4])-1
                    with fitz.open(ROOT/jid/'source.pdf') as doc:
                        p=doc[i]; angle=job.get('pages',[{}]*len(doc))[i].get('rotation',0)
                        pix=p.get_pixmap(matrix=fitz.Matrix(1.2,1.2).prerotate(angle))
                        return self.send(200,pix.tobytes('png'),'image/png')
                except Exception: return self.send(404,{'error':'Página não encontrada.'})
        return self.send(404,{'error':'Não encontrado.'})
    def do_POST(self):
        path=urlparse(self.path).path
        try:
            if path=='/api/login':
                body=json.loads(self.body())
                if not (hmac.compare_digest(str(body.get('user','')),USER) and hmac.compare_digest(str(body.get('password','')),PASSWORD)):
                    time.sleep(1); return self.send(401,{'error':'Usuário ou senha incorretos.'})
                token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24); sessions[token]={'csrf':csrf,'expires':time.time()+8*3600}
                cookie=f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+('; Secure' if os.getenv('COOKIE_SECURE')=='1' else '')
                return self.send(200,{'csrf':csrf},headers={'Set-Cookie':cookie})
            s=self.auth()
            if not s: return self.send(401,{'error':'Faça login.'})
            if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),s['csrf']): return self.send(403,{'error':'Sessão inválida. Atualize a página.'})
            if path=='/api/logout':
                s['expires']=0; return self.send(200,{},headers={'Set-Cookie':'session=; Path=/; Max-Age=0'})
            if path=='/api/jobs':
                mode=self.headers.get('X-Mode','guides')
                if mode not in ['guides','orders','reports']: raise ValueError('Modo inválido.')
                raw=self.body()
                if not raw.startswith(b'%PDF'): raise ValueError('Envie um PDF válido.')
                with lock:
                    if sum(j['status'] in ['queued','processing'] for j in jobs.values())>=3: return self.send(429,{'error':'Há três lotes na fila. Aguarde.'})
                    with fitz.open(stream=raw,filetype='pdf') as d:
                        if d.needs_pass or not 0<len(d)<=400: raise ValueError('PDF protegido, vazio ou com mais de 400 páginas.')
                        count=len(d)
                    jid=secrets.token_hex(16); folder=ROOT/jid; folder.mkdir(); (folder/'source.pdf').write_bytes(raw)
                    jobs[jid]={'id':jid,'status':'queued','done':0,'total':count,'mode':mode,'created':time.time()}
                threading.Thread(target=process,args=(jid,),daemon=True).start()
                return self.send(202,{'id':jid})
            parts=path.strip('/').split('/')
            if len(parts)==4 and parts[:2]==['api','jobs']:
                jid=parts[2]; job=jobs.get(jid)
                if not job: return self.send(404,{'error':'Lote não encontrado.'})
                if parts[3]=='delete':
                    if job['status'] in ['queued','processing']: raise ValueError('Aguarde terminar o processamento.')
                    import shutil
                    shutil.rmtree(ROOT/jid); del jobs[jid]; return self.send(200,{})
                if parts[3]=='export':
                    if job['status']!='ready': raise ValueError('Lote ainda não está pronto.')
                    groups=json.loads(self.body())['groups']; validate(groups,job['total']); out=io.BytesIO(); names={}
                    with fitz.open(ROOT/jid/'source.pdf') as source,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
                        for g in groups:
                            name=filename(g,job['mode']); names[name]=names.get(name,0)+1
                            if names[name]>1: name=name[:-4]+f' ({names[name]}).pdf'
                            with fitz.open() as d:
                                for i in g['pages']: d.insert_pdf(source,from_page=i-1,to_page=i-1)
                                z.writestr(name,d.tobytes(garbage=4,deflate=True))
                    return self.send(200,out.getvalue(),'application/zip',{'Content-Disposition':'attachment; filename="guias-separadas.zip"'})
            self.send(404,{'error':'Não encontrado.'})
        except (ValueError,KeyError,json.JSONDecodeError) as e: self.send(400,{'error':str(e)})
        except Exception: self.send(500,{'error':'Falha ao executar a operação.'})

def cleanup():
    import shutil
    while True:
        time.sleep(60)
        for jid,j in list(jobs.items()):
            if j['status'] not in ['queued','processing'] and time.time()-j['created']>int(os.getenv('RETENTION_HOURS','24'))*3600:
                shutil.rmtree(ROOT/jid,ignore_errors=True); jobs.pop(jid,None)
        for token,s in list(sessions.items()):
            if s['expires']<time.time(): sessions.pop(token,None)

# Files from earlier executions are discarded; this MVP has no persistent batch index.
import shutil
for p in ROOT.iterdir():
    if p.is_dir() and len(p.name)==32 and all(c in '0123456789abcdef' for c in p.name): shutil.rmtree(p)
threading.Thread(target=cleanup,daemon=True).start()
ThreadingHTTPServer(('0.0.0.0',8000),Handler).serve_forever()
