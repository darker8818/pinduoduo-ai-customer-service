"""Additive shared knowledge service, physically separate from shop/order databases."""
import os,json,sqlite3,time,threading
from contextlib import contextmanager
from knowledge_core import clean,assess,key,fingerprint,GENERAL

class KnowledgeStore:
 def __init__(self,path,domain):
  self.path=path;self.domain=domain;self.lock=threading.RLock()
  with self.connect() as c:
   c.executescript('''CREATE TABLE IF NOT EXISTS entry(id INTEGER PRIMARY KEY, cluster TEXT NOT NULL, content TEXT NOT NULL, state TEXT NOT NULL, reason TEXT NOT NULL, revision INTEGER NOT NULL, updated INTEGER NOT NULL, actor TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS submission(fingerprint TEXT PRIMARY KEY, entry_id INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS revision(id INTEGER PRIMARY KEY AUTOINCREMENT, entry_id INTEGER, action TEXT, actor TEXT, created INTEGER, before TEXT);
    CREATE TABLE IF NOT EXISTS receipt(device TEXT PRIMARY KEY, username TEXT, revision INTEGER, seen INTEGER);
    CREATE INDEX IF NOT EXISTS entry_cluster ON entry(cluster);CREATE INDEX IF NOT EXISTS entry_revision ON entry(revision);''')
  for intent,(q,a) in GENERAL.items():self.submit({'question':q,'answer':a,'category':'general'},'system')
 @contextmanager
 def connect(self):
  c=sqlite3.connect(self.path,timeout=20);c.row_factory=sqlite3.Row
  try:
   with c:yield c
  finally:c.close()
 def change(self,c,rid,d,state,reason,actor,action):
  old=c.execute('SELECT * FROM entry WHERE id=?',(rid,)).fetchone() if rid else None
  rev=c.execute('INSERT INTO revision(entry_id,action,actor,created,before) VALUES(?,?,?,?,?)',(rid,action,actor,int(time.time()),json.dumps(dict(old)) if old else '')).lastrowid
  vals=(key(d),json.dumps(d,ensure_ascii=False),state,reason,rev,int(time.time()),actor)
  if old:c.execute('UPDATE entry SET cluster=?,content=?,state=?,reason=?,revision=?,updated=?,actor=? WHERE id=?',vals+(rid,))
  else:rid=c.execute('INSERT INTO entry(cluster,content,state,reason,revision,updated,actor) VALUES(?,?,?,?,?,?,?)',vals).lastrowid
  c.execute('UPDATE revision SET entry_id=? WHERE id=?',(rid,rev));return rid,rev
 def submit(self,raw,actor):
  d=clean(raw,self.domain);fp=fingerprint(d);state,reason=assess(d)
  with self.lock,self.connect() as c:
   old=c.execute('SELECT e.id,e.state,e.revision FROM submission s JOIN entry e ON e.id=s.entry_id WHERE s.fingerprint=?',(fp,)).fetchone()
   if old:return dict(old,duplicate=True)
   peers=c.execute("SELECT * FROM entry WHERE cluster=? AND state IN ('approved','review')",(key(d),)).fetchall()
   if peers and state!='rejected':
    state='review';reason='同一适用条件出现不同答案，请核对冲突'
    for p in peers:
     if p['state']=='approved':self.change(c,p['id'],json.loads(p['content']),'review',reason,actor,'conflict')
   rid,rev=self.change(c,None,d,state,reason,actor,'learn')
   c.execute('INSERT INTO submission VALUES(?,?)',(fp,rid))
   return {'id':rid,'revision':rev,'state':state,'duplicate':False}
 def item(self,r):return dict(json.loads(r['content']),**{k:r[k] for k in ('id','state','reason','revision','updated','actor')})
 def list(self,b):
  page=max(1,int(b.get('page',1)));size=30;state=b.get('state','');q=str(b.get('search',''))[:120];category=str(b.get('category',''))[:120]
  where='state<>\'deleted\'';args=[]
  if state:where+=' AND state=?';args.append(state)
  if q:where+=' AND content LIKE ?';args.append('%'+q+'%')
  if category:where+=' AND content LIKE ?';args.append('%'+category+'%')
  with self.connect() as c:
   total=c.execute('SELECT count(*) FROM entry WHERE '+where,args).fetchone()[0]
   data=[self.item(x) for x in c.execute('SELECT * FROM entry WHERE '+where+' ORDER BY updated DESC,id DESC LIMIT ? OFFSET ?',args+[size,(page-1)*size])]
   counts={r[0]:r[1] for r in c.execute('SELECT state,count(*) FROM entry GROUP BY state')}
   receipts=[dict(x) for x in c.execute('SELECT * FROM receipt ORDER BY seen DESC LIMIT 100')]
  return {'ok':True,'domain':self.domain,'rows':data,'page':page,'pages':max(1,(total+size-1)//size),'total':total,'counts':counts,'receipts':receipts}
 def edit(self,b,actor):
  rid=int(b.get('id',0));op=b.get('action')
  if op not in ('save','approve','delete','reject'):raise ValueError('未知操作')
  with self.lock,self.connect() as c:
   r=c.execute('SELECT * FROM entry WHERE id=?',(rid,)).fetchone()
   if not r or b.get('revision')!=r['revision']:raise ValueError('记录已更新，请刷新后操作')
   d=clean(b.get('item') or json.loads(r['content']),self.domain)
   if op=='approve':d['verified']=True
   state,reason=assess(d)
   if op=='approve':
    if state=='rejected':raise ValueError('不良或敏感内容不可批准')
    if state!='approved':raise ValueError('请先修改为有证据的商品问答；订单和赔付不能共享')
    peers=c.execute("SELECT * FROM entry WHERE cluster=? AND id<>? AND state='approved'",(key(d),rid)).fetchall()
    for p in peers:self.change(c,p['id'],json.loads(p['content']),'review','同条件答案已被老板选择其他版本',actor,'supersede')
   elif op=='delete':state='deleted';reason='老板删除，客户端自动撤回，不再自动导入'
   elif op=='reject':state='rejected';reason='老板拒绝'
   else:state='review';reason='修改已保存，待确认发布'
   _,rev=self.change(c,rid,d,state,reason,actor,op)
   # Both original and edited fingerprints remain tombstoned after deletion.
   c.execute('INSERT OR IGNORE INTO submission VALUES(?,?)',(fingerprint(d),rid))
  return {'ok':True,'revision':rev,'state':state}
 def sync(self,b,username):
  after=max(0,int(b.get('after',0)));size=200
  with self.connect() as c:
   top=c.execute('SELECT coalesce(max(id),0) FROM revision').fetchone()[0]
   ceiling=min(top,int(b.get('ceiling') or top))
   reset=after>top
   if reset:after=0;ceiling=top
   rows=c.execute('SELECT * FROM entry WHERE revision>? AND revision<=? ORDER BY revision LIMIT ?',(after,ceiling,size)).fetchall()
   result=[self.item(x) if x['state']=='approved' else {'id':x['id'],'revision':x['revision'],'state':x['state']} for x in rows]
   cursor=rows[-1]['revision'] if len(rows)==size else ceiling
   sid=str(b.get('device') or '')[:100]
   if sid:c.execute('INSERT INTO receipt VALUES(?,?,?,?) ON CONFLICT(device) DO UPDATE SET username=excluded.username,revision=excluded.revision,seen=excluded.seen',(sid,username,after,int(time.time())))
  return {'ok':True,'domain':self.domain,'rows':result,'cursor':cursor,'ceiling':ceiling,'more':cursor<ceiling,'reset':reset}

def install(ns,domain):
 store=KnowledgeStore(os.path.join(ns['BASE'],'shared-knowledge.db'),domain)
 Handler=ns['Handler'];prev_post=Handler.do_POST;prev_get=Handler.do_GET
 def post(self):
  path=self.path.split('?',1)[0]
  if not path.startswith('/api/knowledge/'):return prev_post(self)
  h=self.headers.get('Authorization','');q={'token':[h[7:] if h.startswith('Bearer ') else '']}
  user=ns['_user_by_token'](q)
  if not user:return self._json({'ok':False,'error':'请先登录'},403)
  if path=='/api/knowledge/admin' and not ns['_boss'](q):return self._json({'ok':False,'error':'仅老板可管理'},403)
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=300000:raise ValueError('请求大小无效')
   b=json.loads(self.rfile.read(n));actor=user['username']
   if path=='/api/knowledge/admin':r=store.list(b) if b.get('action','list')=='list' else store.edit(b,actor)
   elif path=='/api/knowledge/sync':
    if b.get('domain')!=domain:raise ValueError('知识库版本不匹配')
    r=store.sync(b,actor)
   elif path=='/api/knowledge/learn':
    if b.get('domain')!=domain or not isinstance(b.get('items'),list) or len(b['items'])>20:raise ValueError('批次无效')
    result=[]
    for item in b['items']:
     try:result.append(store.submit(item,actor))
     except ValueError as e:result.append({'state':'rejected','error':str(e)})
    r={'ok':True,'results':result}
   else:return self._json({'ok':False,'error':'不存在'},404)
   return self._json(r)
  except (ValueError,TypeError,KeyError) as e:return self._json({'ok':False,'error':str(e)},400)
 def get(self):
  if self.path.split('?',1)[0]=='/knowledge':
   with open(os.path.join(ns['WEB_DIR'],'knowledge.html'),'rb') as f:return self._send(200,f.read(),'text/html; charset=utf-8')
  return prev_get(self)
 Handler.do_POST=post;Handler.do_GET=get
 return store
