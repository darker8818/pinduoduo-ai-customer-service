"""Order status, not the buyer's photo or a previous seller reply, gates aftersales."""
import re
MARK='【本轮售后查单】'
DAMAGE=re.compile(r'死了|死啦|死苗|枯|蔫|烂根|黄叶|发黄|坏了|破损|压坏|碎了|断了|漏发|少发|错发|发错|货不对|花.{0,3}有问题')
RETURN=re.compile(r'退款|退钱|退货|赔付|赔偿|补发|换货|退一下|钱.{0,3}没到[账帐]')
ARRIVED=re.compile(r'刚(?:签收|收货|收到)|已经(?:收货|签收|收到)|收到(?:后|了|的|就|时)|(?:收货|到货|拿到|到手)(?:后|就|了)|拆(?:开|箱)|开箱')
HYP=re.compile(r'如果|万一|要是|假如|还没(?:买|下单)|打算买|会不会')
MIX=re.compile(r'材质|规格|直径|半径|几骨|尺寸|颜色|花色|品种|参数|属性|多高|多大|送盆|带盆|送花盆|有盆|赠品|运费险|包运费|怎么养|浇水|包邮|保修|保质|拍错|发错图|扔了|没有包装|看得清|能看清|多久发货|什么时候发|多少钱|转人工')
def claim(q,images):
    s=str(q or '')
    if re.search(r'退货包运费|退货运费险',s) and not (DAMAGE.search(s) or re.search(r'我要退|我想退|我申请',s)):return False
    if re.search(r'支持(?:退货|退款)|(?:可以|能)(?:退货|退款)吗|售后保障|有.{0,3}保障吗',s) and not (ARRIVED.search(s) or re.search(r'我这单|这笔订单|我买的|我要|我想',s)):return False
    if HYP.search(s) and not re.search(r'刚收到|已经签收|刚签收|我已经收到|已申请',s):return False
    if re.search(r'(?:死了|坏了|死苗|碎了)(?:的话)?(?:怎么办|咋办|怎么处理|包赔吗)',s) and not re.search(r'我收到的|刚收到|已(?:经)?签收|一开箱|拆开|到手就|已经死|我这盆',s) and not images:return False
    return bool(RETURN.search(s) or DAMAGE.search(s) or ('售后' in s and re.search('申请|处理|我的|进度',s)))
def physical(q):
    return bool(DAMAGE.search(q)) and not HYP.search(q)
def simple(q):
    # Card body is the referenced order, not a second customer question. Leave all real text segments.
    q=re.sub(r'(?:^|[；;])\s*\[ORDER_CARD\][^；;]*','',q)
    if MIX.search(q):return False
    # Every pending segment must be explained by the shortcut. Preserve other topics.
    for s in re.split(r'[；;，,。！？?!\n]|另外|还有|顺便|以及',q):
        s=s.strip()
        if s and not (DAMAGE.search(s) or RETURN.search(s) or ARRIVED.search(s) or re.fullmatch(r'(?:\[?(?:图片|照片)\]?|你好|在吗|人捏|人呢|怎么处理|怎么办|帮我看看|您看|亲|.{0,10}的花)',s)):return False
    return True
def facts(row):
    r=row or {}
    ship=' '.join(str(r.get(k) or '') for k in ('order_status_str','panel_order_status'))
    after=' '.join(str(r.get(k) or '') for k in ('after_sales_status_str','after_sale_status_str','aftersales_status_str','afterSalesStatusText','refund_status_str','panel_support_status'))
    text=ship+' '+after
    no=bool(re.search('未发货|待发货|尚未发货|没有发货',text))
    yes=bool(re.search(r'已发货|已签收|已收货|已送达|运输中|待收货|待签收|已揽收',ship))
    partial=bool(re.search('部分退款|部分退回|部分退[款钱]|退部分',text))
    paid=bool(r.get('isFullyRefunded') is True or re.search(r'退款成功|(?<!部分)已退款|已全额退款|全额退款成功|退款已完成',text))
    pending=bool(re.search(r'退款中|退款处理中|退款审核中|退款申请中|待商家处理|待平台处理|待退款',text))
    closed=bool(re.search('交易关闭|订单关闭|订单已取消|交易已关闭',ship))
    conflict=(no and yes) or (paid and pending) or (partial and r.get('isFullyRefunded') is True)
    return ('conflict' if conflict else 'partial' if partial else 'refunded' if paid else 'pending' if pending else 'closed' if closed else '', 'unshipped' if no and not yes else 'received' if re.search('已签收|已收货|已送达',ship) else 'shipped' if yes else '')
def pick(panel,biz,shop,intent):
    from . import scoped_goods
    state,r=scoped_goods.match_order(panel,biz,shop,intent)
    ids=set(panel.get('orders') or []); req=set(re.findall(r'(?<!\d)\d{6}-\d{10,22}(?!\d)',intent))
    wanted=req or ids
    if len(wanted)!=1 or not wanted.issubset(ids):return state,r
    sn=next(iter(wanted));matches=[v for v in panel.get('records',[]) if v.get('id')==sn]
    if len(matches)!=1 or state not in ('verified','unavailable'):return state,r
    if state=='verified' and str(r.get('order_sn'))!=sn:return 'incomplete',{}
    item=matches[0];extra={'panel_order_status':item.get('status',''),'panel_support_status':item.get('after','')}
    if state!='verified':
        if str(panel.get('count'))!=str(len(ids)) or facts(extra) not in (('refunded','unshipped'),('pending','unshipped')):return state,r
        r={'order_sn':sn}
    merged=dict(r,**extra)
    if facts(merged)[0]=='conflict':return 'incomplete',{}
    return 'verified',merged
def subject(row):
    s=str(row.get('goods_name') or '')
    for n in ('迷你玫瑰','月季','玫瑰','洋桔梗','郁金香','绿萝','薰衣草'):
        if n in s:return '这笔'+n+'订单'
    return '这笔订单'
def answer(q,state,r):
    if not simple(q):return ''
    if state!='verified' and physical(q):
        if state=='multiple':return '我帮您看看。您说的是哪一盆花？点一下对应的订单卡就好。'
        if state=='missing':return '我帮您看看。您说的是已经收到的那盆花吗？把对应的订单卡发我就好。'
        if state in ('unavailable','incomplete','known_unavailable'):return '我帮您看看。您说的是已经收到的那盆花吗？这边暂时没核实到对应的订单。'
        if state=='closed':return '这边看到的订单已经结束了。您说的是之前收到的另一盆花吗？'
    if state!='verified' and RETURN.search(q):
        if state=='multiple':return '您想核对哪笔订单的退款？点一下对应订单卡就好。'
        if state in ('missing','closed','unavailable','incomplete','known_unavailable'):return '我帮您核对退款。您指的是哪一笔？可以把对应订单卡发我。'
    if state!='verified':return '' 
    status,shipment=facts(r);item=subject(r);report=physical(q)
    if status=='refunded':
        msg=(item+'没发货，已经退款了。' if shipment=='unshipped' else item+'显示退款成功。')
        if report:
            return msg+('您说的是之前收到的另一盆花吗？我帮您核对那一单。' if shipment=='unshipped' else '您说的是这笔已经退款的订单，还是另一盆花？')
        return msg+('到账进度可以在这笔订单的退款详情里看。' if re.search(r'钱|到[账帐]|进度|到哪',q) else '不用再提交退款申请。')
    if status=='pending':
        return item+'的退款正在处理，不用重复提交。'+('您说的是之前收到的另一盆花吗？' if report and shipment=='unshipped' else '')
    if status=='closed':
        return item+'已经关闭。'+('您说的是之前收到的哪一盆花？' if report else '您想核对这笔的退款进度，还是另一笔订单？')
    if status=='partial':
        return item+'有部分退款记录。'+('您说的是哪一盆花？我按对应的订单帮您核对。' if report else '您想核对已退的这部分，还是剩下的金额？')
    if not status and shipment=='unshipped' and report:
        return '我帮您看看。这笔订单还没发货，您说的是之前收到的那盆花吗？'+('我按那一单核对退款。' if RETURN.search(q) else '')
    return ''
def guard(q,state,row,ans):
    if state not in ('verified','closed'):return []
    status,shipment=facts(row) if state=='verified' else ('closed','')
    if status not in ('refunded','pending','closed','partial','conflict'):return []
    # Exclude explicit negatives but do not let one negative license a later positive instruction.
    s=re.sub(r'(?:不(?:用|需要|必)|无需)(?:再次|重新|重复|再)?(?:在.{0,9})?(?:申请|提交)(?:退款|售后|退货|申请)?','',str(ans or ''))
    if status=='conflict':return ['订单状态不一致，先核对，不指导操作']
    if re.search(r'(?:申请|发起|提交|点选|选择|点击|点开|进入).{0,8}(?:退款|退货|售后)|(?:点|去).{0,4}(?:退款|退货)|(?:退款|退货|售后).{0,3}(?:提交|申请一下)|(?:请|先|要|直接|把|附上|补充).{0,12}(?:寄回|拍照|拍张|上传照片|实物照)|(?:按|走).{0,8}(?:赔付|死苗保障|花苗保障)',s):
        return ['该笔订单不能当成待新办的收货售后；不引导重复申请、寄回、举证或赔付']
    if status!='refunded' and re.search('全额退款成功|全款已退|已经全额退款',s):return ['不能把部分退款、处理中或普通关单说成全额退款']
    if re.search(r'(?:款项|钱|退款).{0,2}(?:已经|已)到[账帐]',s):return ['平台显示退款成功不等于买家账户实收']
    return []
def policy(q,state,row):
    status,ship=facts(row) if state=='verified' else (state,'')
    return {'本单售后':status,'本单物流':ship,'要求':'本轮最新订单为准。已退款不指引重复申请、举证或退寄；没发货不当作已收货。不能排除另有一单，先澄清；退款成功不表示银行卡到账。只有订单状态已核实且与买家反映相符，才继续处理实物证据。多笔不混单、查单失败不是没有订单。'}
