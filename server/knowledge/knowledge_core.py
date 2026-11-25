"""Shared schema and deterministic safety gates. No customer/order identifiers."""
import re,json,hashlib,unicodedata
VERSION=1
DOMAINS=('flower','umbrella')
PII=re.compile(r'https?://|[\w.+-]+@[\w.-]+|\b\d[\d -]{10,}\b|订单号|订单编号|单号|收件人|手机号|收货地址|api.key|bearer|sk-[a-z0-9]',re.I)
BAD=re.compile(r'傻|笨蛋|活该|滚蛋|骗子|不是机器人|真人客服|好评返|微信|支付宝|忽略.{0,8}(指令|规则)|system\s*:|<script|你自己|不存在真假',re.I)
VOLATILE=re.compile(r'退款成功|已经退款|已退款|已发货|已签收|待发货|没发货|未发货|库存|包邮|运费|新疆|西藏|赔付|赔偿|补发|七天|7天|包赔|保证|赠送|赠品|花盆|送盆|\d+(?:\.\d+)?\s*元|[¥￥]')
CASE=re.compile(r'订单|退款|退货|售后|发错|投诉|收到|死了|枯萎|破损|坏了|黄了|赔|物流|快递')
COLORS=('白色','黑色','红色','粉色','蓝色','紫色','黄色','绿色','藏青','酒红','多色','混色')
SPECIES=('蝴蝶兰','蟹爪兰','三角梅','栀子花','桂花','茶花','月季','玫瑰','茉莉','杜鹃','绣球','薰衣草','小野花','绿萝','发财树','郁金香')
INTENTS=(('bones',r'几骨|几根|伞骨数量'),('size',r'尺寸|直径|半径|多大|长度|几人|个人|几个人|厘米'),('material',r'材质|材料|成分|什么做'),('opening',r'自动|手动|开合|打开'),('color',r'颜色|花色|什么色'),('care',r'养护|浇水|怎么养|清洁|擦洗'),('type',r'真花|假花|仿真|品种|什么花|哪种伞'))
GENERAL={'greeting':('你好','亲，在呢，您想了解什么呀？'),'thanks':('谢谢','亲，不客气呀，有需要再找我就好。'),'bye':('再见','亲，再见呀，祝您生活愉快。')}
PATTERNS={'greeting':r'你好|您好|在吗|在不在|有人吗','thanks':r'谢谢|感谢|多谢|辛苦了|好的谢谢|好的感谢','bye':r'再见|拜拜'}
def norm(v):return re.sub(r'[\W_]+','',unicodedata.normalize('NFKC',str(v))).removeprefix('请问')
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def intent(q):
 for k,p in PATTERNS.items():
  if re.fullmatch(p,norm(q)):return k
 return next((k for k,p in INTENTS if re.search(p,q)),'other')
def taxonomy(product,domain):
 t=' '.join(str(product.get(k) or '') for k in ('goods_name','category','category_name','species','tags'))
 if domain=='umbrella':
  if '伞' not in t:return ''
  return 'umbrella/'+('五折' if '五折' in t else '三折' if '三折' in t else '长柄' if '长柄' in t else '折叠' if '折叠' in t else '其他')+'/'+('全自动' if '全自动' in t else '手动' if '手动' in t else '未知开合')
 if '伞' in t:return ''
 names=[x for x in SPECIES if x in t]
 if len(names)!=1:return ''
 return ('artificial/' if re.search('仿真|假花|人造',t) else 'plant/')+names[0]
def clean(raw,domain):
 if domain not in DOMAINS or not isinstance(raw,dict):raise ValueError('invalid domain/item')
 q=str(raw.get('question') or '').strip();a=str(raw.get('answer') or '').strip()
 if not 1<=len(q)<=700 or not 1<=len(a)<=1500:raise ValueError('问答长度无效')
 if PII.search(q+' '+a):raise ValueError('含客户身份、链接或订单信息，不进入共享库')
 cat=str(raw.get('category') or '')[:120];it=intent(q)
 ev=raw.get('evidence') or []
 if not isinstance(ev,list) or len(ev)>12 or any(not isinstance(x,str) or len(x)>1200 or PII.search(x) for x in ev):raise ValueError('证据格式或隐私检查失败')
 colors=sorted(set(x for x in (raw.get('colors') or []) if x in COLORS))
 if it in GENERAL:cat='general';colors=[];ev=[]
 if cat!='general' and not (cat.startswith('umbrella/') if domain=='umbrella' else cat.startswith(('plant/','artificial/'))):raise ValueError('品类无法确认或版本不匹配')
 if cat=='general' and it not in GENERAL:raise ValueError('非通用接待不得扩为全局')
 if it=='color' and not colors:colors=sorted(x for x in COLORS if x in q)
 # No source shop, buyer, order, product ID or transcript accepted in the payload.
 return {'domain':domain,'category':cat,'colors':colors,'intent':it,'question':q,'answer':a,'evidence':list(dict.fromkeys(ev)),'verified':raw.get('verified') is True}
def assess(d):
 text=d['question']+' '+d['answer']+' '+''.join(d['evidence'])
 if BAD.search(text):return 'rejected','含不良语气、指令或身份误导'
 if CASE.search(text) or VOLATILE.search(text):return 'review','涉及个案或动态政策，不自动跨店复用'
 if d['category']=='general':
  if norm(d['answer'])==norm(GENERAL[d['intent']][1]):return 'approved','通用低风险接待'
  polite=norm(d['answer'])
  for word in sorted(('亲亲','亲','您好','你好','您','你','在呢','在的','不客气','不用谢','谢谢','感谢','有需要','随时','再','找我','联系我','有什么','可以','帮您','帮你','想了解','什么','呀','哦','哟','呢','啊','好','祝您','生活愉快','再见','拜拜','的','吗'),key=len,reverse=True):polite=polite.replace(word,'')
  if d['verified'] and not polite and len(d['answer'])<=120:return 'approved','老板确认的无事实承诺通用表达'
  return 'review','通用回复包含非标准事实或扩展内容'
 if d['intent']=='other' or not d['verified'] or not d['evidence']:return 'review','缺少逐项商品证据'
 if any(n not in ''.join(d['evidence']) for n in re.findall(r'\d+(?:\.\d+)?',d['answer'])):return 'review','数字与证据不一致'
 # A product answer is never a general fact: retrieval must revalidate all evidence.
 return 'approved','已通过本机商品证据审核；复用时仍须当前商品逐项匹配'
def key(d):
 return digest([d['domain'],d['category'],d['colors'],d['intent'],norm(d['question']) if d['intent']=='other' else d['intent'],sorted(norm(x) for x in d['evidence'])])
def fingerprint(d):return digest([key(d),norm(d['answer'])])
def match(d,domain,category,q,current_text):
 if d.get('domain')!=domain or d.get('state')!='approved' or intent(q)!=d.get('intent'):return False
 if PII.search(q) or CASE.search(q):return False
 if d['category']=='general':return intent(q) in GENERAL
 if category!=d['category']:return False
 colors=sorted(x for x in COLORS if x in q)
 if d['colors'] and colors!=d['colors']:return False
 if not d['evidence'] or not all(x in current_text for x in d['evidence']):return False
 return assess(d)[0]=='approved'
