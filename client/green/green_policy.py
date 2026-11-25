"""Green service: per-turn scope, never persist order state or transfer shop promises."""
import re
FREIGHT=re.compile(r'运费险|退货包运费|退货运费保障|退货运费(?:谁|哪|怎么|险|包)|退货.*(?:包不包|谁出)运费')
PLANT=re.compile(r'死苗|苗死|枯死|死了|死掉|养死|不活|没活|烂根|枯萎|包活|包赔|死花|死株|破损|损坏|坏了|补发|赔偿|赔付|售后|(?:这|那|你|这盆|这株|这款|你家|你这|你的|你家的)?(?:花|苗|盆栽|商品|货)(?:儿|好像|好象|怎么|看着)?(?:有问题|不对劲)|质量(?:好像)?有问题')
GIFT=re.compile(r'赠品|随单|赠.{0,3}盆|送.{0,5}(?:花盆|盆|什么)|(?:带|含|配|有|包不包)(?:不带|不含|没有)?(?:花盆|盆)(?:吗|么|嘛|不|[？?]|$)|花盆.{0,6}(?:送|带|含|配)')
POS=re.compile(r'(?:带|含|配|附|赠送|赠|送)(?:一个|个|标配|原装|塑料|陶瓷|育苗|简易|营养|小)?(?:花盆|盆)(?!栽)|原盆原土|带盆发货')
NEG=re.compile(r'(?:不(?:包)?(?:附赠|赠送|含|带|送|配|赠)|不附|无)(?:赠送|原装|标配|塑料|陶瓷|额外)?(?:花盆|盆)(?!栽)|裸根(?:发货|苗)?|仅苗|盆需另购')
VAR=re.compile(r'(?:^|[；;\n])\s*(?:型号|颜色|规格)[：:]\s*([^；;\n]+)')
EXPLICIT=re.compile(r'我(?:刚|已|已经)?(?:收到了?|签收)|(?:寄|发)来.{0,5}(?:死|坏)|到手就|一开箱|我这(?:单|盆).{0,8}(?:死|坏)|我要(?:退|换)|我买的.{0,8}(?:死|坏)')
HYP=re.compile(r'如果|万一|假如|要是|还没买|没下单|打算买')
# Treat the buyer's statement and the status of a matched order as independent evidence.
SYM50=r'(?:枯死了?|枯萎了?|蔫了|死了|死啦|死掉了?|没活(?:成)?|烂根了?|黄了|掉光了|折断了)'
PLANT50=r'(?:我(?:买|收到|养)的|你们(?:家|发来的)|刚收到的|收到的|这|那|我这|我那|我的)?(?:株|盆|棵|束)?(?:玫瑰花?|月季花?|这花|花苗|花儿?|苗|叶子|盆栽|植株|花苞)'
BARE50=re.compile(r'(?:你好[，,、\s]*|亲[，,\s]*)?'+PLANT50+r'(?:好像|看着|已经|都|全|早就|刚|有点|都已经){0,3}'+SYM50+r'[呀啊呢啦哎。！!\s]*')
def report50(q):
    for clause in re.split(r'[；;，,\n。！!]+',str(q)):
        s=clause.strip()
        if BARE50.fullmatch(s):return True
    return False
def hypothetical50(q):
    return bool(HYP.search(q) or re.search(r'会不会.{0,4}(?:死|蔫)|(?:死了|死苗|枯萎了?)(?:的话)?(?:咋办|怎么办|怎么处理|包赔吗|赔吗|能赔吗)',q))
def status50(state,row):
    if state=='closed' or row.get('isFullyRefunded'):return 'closed'
    if state!='verified':return state
    s=str(row.get('order_status_str') or '')
    if re.search(r'已关闭|交易关闭|退款成功|已退款',s):return 'closed'
    if re.search('待发货|未发货',s):return 'unshipped'
    if re.search('已签收|已收货',s):return 'received'
    return 'unknown'
def report_reply50(part,state,row):
    if not BARE50.fullmatch(part.strip()):return ''
    st=status50(state,row)
    if st=='unshipped':return '我帮您看看。这笔订单还没发货，您说的是之前收到的那盆花吗？'
    if st=='received':return '我帮您看看，是拆箱时就这样，还是收到后才慢慢变的？'
    if st=='multiple':return '我帮您看看。您说的是哪一盆花？我好对上那笔订单。'
    return '我帮您看看。您说的是已经收到的那盆花吗？'
def actionable50(v):
    # A tag list describes covered topics, not a remedy. No inference about compensation.
    v=str(v or '').strip()
    if not v or re.search(r'待确认|待补充|暂未设置|话术|后台|模板|示例|仅供参考',v):return False
    return bool(re.search(r'(?:可(?:以)?|能|不支持|支持|免费|予以|负责|给予|安排|不予|不|可申请|只|仅|给您|给你)(?:免费)?(?:补寄|补发|赔付|赔偿|赔|退款|退货|换货|换苗|重发)|(?:包退|包换|包赔|不包赔)|(?:签收|收到|到货).{1,35}(?:内|后).{0,20}(?:拍照|联系|申请)|(?:凭|经|核实后|确认后).{0,16}(?:退款|退货|补发|赔付|换货)',v))
def terms50(rows):
    return [c for c in rows if not re.search(r'赔|补发|保修|保障',str(c.get('主题',''))) or actionable50(c.get('已确认内容',''))]
def mode(q, state, row):
    actual=report50(q) and not (hypothetical50(q) and not EXPLICIT.search(q))
    if actual:return 'claim' if state=='verified' else 'unmatched_claim'
    if not PLANT.search(q):return ''
    if HYP.search(q) and not re.search(r'我要退|我想退|已申请',q):return 'policy'
    if EXPLICIT.search(q):return 'claim' if state=='verified' else 'unmatched_claim'
    if state in ('missing','closed'):return 'policy'
    if state=='verified' and re.search(r'待发货|未发货',str(row.get('order_status_str',''))):return 'policy'
    if state in ('unavailable','known_unavailable','incomplete','multiple') and re.search(r'咋办|怎么办|包不包|保障|管吗|包活',q):return 'conditional'
    return 'claim' if state=='verified' else 'uncertain'
def sign(v):
    v=str(v or ''); n=bool(NEG.search(v));p=bool(POS.search(NEG.sub('',v)))
    return 'choose' if n and p else 'no' if n else 'included' if p else ''
def pot(q,product,selected,gid):
    if not GIFT.search(q):return ''
    product=product or {}; selected=selected or {}
    variants=VAR.findall(str(product.get('specs') or ''))
    card=str(selected.get('card') or '') if str(selected.get('goods_id') or '')==str(gid) else ''
    hits={v.strip() for v in variants if v.strip() and v.strip() in card}
    if len(hits)==1:
        s=sign(next(iter(hits)))
        if s:return s
    signs={sign(x) for x in variants}
    if signs- {''}:
        return signs.pop() if len(signs)==1 else 'choose'
    # Include only catalog assertions; neither a display prop nor 带花苞/盆栽 is an accessory.
    base=VAR.sub('',str(product.get('specs') or ''))
    return sign('；'.join(str(x or '') for x in (product.get('goods_name'),base,product.get('gift'))))
def unrelated(gid,state,row):
    return state=='verified' and bool(gid and row.get('goods_id')) and str(gid)!=str(row.get('goods_id'))
def single_insurance(q):
    return bool(re.fullmatch(r'(?:亲[，, ]*)?(?:这(?:一)?(?:单|款)|这个|请问|那)?(?:有没有|有|送|赠送|带|含|包)?(?:退货包运费|退货运费险|运费险)(?:有吗|送吗|吗|么|嘛|呢|不|呀)?[？?！!。\s]*',q))
def insurance_text(state,row):
    if state=='verified':
        return {'no':'您这单没有赠送退货包运费。','yes':'您这单有退货包运费服务，具体保障范围按订单页面显示。'}.get(row.get('return_freight'),'这笔订单还没核实到运费保障，先以订单页的“退货包运费”为准。')
    if state=='multiple':return '退货包运费要看具体订单，您问的是哪一笔？'
    if state=='missing':return '下单前可以看看结算页，有“退货包运费”标识再按页面说明确认。'
    return '退货包运费要看对应订单的保障标识，暂时还没核实到这笔是否赠送。'
def consult(q,state,row,product,selected,gid,commitments):
    gift=pot(q,product,selected,gid);m=mode(q,state,row)
    if unrelated(gid,state,row) and m and not EXPLICIT.search(q) and not report50(q):m='conditional'
    if m:commitments=terms50(commitments)
    if gift:commitments=[c for c in commitments if not re.search('赠|配件|随单',str(c.get('主题','')))]
    plan={}
    if m: plan['花苗保障']= {'policy':'按售前保障条件答，不说客户已经收货或已死苗，不让现在发图或单号。','conditional':'条件式回答已发布保障。订单尚未确定，不宣称无订单，不叫买家拍照。','claim':'根据本轮订单、是否已收货、买家陈述处理；证据确有必要且未提供时再索取。','unmatched_claim':'买家明确报告实情但没有匹配到对应订单，不能把投诉改说成售前，也不假称买过；先澄清必要一项。','uncertain':'不确定是否已实际发生，先说明条件；不把买家当已收货。'}[m]
    if gift:plan['花盆依据']={'included':'当前商品或已选规格明确带盆，只表达随货有盆，不说额外送一个。','no':'当前规格不含花盆/裸根发货；不能使用通用送盆覆盖。','choose':'不同规格、或标注不一致；只问选的带盆款还是裸根款，不承诺所有款送盆。'}[gift]
    elif GIFT.search(q):plan['随单赠品']='商品或规格没有明确约定才按已发布通用赠品政策；只说政策里的配件，不从花苞、盆栽、摆拍图推断赠品。'
    if FREIGHT.search(q):plan['退货运费保障']=insurance_text(state,row)
    return m,gift,plan,commitments
def problems(q,text,m,gift,state,row):
    issues=[]
    if m in ('policy','conditional') and re.search(r'(?:麻烦|您先|请|把|给我|发我|发给我|先拍|拍一张|拍张|拍照发).{0,12}(?:拍|照片|发我|发给|订单号)|(?:照片|图片|订单号).{0,3}(?:发我|发给我)',text):issues.append('是假设保障咨询，不索取当前实拍或单号；如果政策要求留证，用将来条件句陈述')
    if FREIGHT.search(q):
        if not FREIGHT.search(text):issues.append('漏答这笔订单的退货运费保障')
        elif state=='verified' and row.get('return_freight')=='no' and not re.search(r'未赠|没(?:有)?(?:赠送|运费险|退货包运费)|不含',text):issues.append('订单标识未赠送，必须说未赠送')
    if gift=='no' and POS.search(NEG.sub('',text)):issues.append('当前规格不含盆，不能承诺赠盆')
    return issues
def complaint_text(q,state,row):
    if not re.fullmatch(r'(?:你(?:家|这|家的|的)?|这|这个|这株|这盆|这款)?(?:花|苗|盆栽|商品|货|质量)(?:儿|好像|看着)?(?:有问题|不对劲)[呀啊哦呢吧！？?。！\s]*',q):return ''
    if state=='verified' and re.search('待发货|未发货',str(row.get('order_status_str') or '')) and not row.get('isFullyRefunded'):
        return '这笔订单还没发货。您指的是页面上这款花，还是之前收到的那盆？'
    return '您指的是商品页面上的问题，还是已经收到的花有状况？'
def direct_answer(q,state,row,m,gift,commitments,live):
    import hashlib
    parts=[v.strip() for v in re.split(r'[；;\n]+',q) if v.strip()]
    answers=[]
    def choose(options):
        seed=str(live.get('thread_key',''))+q+repr([x.get('msg_id','') for x in live.get('msgs',[])[-2:]])
        return options[int.from_bytes(hashlib.sha256(seed.encode()).digest()[:2],'big')%len(options)]
    for part in parts:
        if m in ('claim','unmatched_claim') and report50(part):
            a=report_reply50(part,state,row)
            if not a:return ''
            answers.append(a);continue
        if status50(state,row)=='unshipped' and re.fullmatch(r'(?:那|我想|我要|想|要|申请)?(?:退货退款|退货|仅退款|退款|退钱)(?:怎么办|怎么退|怎么申请|吧|呀|啊)?[？?。！!\s]*',part):
            answers.append('这笔还没发货，想取消的话，在订单里申请退款就好，不用寄回商品。');continue
        if single_insurance(part):answers.append(insurance_text(state,row));continue
        caution=complaint_text(part,state,row)
        if caution:answers.append(caution);continue
        if re.fullmatch(r'(?:请问|这款|这个|那|请问这款)?(?:送|带|含|配|有没有|有|赠送)(?:不送|不带)?(?:花盆|盆)(?:吗|么|不|嘛|呢|呀)?[？?。！\s]*',part):
            if gift=='no':a=choose(['这个规格不带花盆。','这款按您选的规格发，不含花盆。'])
            elif gift=='included':a=choose(['这个规格是带盆发货的，不用另配花盆。','您选的这款本身就带盆。'])
            elif gift=='choose':a='要分规格看，您选的是带盆款还是裸根款？'
            else:
                terms=[str(x.get('已确认内容','')).strip().strip('。') for x in commitments if re.search('配件|赠品|随单',str(x.get('主题','')))]
                if terms not in (['送标配花盆'],['赠送标配花盆']):return ''
                a=choose(['有的，随单送标配花盆。','会配一个标配花盆一起发。'])
            answers.append(a);continue
        if m in ('policy','conditional') and re.fullmatch(r'(?:如果|万一|那|要是)?(?:花|苗|花苗|这花|这盆花)?(?:死了|死苗|死掉了|养死了|不活)(?:咋办|怎么办|怎么处理|包赔吗|赔吗)?[了呀啊呢？！?。\s]*',part):
            terms=list(dict.fromkeys(str(x.get('已确认内容','')).strip().rstrip('。') for x in commitments if actionable50(x.get('已确认内容','')) and re.search(r'赔|补发|保修|保障',str(x.get('主题',''))) and (not re.search('破损|包装',str(x.get('已确认内容',''))) or re.search('死苗|死株|枯|花死|苗死',str(x.get('已确认内容',''))))))
            if not terms:
                answers.append(choose(['如果收到时花苗状态不对，直接联系店里，我们按实际情况帮您处理。','如果到货时发现花苗有问题，联系这边就好，我们会帮您核实。']));continue
            if terms and all(0<len(x)<=90 and not re.search(r'客服|老板|后台|配置|话术|系统|请.*(?:拍|发).*(?:照片|我)|内部',x) for x in terms):
                answers.append('；'.join(terms)+'。');continue
        return ''
    return ''.join(answers)

# Flower aftersales: observation, identity and settlement are independent decisions.
SERVICE49 = """买家说“花死了”是在反映状况，不擅自说他是提前问，也不因眼前一笔待发货否认另有已收货的订单。先表明愿意帮忙，只核对一项必要信息，再按实际可执行的店铺承诺处理。“花死，包装破损”这样的词是问题分类，不是赔付办法，不能照念或据此许诺。问“万一死苗怎么办”才按条件说明保障。对方尚未发货的这单若要取消，不指导寄回商品。\n像一位熟悉自家商品的小美：先答买家此刻最关心的那件事，能直接办清的别让人做功课；多问逐项答。信息够就给结论和下一步，不够只问一个真正会影响判断的问题。一般一两句话，不套“亲+抱歉+请提供”的格式，不猜买家情绪。
活体售后分清三件事：订单买的是什么、实物现在是什么状态、照片能否对应这笔订单。这三者不能相互代替。优先用已查到的本店订单和所选规格，客服自己能查的不向买家索要。叶子打蔫、运输压弯、花苞没开、光照色差，不能单凭这些说死苗、错品或调包。
收到图片不是已看清图片；若买家明确问照片能否辨清，要正面回答，看不出品种或枯萎程度就说哪一点看不清。叶子是绿的不能否定到货时的状况。仅在图片和已购规格确有明显出入或对应关系影响处理时问是否发的是这盆；已核对过就不再问。能看清只描述与问题有关的可见现象。同品种、颜色相似或同款花盆，也不能证明实物来源。疑似不同也可能是拍错图或商家发错货。信息不足用中性语言，别指责、试探或要求买家自证清白。买家明确要退款就回应退款诉求，不要转成养护教学或一味劝补发。没有执行回执不说已退款、已拒绝、已登记或已转人工。
已经有足够信息就用现有材料；需要区分两盆时才补最小一项：确认照片是否是这单收到的那盆，或看能对上规格的植株标签。没有标签/包装可用整株照或描述，不设开箱视频、面单、身份证、手机号等门槛。不强制同框，不重复索取已给的东西。少量疑点先自己核对；核对后仍有实质争议或买家明确要人工才走已有人工流程。"""
DAMAGE49=re.compile(r'蔫|萎|枯|死苗|苗死|死了|干瘪|干巴|发黄|黄叶|烂根|折断|破损|掉叶|打蔫|发错|错品|货不对|不是.{0,6}(?:买|订|拍|收到|那盆|同一)|另一(?:盆|株)|别的花|拍错|发错图|换.{0,3}照片')
CLAIM49=re.compile(r'我(?:想|要)?(?:仅)?退款|退(?:货|款|钱)|赔|已(?:经)?(?:收到|签收)|收(?:到|货)(?:后|了|就|时)|到(?:货|手)就|刚(?:到货|收货)|拆开|开箱|寄来|发来|买的')
PHOTO49=re.compile(r'^\s*(?:(?:\[?(?:图片|照片|image)\]?|这(?:张|盆|个)|是这盆|发了|拍好了|你看|看看)[，,。!！\s]*)*$',re.I)
def focus49(q,images,live):
    if not images or not PHOTO49.fullmatch(q):return q
    buyers=[x for x in live.get('msgs',[]) if not x.get('system')]
    split=next((i for i in range(len(buyers)-1,-1,-1) if buyers[i].get('self')),-1)
    if split<0:return q
    for x in reversed(buyers[max(0,split-3):split]):
        t=str(x.get('text') or '').strip()
        if x.get('self') or x.get('card') or x.get('order_sn'):break
        if not t or PHOTO49.fullmatch(t):continue
        if DAMAGE49.search(t) and CLAIM49.search(t):
            return t+'；本轮补充实物图片'
        break
    return q
def is_case49(q,images):
    if hypothetical50(q) and not images and not EXPLICIT.search(q) and not re.search('刚收到|已签收|已经签收|到手就|已经死|要退款|申请了',q):return False
    if HYP.search(q) and not re.search(r'刚收到|已经签收|刚签收|我要退|申请了退款',q):return False
    return bool(DAMAGE49.search(q) and (CLAIM49.search(q) or images or re.search('拍错|发错图',q)))
def policy49(state,row,images):
    return {
     '当前买家附图数':len(images or []),
     '订单对应':'以最新订单证据里的商品名及已购规格为准；商品卡、其他SKU、另一单的品种不能代替已购实物。',
     '核对动作':'先用买家已经给的资料；只有对应不上才澄清一项。买家说收到不同品种要同时考虑错发，不先让对方证明。没有图也不能装作看过图。',
     '处理边界':{'missing':'买家明确报告收货但本轮没有匹配订单：不是售前，先问是不是另一笔或另一账号，不索要照片来证明购买。','multiple':'只澄清对应哪笔，不把多单合成一笔。','closed':'相关订单已结束不等于全都退款成功；不承诺再退，也不自动拒绝。','verified':'查过订单不等于证实实物来源；未发货、在途、已签收分开说，收货与状态矛盾时先核对是否另一单。'}.get(state,'查询未完成，不能说无订单，不能虚报已核实状态。'),
     '退款':'可以说明从该订单申请退款并在售后里附现有材料，不把补照片作为允许申请的前提。有效承诺按原条件说明；不因为收到照片自动同意或拒绝退款。'}
def issues49(active,text,images,state,q=""):
    if not active:return []
    if re.search(r'骗(?:我|我们|商家|退款|赔)|骗单|骗保|调包|造假|冒充|恶意退款|不是(?:我们|本店|我家)(?:发的|卖的|的花)|你.{0,4}拿别的花|故意.{0,6}(?:换|拍错|发错)',text):return ['不推断客户动机或实物归属，不作欺诈指控。']
    if re.search(r'(?:不能|不给|不予|拒绝)(?:给您)?(?:退[款钱]|赔付)|(?:已为您|已经给您|我给您|马上给您|直接给您|肯定给您|已同意|已批准)(?:全额)?(?:退款|退钱|赔付)|包(?:赔|退)到底',text):return ['未执行裁决，不承诺或拒绝具体退款。']
    if re.search(r'(?:必须|务必|需要先|只有|一定要).{0,22}(?:开箱视频|快递面单|身份证|手机号)|不(?:拍|发|提供).{0,14}(?:不退|不能退款|不给退)',text):return ['不能设置不必要的举证门槛。']
    if images and re.search('照片能看清|图能看清|看得清|能分辨|能看出',q) and not re.search(r'难以|没法|无法|看不清|看不出|不能确|不确定|不能只凭|对不上|确认.{0,8}是不是|这单收到|辨认|对应|未能|同一株',text):return ['能看到外观不等于能辨认品种和对应哪一单；回答哪一点仍不能确认。']
    if images and re.search(r'(?:这(?:株|盆|棵)|图[中里上]|照片[中里上]|图片[中里上]|枝叶看起来)[^，。！？；]{0,18}(?:月季|玫瑰|桂花|栀子|牡丹|兰花|茉莉|绣球|茶花|百合|杜鹃)|(?:照片|图片).{0,12}(?:就是|确实是|肯定是)',text):return ['订单名称只能用来描述订单，不拿它给照片中的植株定品种。']
    if images and re.search(r'(?:仅凭|从|根据|看).{0,6}(?:图片|照片|叶子).{0,10}(?:证明|断定|肯定是|确定就是)|(?:肯定|确定)不是您(?:买的|购买的)',text):return ['照片不足以证明订单归属或责任，陈述可观察现象即可。']
    if not images and re.search(r'(?:图中|从(?:图|照片)上|照片(?:上|里)|我看到(?:图|照片)).{0,12}(?:看|叶|花|枯|不符|能确定)',text):return ['本轮没有可看的图片，不编造图像内容。']
    return []
def fallback49(q,state,row,images,prior):
    if not CLAIM49.search(q) or re.search(r'运费|花盆|几天|多久|多少钱|赠品|补发|怎么养|浇水|保修|几株|另外|还有.{1,5}(?:吗|么)',q):return ''
    wants=bool(re.search(r'退款|退钱|退货',q))
    if not wants:return ''
    if state=='closed' or row.get('isFullyRefunded'):
        return '查到的订单已经结束了。您想核对之前的退款进度，还是另一笔花苗订单？'
    if state=='multiple':return '您有不止一笔订单。想退的是哪款花？我按那笔帮您核对。'
    if state=='missing':return '这边暂时没找到对应的订单。您可以把买这盆花的订单卡发来，我按那笔帮您核对退款。'
    if state!='verified':return '退款要按买这盆花的那笔订单处理。您可以从对应订单申请，我这边还没核实到它的状态。'
    if re.search('待发货|未发货',str(row.get('order_status_str',''))):
        return '查到这笔还待发货。您说的是另外哪笔花苗订单？我按那笔帮您核对退款。'
    if re.search('发错图|拍错|另[一外]盆',q):return '没关系，您可以在这笔订单申请退款，附上实际收到的那盆花的照片就好。'
    if re.search('扔了|丢了|没有包装|没标签',q):return '包装不在了没关系。您可以在这笔订单申请退款，说明花到手时的状况，有现成的照片就附上。'
    if '发来' in q and re.search('别的|不是|不同',q):return '有可能是发错了，我们按您实际收到的花核对。您可以在这笔订单申请退款，说明收到的和所选规格哪里不同。'
    if images:return '单凭这张照片还不能确认是不是订单里的那株。您发的是这单收到的花吗？可以先在这笔订单申请退款。'
    return '收到花就蔫了，您可以从这笔订单申请退款，说明到货时的状况；有现成的实物照就一起附上。'