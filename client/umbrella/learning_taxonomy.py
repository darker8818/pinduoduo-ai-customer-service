"""Continuing classification; cross-product examples require current factual evidence."""
import json, re, time
SPECIES = ('儿童伞', '高尔夫伞', '折叠伞', '长柄伞', '雨伞')
COLORS = ('黑色', '白色', '灰色', '米色', '藏青', '粉色', '红色', '黄色', '紫色', '蓝色', '橙色', '绿色', '透明', '混色', '多色')
COLOR_QUERY = re.compile('颜色|配色|什么色|哪种色|黑色|白色|灰色|米色|藏青|粉色|红色|黄色|紫色|蓝色|橙色|绿色|透明|混色|多色')
UNSAFE = re.compile('价格|拼团|库存|优惠|发货|运费|包邮|新疆|西藏|退款|退货|赔|补发|售后|签收|订单|伞套|赠|保证|承诺|机器人|微信|[¥￥]|\\d+(?:\\.\\d+)?元')

def schema(c):
    c.executescript('CREATE TABLE IF NOT EXISTS history_learning_tags(\n      pair_id INTEGER PRIMARY KEY, library_id INTEGER, kind TEXT NOT NULL,\n      species TEXT NOT NULL, colors TEXT NOT NULL, color_specific INTEGER NOT NULL,\n      source_hash TEXT NOT NULL, updated INTEGER NOT NULL);\n      CREATE INDEX IF NOT EXISTS history_tags_lookup ON history_learning_tags(kind,species,library_id);')

def classify(row, question=''):
    from .flower_product import classify as umbrella_classify
    text = ' '.join((str(row.get(k) or '') for k in ('goods_name', 'category', 'category_name', 'species', 'plant_type')))
    category, opening, _ = umbrella_classify(text, [])
    colors = sorted({x for x in COLORS if x in question}) if COLOR_QUERY.search(question) else []
    return {'kind': opening or ('umbrella' if category else 'unknown'), 'species': category, 'colors': colors, 'color_specific': bool(COLOR_QUERY.search(question))}

def product(shop, gid):
    from . import db
    if not gid:
        return None
    return next((r for r in db.list_knowledge(shop, '', 500) if r.get('enabled') and str(r.get('mall_id') or '') == str(shop) and (str(r.get('goods_id') or '') == str(gid))), None)

def tag(ids):
    from . import history_learning as h
    for cid in ids:
        with h.connect() as c:
            schema(c)
            r = c.execute('SELECT * FROM history_learning_pair WHERE id=?', (cid,)).fetchone()
        if not r:
            continue
        p = product(r['shop'], r['goods_id'])
        kb = h.knowledge(r['shop'], r['goods_id'])
        t = classify(p or {}, r['question'])
        with h.connect() as c:
            schema(c)
            c.execute('INSERT OR REPLACE INTO history_learning_tags VALUES(?,?,?,?,?,?,?,?)', (cid, r['library_id'], t['kind'], t['species'], json.dumps(t['colors'], ensure_ascii=False), int(t['color_specific']), kb['hash'] if kb else '', int(time.time())))

def references(shop, gid, q, existing=''):
    from . import history_learning as h
    if h.CASE.search(q) or UNSAFE.search(q):
        return existing
    kb = h.knowledge(shop, gid)
    p = product(shop, gid)
    if not kb or not p:
        return existing
    target = classify(p, q)
    if target['kind'] == 'unknown' or not target['species']:
        return existing
    with h.connect() as c:
        schema(c)
        rows = c.execute("SELECT DISTINCT l.*,t.colors,t.color_specific,t.source_hash\n          FROM history_learning_library l JOIN history_learning_tags t ON t.library_id=l.id\n          JOIN history_learning_pair p ON p.id=t.pair_id\n          WHERE l.enabled=1 AND l.scope='product' AND p.state='learned'\n          AND t.kind=? AND t.species=? AND NOT(l.shop=? AND l.goods_id=?)\n          ORDER BY l.id DESC LIMIT 50", (target['kind'], target['species'], shop, str(gid))).fetchall()
    chosen = []
    seen = set()
    for r in rows:
        if UNSAFE.search(r['question'] + ' ' + r['answer']) or h.BAD.search(r['answer']):
            continue
        if r['color_specific']:
            if not target['color_specific'] or json.loads(r['colors']) != target['colors']:
                continue
        elif target['color_specific']:
            continue
        if h.norm(q) != h.norm(r['question']) and len(set(h.norm(q)) & set(h.norm(r['question']))) < 2:
            continue
        source = h.knowledge(r['shop'], r['goods_id'])
        if source and source['hash'] != r['kb_hash'] or r['source_hash'] != r['kb_hash']:
            continue
        try:
            evidence = json.loads(r['evidence'])
        except (ValueError, TypeError):
            continue
        if not evidence or not all((isinstance(x, str) and len(x) >= 2 and (x in kb['text']) for x in evidence)):
            continue
        if not all((n in kb['text'] for n in re.findall('\\d+(?:\\.\\d+)?', r['answer']))):
            continue
        signature = h.norm(r['answer'])
        if signature in seen or r['answer'] in existing:
            continue
        seen.add(signature)
        chosen.append({'question': r['question'], 'reference': r['answer'], 'species': target['species'], 'colors': target['colors']})
        if len(chosen) >= 2:
            break
    if chosen:
        return existing + '\n同分类审核参考（仅学习表达；事实已逐项对照当前商品，不代表其他客户或订单）：' + json.dumps(chosen, ensure_ascii=False)
    return existing
