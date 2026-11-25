"""Separate, boss-controlled service references. Never contains buyer/order memory."""
import os,json,sqlite3,time,threading
from contextlib import contextmanager

class ServiceStore:
 def __init__(self,path,domain,seeds=()):
  self.path=path;self.domain=domain;self.lock=threading.RLock()
  with self.db() as c:
   c.executescript('CREATE TABLE IF NOT EXISTS entry(id TEXT PRIMARY KEY, content TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL, hits INTEGER NOT NULL DEFAULT 1); CREATE TABLE IF NOT EXISTS meta(id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER); INSERT OR IGNORE INTO meta VALUES(1,0);')
   for row in seeds:
    key='advice:'+row['topic']
    if not c.execute('SELECT 1 FROM entry WHERE id=?',(key,)).fetchone():self.put(c,key,row,'published')
 @contextmanager
 def db(self):
  c=sqlite3.connect(self.path,timeout=15);c.row_factory=sqlite3.Row
  try:
   with c:yield c
  finally:c.close()
 def put(self,c,key,row,state):
  rev=c.execute('UPDATE meta SET revision=revision+1 WHERE id=1 RETURNING revision').fetchone()[0]
  c.execute('INSERT INTO entry VALUES(?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET content=excluded.content,state=excluded.state,revision=excluded.revision',(key,json.dumps(row,ensure_ascii=False),state,rev));return rev
 def snapshot(self,published=False):
  with self.db() as c:
   rows=[dict(json.loads(x['content']),id=x['id'],state=x['state'],revision=x['revision'],hits=x['hits']) for x in c.execute('SELECT * FROM entry ORDER BY revision DESC') if x['state']==('published' if published else x['state']) and (published or x['state']!='deleted')]
   return {'ok':True,'domain':self.domain,'revision':c.execute('SELECT revision FROM meta').fetchone()[0],'rows':rows}
 def gap(self,b):
  topic=b.get('topic');goods=str(b.get('goods_id') or '') if b.get('binding_scope')=='product' else ''
  if topic not in ('warranty','compensation','gift','resend'):raise ValueError('未知承诺类型')
  if goods and not goods.isdigit():raise ValueError('商品标识错误')
  key='commitment:'+topic+':'+goods
  with self.lock,self.db() as c:
   old=c.execute('SELECT state FROM entry WHERE id=?',(key,)).fetchone()
   if old:c.execute('UPDATE entry SET hits=hits+1 WHERE id=?',(key,))
   else:self.put(c,key,{'kind':'commitment','topic':topic,'goods_id':goods,'goods_name':str(b.get('goods_name') or '')[:200] if goods else '', 'binding_scope':'product' if goods else 'global','scope':self.domain,'title':{'warranty':'保修范围/期限','compensation':'赔付规则','gift':'随单配件/赠品','resend':'补发条件'}[topic],'guidance':'','variants':[]},'draft')
  return {'ok':True,'id':key}
 def create(self,b):
  result=self.gap(b)
  with self.lock,self.db() as c:
   old=c.execute('SELECT * FROM entry WHERE id=?',(result['id'],)).fetchone()
   if old['state']=='deleted':
    row=json.loads(old['content']);row['guidance']='';row['variants']=[]
    self.put(c,result['id'],row,'draft')
  return result
 def edit(self,b):
  key=str(b.get('id') or '');op=b.get('action')
  if op not in ('save','publish','delete'):raise ValueError('未知操作')
  with self.lock,self.db() as c:
   old=c.execute('SELECT * FROM entry WHERE id=?',(key,)).fetchone()
   if not old or old['revision']!=b.get('revision'):raise ValueError('内容已变化，请刷新')
   row=json.loads(old['content'])
   if op=='save':
    item=b.get('item') or {};row['guidance']=str(item.get('guidance','')).strip()[:4000]
    row['variants']=[str(x).strip()[:500] for x in item.get('variants',[]) if str(x).strip()][:10]
   if op=='publish' and not row.get('guidance'):raise ValueError('请填写确认后的内容再发布')
   state={'save':'draft','publish':'published','delete':'deleted'}[op]
   rev=self.put(c,key,row,state)
  return {'ok':True,'revision':rev,'state':state}

def install(ns,domain):
 seed=[];p=os.path.join(ns['BASE'],'curated-umbrella.json')
 if domain=='umbrella' and os.path.exists(p):seed=json.load(open(p,encoding='utf8'))['entries']
 store=ServiceStore(os.path.join(ns['BASE'],'service-knowledge.db'),domain,seed)
 Handler=ns['Handler'];previous=Handler.do_POST
 def post(self):
  path=self.path.split('?',1)[0]
  if not path.startswith('/api/service-knowledge/'):return previous(self)
  h=self.headers.get('Authorization','');q={'token':[h[7:] if h.startswith('Bearer ') else '']}
  if not ns['_user_by_token'](q):return self._json({'ok':False,'error':'请登录'},403)
  if path.endswith('/admin') and not ns['_boss'](q):return self._json({'ok':False,'error':'仅老板可管理'},403)
  try:
   n=int(self.headers.get('Content-Length',0))
   if not 0<n<80000:raise ValueError('请求大小错误')
   b=json.loads(self.rfile.read(n))
   if b.get('domain')!=domain:raise ValueError('版本不匹配')
   if path.endswith('/admin'):
    action=b.get('action','list')
    r=store.snapshot() if action=='list' else store.create(b) if action=='create' else store.edit(b)
   elif path.endswith('/sync'):r=store.snapshot(True)
   elif path.endswith('/gap'):r=store.gap(b)
   else:return self._json({'ok':False,'error':'不存在'},404)
   return self._json(r)
  except (ValueError,TypeError,KeyError) as e:return self._json({'ok':False,'error':str(e)},400)
 Handler.do_POST=post
 return store
