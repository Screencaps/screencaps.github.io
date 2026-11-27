from datetime import datetime
import csv
import io
import re
import shutil
import urllib.request
from pathlib import Path
from html import escape
from urllib.parse import urlencode, urlsplit
import xml.etree.ElementTree as ET
from download_posters import prepare_posters

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'public'
SITE = 'https://screencaps.github.io/'
BASE = 'https://docs.google.com/spreadsheets/d/e/2PACX-1vTw52xscROjuju9tOk7TlUbx3Q6FAx60jvxgduKYNGkUhySgePAGoRuZqaqWh-UjnuTBhcuucFXvHVC/pub'
SHEETS = {'Фильмы':0,'Сериалы':1699969347,'Мультфильмы':153837603,'Дорамы':895187217,'Мультсериалы':484338684,'Серии':1847353801,'Жанры':834653010}

def read_sheet(name):
    url = BASE + '?' + urlencode({'gid': SHEETS[name], 'single':'true', 'output':'csv'})
    req = urllib.request.Request(url, headers={'User-Agent':'SCREENCAPS catalog builder'})
    with urllib.request.urlopen(req, timeout=60) as response:
        text = response.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    required = {'Жанр'} if name == 'Жанры' else ({'ID серии','ID произведения','Сезон','Номер серии','Статус','Альбом ВК','Пост ВК','Дата обновления материалов'} if name == 'Серии' else {'ID','Русское название','Статус'})
    if not required.issubset(set(reader.fieldnames or [])):
        raise ValueError(f'Неверные заголовки листа: {name}')
    return [{k:(v or '').strip() for k,v in row.items() if k is not None} for row in reader]

def published(r): return r.get('Статус','').casefold() == 'опубликовано'
def e(s): return escape(str(s or ''), quote=True)
def safe_url(s, vk=False):
    try:
        u=urlsplit(s)
        if u.scheme=='https' and u.hostname and (not vk or u.hostname in {'vk.ru','vk.com','m.vk.ru','m.vk.com'}): return s
    except ValueError: pass
    return ''
def vk_urls(value):
    result=[]
    for raw in str(value or '').split():
        url=safe_url(raw,True)
        if not url: continue
        u=urlsplit(url)
        if u.username or u.password: continue
        if url not in result: result.append(url)
    return result

def vk_link(s,label):
    urls=vk_urls(s)
    return ''.join(f'<a class="vk" href="{e(url)}" target="_blank" rel="noopener noreferrer">{e(label + (" №"+str(i) if len(urls)>1 else ""))}</a>' for i,url in enumerate(urls,1))
def filter_link(key,value,label): return f'<a class="chip" href="/?{e(urlencode({key:value}))}">{e(label)}</a>'
def number_key(s): return (0,int(s)) if s.isdigit() else (1,s)

# Retired SCREENCAPS IDs: keep old static URLs without indexing duplicates.
def write_merged_redirects(out):
    redirects = {'films/MS00059.html': 'films/MS00058.html'}
    redirects.update({f'episodes/MS00059-S01E{i:02d}.html':
                      f'episodes/MS00058-S02E{i:02d}.html' for i in range(1,44)})
    # Validate the whole plan before writing any redirect.
    for old, new in redirects.items():
        if (out / old).exists():
            raise ValueError(f'Зарезервированный адрес уже занят: {old}')
        if not (out / new).is_file():
            raise ValueError(f'Нет целевой страницы перенаправления: {new}')
    for old, new in redirects.items():
        target = e(SITE + new)
        page = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
                f'<title>Страница перенесена — SCREENCAPS</title>'
                f'<meta name="robots" content="noindex,follow">'
                f'<link rel="canonical" href="{target}">'
                f'<meta http-equiv="refresh" content="0; url={target}">'
                f'</head><body><p>Страница перенесена. '
                f'<a href="{target}">Перейти к новой странице</a>.</p></body></html>')
        (out / old).write_text(page, encoding='utf-8')
    return len(redirects)

def update_date(raw):
    raw = str(raw or '').strip()
    for fmt in ('%d.%m.%Y %H:%M:%S', '%d.%m.%Y %H:%M', '%d.%m.%Y', '%d/%m/%Y', '%Y-%m-%d', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    return None


def collect_updates(rows, episodes, episode_pages):
    parents = {r['ID']: (category, r) for category, r in rows}
    items = []
    def add(date, category, kind, label, href):
        if date:
            items.append(dict(key=date.isoformat(), date=date.strftime('%d.%m.%Y'), category=category, kind=kind, label=label, href=href))
    for category, r in rows:
        add(update_date(r.get('Дата добавления')), category, 'work', r['Русское название'] + (' (' + r['Год выпуска'] + ')' if r.get('Год выпуска') else ''), '/films/'+r['ID']+'.html')
    for ep in episodes:
        ident=ep.get('ID серии',''); parent=parents.get(ep.get('ID произведения',''))
        if not parent or ident not in episode_pages or not published(ep) or not (vk_urls(ep.get('Альбом ВК','')) or vk_urls(ep.get('Пост ВК',''))):
            continue
        category, r=parent
        add(update_date(ep.get('Дата обновления материалов')), category, 'episode', r['Русское название']+' — сезон '+ep['Сезон']+', серия '+ep['Номер серии'], episode_pages[ident])
    return sorted(items, key=lambda item:(item['key'],item['href']), reverse=True)


def write_updates_page(head, footer, banner, items):
    h=re.sub(r'<title>.*?</title>', '<title>Последние обновления — SCREENCAPS</title>', head, count=1, flags=re.S)
    h=re.sub(r'<meta name="description"[^>]*>', '<meta name="description" content="Новые произведения и обновления материалов серий SCREENCAPS.">', h, count=1)
    h=h.replace('href="favicon.svg"','href="/favicon.svg"').replace('src="vk-config.js"','src="/vk-config.js"')
    h+='<link rel="canonical" href="https://screencaps.github.io/updates.html"><style>.update-row{padding:12px 0;border-bottom:1px solid #45454a}.update-row a{display:block;font-weight:600}.update-controls{display:flex;gap:12px;flex-wrap:wrap}.update-day{margin:22px 0}</style></head><body>'
    body='<header><div><h1><a class="brand" href="/">SCREEN<span>CAPS</span></a></h1><nav class="topnav"><a href="/">Каталог</a><a href="/updates.html" aria-current="page">Обновления</a><a href="/hunger-games.html">Голодные игры</a><a href="/services.html">Услуги</a><a href="/about.html">О проекте</a><a href="/team.html">В команду</a><a href="https://vk.ru/screencaps" id="groupLink" target="_blank" rel="noopener noreferrer">Группа ВКонтакте</a></nav></div></header><main><h2>Последние обновления</h2><p>Новые произведения и обновлённые материалы серий. Даты берутся из каталога. Старые серии без подтверждённой даты обновления не включены.</p><div class="panel update-controls"><label>Тип <select id="updateKind"><option value="">Все обновления</option><option value="work">Новые произведения</option><option value="episode">Материалы серий</option></select></label><label>Категория <select id="updateCategory"><option value="">Все категории</option>'
    body+=''.join(f'<option>{e(cat)}</option>' for cat in list(SHEETS)[:5])+'</select></label></div><p id="updateCount" aria-live="polite"></p>'
    days={}
    for item in items: days.setdefault(item['date'], []).append(item)
    for day, group in days.items():
        body+=f'<section class="panel update-day"><h3>{e(day)}</h3>'
        for item in group:
            label='Новое произведение' if item['kind']=='work' else 'Обновлены материалы серии'
            body+=f'<article class="update-row" data-kind="{e(item["kind"])}" data-category="{e(item["category"])}"><small>{label} · {e(item["category"])}</small><a href="{e(item["href"])}">{e(item["label"])}</a></article>'
        body+='</section>'
    body+='<p id="updateEmpty" hidden>Нет обновлений по выбранным параметрам.</p></main><script>function filterUpdates(){const k=document.getElementById("updateKind").value,c=document.getElementById("updateCategory").value;let n=0;for(const day of document.querySelectorAll(".update-day")){let m=0;for(const row of day.querySelectorAll(".update-row")){row.hidden=!!((k&&row.dataset.kind!==k)||(c&&row.dataset.category!==c));if(!row.hidden)m++}day.hidden=!m;n+=m}document.getElementById("updateCount").textContent="Обновлений: "+n;document.getElementById("updateEmpty").hidden=!!n}document.getElementById("updateKind").onchange=filterUpdates;document.getElementById("updateCategory").onchange=filterUpdates;filterUpdates();</script>'
    (OUT/'updates.html').write_text(h+body+footer+banner+'</body></html>',encoding='utf-8')



# Browser-local favorites, recent works and random selection.
def write_library(head, footer, banner, rows, sheets, episode_pages, poster_for):
    import json
    def encoded(value):
        return json.dumps(value, ensure_ascii=True).replace('<', '\\u003c')
    records = [dict(id=r['ID'], title=r['Русское название'], category=c, year=r.get('Год выпуска',''), href='/films/'+r['ID']+'.html', poster=poster_for(r)) for c,r in rows]
    parents = {r['ID серии']:r['ID произведения'] for r in sheets['Серии'] if r.get('ID серии') in episode_pages}
    js = LIBRARY_JS.replace('SC_DATA', encoded(records), 1).replace('SC_EPISODES', encoded(parents), 1)
    (OUT/'sc-library.js').write_text(js, encoding='utf-8')
    for mode,title,empty in [('favorites','Избранное','В избранном пока ничего нет.'),('history','История просмотров','История пока пуста.')]:
        h=re.sub(r'<title>.*?</title>', lambda m:'<title>'+title+' — SCREENCAPS</title>',head,count=1,flags=re.S)
        h=re.sub(r'<meta name="robots"[^>]*>','',h,flags=re.I)
        h=re.sub(r'<meta name="description"[^>]*>','',h,flags=re.I)
        h=h.replace('href="favicon.svg"','href="/favicon.svg"').replace('src="vk-config.js"','src="/vk-config.js"')
        h+='<meta name="robots" content="noindex,follow"></head><body>'
        body='<header><div><h1><a class="brand" href="/">SCREEN<span>CAPS</span></a></h1><nav class="topnav"><a href="/">Каталог</a><a href="/updates.html">Обновления</a><a href="/hunger-games.html">Голодные игры</a><a href="/services.html">Услуги</a><a href="/about.html">О проекте</a><a href="/team.html">В команду</a><a id="groupLink" href="https://vk.ru/screencaps" target="_blank" rel="noopener noreferrer">Группа ВКонтакте</a></nav></div></header><main><h2>'+title+'</h2><p>Список хранится в этом браузере. Регистрация не требуется.</p><p id="sc-storage-notice" hidden>Хранилище браузера недоступно: изменения могут не сохраниться.</p><div class="panel sc-library-controls"><label>Категория <select id="sc-library-category"><option value="">Все категории</option>'
        body+=''.join('<option>'+e(c)+'</option>' for c in list(SHEETS)[:5])
        body+='</select></label><label>Сортировка <select id="sc-library-sort"><option value="new">Сначала последние</option><option value="old">Сначала ранние</option><option value="az">По названию</option></select></label><button type="button" id="sc-library-clear">Очистить список</button></div><p id="sc-library-count" aria-live="polite"></p><p id="sc-library-missing"></p><p id="sc-library-empty" hidden>'+empty+'</p><div id="sc-library-grid" class="sc-library-grid"></div><noscript>Для работы списка включите JavaScript.</noscript></main>'
        (OUT/(mode+'.html')).write_text(h+body+footer+banner+'</body></html>',encoding='utf-8')

LIBRARY_JS = '(function(){\'use strict\';\nconst items=SC_DATA, byId=new Map(items.map(x=>[x.id,x])), episodes=SC_EPISODES;\nconst keys={favorites:\'sc_favorites_v1\',history:\'sc_history_v1\'}, memory={}, failed=new Set();\nconst mode=location.pathname===\'/favorites.html\'?\'favorites\':location.pathname===\'/history.html\'?\'history\':null;\nfunction canonical(id){return id===\'MS00059\'?\'MS00058\':id}\nfunction read(k){let raw;try{raw=failed.has(k)?memory[k]:localStorage.getItem(keys[k]);}catch{raw=memory[k];failed.add(k)}let a;try{a=JSON.parse(raw||\'[]\')}catch{a=[]}const m=new Map();for(const x of Array.isArray(a)?a:[]){if(!x||typeof x.id!==\'string\'||!Number.isFinite(x.at))continue;const id=canonical(x.id);if(!m.has(id)||m.get(id)<x.at)m.set(id,x.at)}return [...m].map(([id,at])=>({id,at})).sort((a,b)=>b.at-a.at)}\nfunction write(k,a){const raw=JSON.stringify(a);memory[k]=raw;try{localStorage.setItem(keys[k],raw);failed.delete(k)}catch{failed.add(k)}sync();if(mode===k)render();}\nfunction node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el}\nfunction visible(k){return read(k).filter(x=>byId.has(x.id))}\nfunction toggle(id){id=canonical(id);if(!byId.has(id))return;const a=read(\'favorites\');write(\'favorites\',a.some(x=>x.id===id)?a.filter(x=>x.id!==id):[{id,at:Date.now()},...a])}\nfunction button(id,compact){const b=node(\'button\',\'\',compact?\'sc-fav sc-fav-mini\':\'sc-fav\');b.type=\'button\';b.dataset.scFav=id;b.dataset.compact=compact?\'1\':\'0\';b.onclick=()=>toggle(id);paint(b,new Set(read(\'favorites\').map(x=>x.id)));return b}\nfunction paint(b,set){const on=set.has(b.dataset.scFav);b.setAttribute(\'aria-pressed\',String(on));b.title=on?\'Удалить из избранного\':\'Добавить в избранное\';b.setAttribute(\'aria-label\',b.title);b.textContent=(on?\'♥\':\'♡\')+(b.dataset.compact===\'1\'?\'\':on?\' В избранном\':\' В избранное\')}\nfunction sync(){const set=new Set(read(\'favorites\').map(x=>x.id));document.querySelectorAll(\'[data-sc-fav]\').forEach(b=>paint(b,set));for(const k of Object.keys(keys)){const n=document.querySelector(\'[data-sc-count="\'+k+\'"]\');if(n)n.textContent=String(visible(k).length)}const notice=document.getElementById(\'sc-storage-notice\');if(notice)notice.hidden=!failed.size}\nfunction visit(id){id=canonical(id);if(!byId.has(id))return;write(\'history\',[{id,at:Date.now()},...read(\'history\').filter(x=>x.id!==id)].slice(0,500))}\nwindow.scLibraryCard=function(a,id){if(!byId.has(id))return a;const wrap=node(\'div\',undefined,\'sc-card-wrap\');wrap.append(a,button(id,true));return wrap};\nwindow.scLibraryDetail=function(box,id){id=canonical(id);if(!byId.has(id))return;const h=box.querySelector(\'h2\');if(h&&!box.querySelector(\'[data-sc-fav]\'))h.after(button(id,false));visit(id)};\nfunction current(){const p=location.pathname,m=/^\\/films\\/([\\w-]+)\\.html$/.exec(p),ep=/^\\/episodes\\/([\\w-]+)\\.html$/.exec(p);return m?canonical(m[1]):ep?episodes[ep[1]]:new URLSearchParams(location.search).get(\'film\')||\'\'}\nfunction addNav(){for(const nav of document.querySelectorAll(\'header .topnav\')){if(nav.querySelector(\'[data-sc-library-nav]\'))continue;for(const [k,label] of [[\'favorites\',\'Избранное\'],[\'history\',\'История\']]){const a=node(\'a\',label+\' (\');a.href=\'/\'+k+\'.html\';a.dataset.scLibraryNav=\'1\';if(mode===k)a.setAttribute(\'aria-current\',\'page\');const count=node(\'span\',\'0\');count.dataset.scCount=k;a.append(count,document.createTextNode(\')\'));nav.append(a)}const b=node(\'button\',\'Случайное произведение\');b.type=\'button\';b.disabled=!items.length;b.onclick=()=>{const others=items.filter(x=>x.id!==current());const pool=others.length?others:items;if(pool.length)location.assign(pool[Math.floor(Math.random()*pool.length)].href)};nav.append(b)}}\nfunction render(){const grid=document.getElementById(\'sc-library-grid\');if(!grid||!mode)return;const category=document.getElementById(\'sc-library-category\').value,sort=document.getElementById(\'sc-library-sort\').value;const all=read(mode), list=all.filter(x=>byId.has(x.id)).map(x=>({...byId.get(x.id),at:x.at})).filter(x=>!category||x.category===category);if(sort===\'az\')list.sort((a,b)=>a.title.localeCompare(b.title,\'ru\'));if(sort===\'old\')list.sort((a,b)=>a.at-b.at);grid.replaceChildren();document.getElementById(\'sc-library-count\').textContent=\'Найдено: \'+list.length;document.getElementById(\'sc-library-empty\').hidden=!!list.length;document.getElementById(\'sc-library-missing\').textContent=all.length-visible(mode).length?\'Недоступных в текущем каталоге записей: \'+(all.length-visible(mode).length):\'\';for(const x of list){const a=node(\'a\',undefined,\'movie\');a.href=x.href;const p=node(\'div\',undefined,\'poster\'),im=node(\'img\');im.alt=x.title;im.loading=\'lazy\';im.onerror=()=>{im.onerror=null;im.src=\'/assets/posters/placeholder.svg\'};im.src=x.poster;p.append(im);const info=node(\'div\',undefined,\'info\');info.append(node(\'strong\',x.title),node(\'small\',[x.year,x.category].filter(Boolean).join(\' · \')),node(\'small\',new Date(x.at).toLocaleString(\'ru-RU\')));a.append(p,info);const wrap=window.scLibraryCard(a,x.id);if(mode===\'history\'){const remove=node(\'button\',\'Удалить из истории\',\'sc-history-remove\');remove.type=\'button\';remove.onclick=()=>write(mode,read(mode).filter(y=>y.id!==x.id));wrap.append(remove)}grid.append(wrap)}sync()}\nfunction init(){addNav();if(mode){document.getElementById(\'sc-library-category\').onchange=render;document.getElementById(\'sc-library-sort\').onchange=render;document.getElementById(\'sc-library-clear\').onclick=()=>{if(read(mode).length&&confirm(\'Очистить весь список?\'))write(mode,[])};render()}else if(/^\\/(films|episodes)\\//.test(location.pathname)){const box=document.querySelector(\'#detail article.panel\');if(box)window.scLibraryDetail(box,current())}sync()}\nwindow.addEventListener(\'storage\',e=>{if(e.key===null||Object.values(keys).includes(e.key)){sync();if(mode)render()}});document.addEventListener(\'DOMContentLoaded\',init);window.addEventListener(\'pageshow\',()=>{sync();if(mode)render()});\n})();\n'
LIBRARY_STYLE = '<style>.sc-card-wrap{position:relative;min-width:0;display:flex;flex-direction:column;gap:5px}.sc-card-wrap>.movie{flex:1}.sc-fav-mini{position:absolute;top:8px;right:8px;z-index:2;min-width:44px;min-height:44px;font-size:24px;line-height:1;background:#171c26;color:#fff;border:1px solid #aaa}.sc-fav[aria-pressed=true]{color:#ff8490}.sc-fav:not(.sc-fav-mini){margin:5px 0 12px}.sc-library-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:18px}.sc-library-controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center}.sc-history-remove{font-size:13px}.sc-library-grid .movie{min-width:0}.sc-library-grid .info{overflow-wrap:anywhere}@media(max-width:500px){.sc-library-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>'
LIBRARY_TAG = LIBRARY_STYLE + '<script src="/sc-library.js"></script>'

def build(sheets, template):
    head=template.split('</head>',1)[0]+LIBRARY_TAG
    if 'scTrackView' not in head: raise ValueError('Не найден код аналитики в исходном index.html')
    banner=template[template.index('<div id="sc-consent"'):].split('</body>',1)[0]
    footer=re.search(r'<footer>.*?</footer>',template,re.S).group()
    rows=[]; seen=set()
    for category in list(SHEETS)[:5]:
        for r in sheets[category]:
            if not published(r): continue
            ident=r.get('ID',''); title=r.get('Русское название','')
            if not title or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',ident): raise ValueError(f'Неверный ID или название: {ident} {title}')
            if ident in seen: raise ValueError(f'Повтор ID: {ident}')
            seen.add(ident); rows.append((category,r))
    local_posters = prepare_posters(rows, ROOT)
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir(); (OUT/'films').mkdir(); (OUT/'episodes').mkdir()
    for p in ROOT.iterdir():
        if p.is_file() and p.suffix in {'.html','.js','.css','.svg','.png','.jpg','.jpeg','.webp','.ico','.txt','.xml'} and p.name not in {'index (1).html','sitemap.xml'}:
            shutil.copy2(p,OUT/p.name)
    if (ROOT/'assets').is_dir():
        shutil.copytree(ROOT/'assets', OUT/'assets', dirs_exist_ok=True)
    # Add team navigation to existing standalone pages when their navigation is present.
    for page_path in OUT.glob('*.html'):
        if page_path.name in {'index.html', 'team.html'}:
            continue
        page_text = page_path.read_text(encoding='utf-8')
        def add_team_nav(match):
            block = match.group(0)
            if '/team.html' in block:
                return block
            return block.replace('</nav>', '<a href="/updates.html">Обновления</a><a href="/team.html">В команду</a></nav>', 1)
        updated = re.sub(r'<nav\b[^>]*class="[^"]*\btopnav\b[^"]*"[^>]*>.*?</nav>', add_team_nav, page_text, flags=re.S)
        if '<nav' in updated and '</head>' in updated and 'sc-library.js' not in updated:
            updated=updated.replace('</head>',LIBRARY_TAG+'</head>',1)
        if updated != page_text:
            page_path.write_text(updated, encoding='utf-8')
    team_page=OUT/'team.html'
    if team_page.is_file():
        text=team_page.read_text(encoding='utf-8')
        if '</head>' in text and 'sc-library.js' not in text:
            team_page.write_text(text.replace('</head>',LIBRARY_TAG+'</head>',1),encoding='utf-8')
    poster_dir = OUT / 'assets' / 'posters'
    poster_dir.mkdir(parents=True, exist_ok=True)
    placeholder = poster_dir / 'placeholder.svg'
    placeholder.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 600"><rect width="400" height="600" fill="#171c26"/><rect x="110" y="190" width="180" height="130" rx="12" fill="none" stroke="#b9a06a" stroke-width="5"/><path d="M110 225h180M150 190l25 35m35-35 25 35" stroke="#b9a06a" stroke-width="5"/><text x="200" y="375" text-anchor="middle" fill="#e8e3da" font-family="sans-serif" font-size="25">SCREENCAPS</text><text x="200" y="410" text-anchor="middle" fill="#b5b5b5" font-family="sans-serif" font-size="16">Постер недоступен</text></svg>', encoding='utf-8')
    poster_map = {}
    for _, r in rows:
        source = local_posters.get(r['ID'])
        if source:
            shutil.copy2(source, poster_dir / source.name)
            poster_map[r['ID']] = SITE + 'assets/posters/' + source.name
    fallback = SITE + 'assets/posters/placeholder.svg'
    def poster_for(r):
        return poster_map.get(r['ID']) or safe_url(r.get('Постер','')) or fallback
    def poster_error(r):
        external = safe_url(r.get('Постер',''))
        candidates = ([external] if r['ID'] in poster_map and external else []) + [fallback]
        import json
        return e('const a='+json.dumps(candidates,ensure_ascii=True)+';const i=Number(this.dataset.attempt||0);if(i>=a.length){this.onerror=null;return;}this.dataset.attempt=i+1;this.src=a[i];')
    (OUT/'.nojekyll').touch()
    urls=[SITE,SITE+'services.html',SITE+'about.html',SITE+'privacy.html',SITE+'team.html',SITE+'updates.html']
    collection = OUT/'hunger-games.html'
    if collection.is_file():
        page = collection.read_text(encoding='utf-8')
        for year in ('2012','2013','2014','2015','2023','2026'):
            matches = [r for category,r in rows if category == 'Фильмы' and r.get('Год выпуска','') == year and (r.get('Русское название','').casefold().startswith('голодные игры') or r.get('Оригинальное название','').casefold().startswith('the hunger games'))]
            if len(matches) != 1:
                continue
            r = matches[0]
            poster = poster_for(r)
            content = (f'<img class="collection-poster" src="{e(poster)}" onerror="{poster_error(r)}" alt="{e(r.get("Русское название",""))}" loading="lazy">' if poster else '')
            album_count = len(vk_urls(r.get('Альбом ВК','')))
            content += f'<p class="collection-status">Фотоальбомов: {album_count}</p>'
            content += f'<a class="collection-link" href="/films/{e(r["ID"])}.html">Открыть карточку фильма</a>'
            page = re.sub(r'<!-- PANEM-'+year+r'-START -->.*?<!-- PANEM-'+year+r'-END -->', lambda m: content, page, count=1, flags=re.S)
        collection.write_text(page,encoding='utf-8')
        urls.append(SITE+'hunger-games.html')
    links=[]; episode_pages={}; episode_count=0
    for category,r in rows:
        ident=r['ID']; title=r['Русское название']; year=r.get('Год выпуска',''); desc=r.get('Описание',''); poster=poster_for(r); path=f'films/{ident}.html'; url=SITE+path; urls.append(url)
        page_title=title+(f' ({year})' if year else '')+' — SCREENCAPS'
        summary=' '.join(desc.split())[:300] or f'{title} — {category.lower()}, кадры и материалы ВКонтакте.'
        h=re.sub(r'<title>.*?</title>',lambda m:f'<title>{e(page_title)}</title>',head,count=1,flags=re.S)
        h=re.sub(r'<meta name="description"[^>]*>',lambda m:f'<meta name="description" content="{e(summary)}">',h,count=1)
        h=h.replace('href="favicon.svg"','href="/favicon.svg"').replace('src="vk-config.js"','src="/vk-config.js"')
        h+=f'<link rel="canonical" href="{e(url)}"><meta property="og:type" content="website"><meta property="og:title" content="{e(page_title)}"><meta property="og:description" content="{e(summary)}"><meta property="og:url" content="{e(url)}">'
        if poster: h+=f'<meta property="og:image" content="{e(poster)}">'
        h+='</head><body>'
        body='<header><div><h1><a class="brand" href="/">SCREEN<span>CAPS</span></a></h1><p>Кино в кадрах · каталог фильмов и сериалов</p><nav class="topnav"><a href="/">Каталог</a><a href="/services.html">Услуги</a><a href="/about.html">О проекте</a><a href="/updates.html">Обновления</a><a href="/team.html">В команду</a><a id="groupLink" href="https://vk.ru/screencaps" target="_blank" rel="noopener noreferrer">Группа ВКонтакте</a></nav></div></header><main><section id="detail"><a href="/" data-sc-back>← Назад к каталогу</a><article class="panel">'
        if poster: body+=f'<div class="poster"><img src="{e(poster)}" onerror="{poster_error(r)}" alt="{e(title)}"></div>'
        body+=f'<h2>{e(title)}</h2><p>{e(r.get("Оригинальное название"))}</p><div class="detailmeta">'
        if year: body+=filter_link('year',year,year+('–'+r['Год окончания'] if r.get('Год окончания') else ''))
        body+=filter_link('category',category,category)
        for genre in re.split('[,;]',r.get('Жанры','')):
            if genre.strip(): body+=filter_link('genre',genre.strip(),genre.strip())
        body+='</div><p>'+e(' · '.join(r[k] for k in ['Страна','Режиссёр','Продолжительность'] if r.get(k)))+'</p>'
        if r.get('Количество сезонов') or r.get('Количество серий'):
            body+='<p>'+e(' · '.join(label+r[k] for k,label in [('Количество сезонов','Сезонов: '),('Количество серий','Серий: ')] if r.get(k)))+'</p>'
        body+=f'<h3>Описание</h3><p>{e(desc or "Описание пока не добавлено")}</p>'
        if category in {'Сериалы','Дорамы','Мультсериалы'}:
            groups={}; used=set()
            for ep in sheets['Серии']:
                if ep.get('ID произведения')!=ident or ep.get('Статус','').casefold() not in {'опубликовано','ожидается'}: continue
                eid=ep.get('ID серии',''); season=ep.get('Сезон',''); num=ep.get('Номер серии','')
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,150}',eid) or not season.isdigit() or not num.isdigit() or int(season)<1 or int(num)<0: raise ValueError(f'Некорректная серия: {eid}')
                if eid in episode_pages or (int(season),int(num)) in used: raise ValueError(f'Повтор серии: {eid}')
                used.add((int(season),int(num))); episode_pages[eid]='/episodes/'+eid+'.html'; groups.setdefault(int(season),[]).append(ep)
            def ready(ep): return published(ep) and bool(vk_urls(ep.get('Альбом ВК','')) or vk_urls(ep.get('Пост ВК','')))
            all_eps=[ep for eps in groups.values() for ep in eps]
            body+=f'<h3 style="clear:both">Сезоны и серии</h3><p>Добавлено {sum(ready(ep) for ep in all_eps)} из {len(all_eps)} серий</p>'
            for season,eps in sorted(groups.items()):
                eps.sort(key=lambda ep:int(ep['Номер серии']))
                bonus_count=sum(int(ep["Номер серии"])==0 for ep in eps)
                season_label=f"{len(eps)-bonus_count} серий" + (f" + {bonus_count} бонусная" if bonus_count else "")
                body+=f'<details{" open" if season==min(groups) else ""}><summary>Сезон {season} · {e(season_label)}</summary><div class="episode-grid">'
                for i,ep in enumerate(eps):
                    eid=ep['ID серии']; num=ep['Номер серии']; ep_path=episode_pages[eid]; available=ready(ep)
                    episode_label = f"Серия {num}" + (" — Бонусная серия" if int(num)==0 else "")
                    body+=f'<a class="episode-card" href="{e(ep_path)}"><strong>{e(episode_label)}</strong><small class="{"episode-ready" if available else ""}">{"Добавлена" if available else "Ожидается"}</small></a>'
                    ep_url=SITE.rstrip('/')+ep_path; ep_title=f'{title} — сезон {season}, серия {num} — SCREENCAPS'; ep_summary=f'{title}: сезон {season}, серия {num}. '+('Кадры и материалы ВКонтакте.' if available else 'Материалы пока не добавлены.')
                    eh=re.sub(r'<title>.*?</title>',lambda m:f'<title>{e(ep_title)}</title>',h,count=1,flags=re.S)
                    eh=re.sub(r'<meta name="description"[^>]*>',lambda m:f'<meta name="description" content="{e(ep_summary)}">',eh,count=1)
                    eh=re.sub(r'<meta property="og:(title|description|url)"[^>]*>',lambda m:f'<meta property="og:{m[1]}" content="{e({"title":ep_title,"description":ep_summary,"url":ep_url}[m[1]])}">',eh)
                    eh=eh.replace(f'href="{e(url)}"',f'href="{e(ep_url)}"')
                    if not available: eh=eh.replace('content="index,follow"','content="noindex,follow"')
                    eb=body.split('<main>',1)[0]+f'<main><section id="detail"><a href="/{e(path)}">← Назад к сериалу</a><article class="panel">'
                    if poster: eb+=f'<div class="poster"><img src="{e(poster)}" onerror="{poster_error(r)}" alt="{e(title)}"></div>'
                    eb+=f'<h2>{e(title)}</h2><p>{e(r.get("Оригинальное название"))}</p><h3>Сезон {season} · {e(episode_label)}</h3><h3>Материалы ВКонтакте</h3>'
                    eb+=(vk_link(ep.get('Альбом ВК',''),'Фотоальбом ВКонтакте')+vk_link(ep.get('Пост ВК',''),'Публикация ВКонтакте')) if available else '<p>Материалы пока не добавлены.</p>'
                    eb+='<p><a class="vk" id="orderFilm" href="https://vk.me/screencaps" target="_blank" rel="noopener noreferrer">Заказать кадры серии</a></p><nav class="episode-nav" style="clear:both">'
                    if i: eb+=f'<a href="/episodes/{e(eps[i-1]["ID серии"])}.html">← Предыдущая серия</a>'
                    if i+1<len(eps): eb+=f'<a href="/episodes/{e(eps[i+1]["ID серии"])}.html">Следующая серия →</a>'
                    eb+=f'<a href="/{e(path)}">Все сезоны</a></nav></article></section></main>'
                    (OUT/ep_path.lstrip('/')).write_text(eh+eb+footer+banner+'</body></html>',encoding='utf-8')
                    episode_count+=1
                    if available: urls.append(ep_url)
                body+='</div></details>'
            if not groups: body+='<p>Серии пока не добавлены.</p>'
        else:
            body+='<h3>Материалы ВКонтакте</h3>'+vk_link(r.get('Альбом ВК',''),'Фотоальбом ВКонтакте')+vk_link(r.get('Пост ВК',''),'Публикация ВКонтакте')
        body+='<p><a class="vk" id="orderFilm" href="https://vk.me/screencaps" target="_blank" rel="noopener noreferrer">Заказать кадры</a></p>'
        body+='<p><button type="button" onclick="navigator.clipboard.writeText(location.origin+location.pathname).then(()=>this.textContent=\'Ссылка скопирована\').catch(()=>prompt(\'Ссылка\',location.origin+location.pathname))">Скопировать ссылку на карточку</button></p></article></section></main>'
        (OUT/path).write_text(h+body+footer+banner+'</body></html>',encoding='utf-8')
        links.append((ident,path,title))
    updates=collect_updates(rows, sheets['Серии'], episode_pages)
    write_updates_page(head, footer, banner, updates)
    print(f'Generated {len(updates)} update entries')
    redirect_count = write_merged_redirects(OUT)
    print(f"Generated {redirect_count} merged redirects")
    # Keep the live catalogue and old query URLs; provide stable links for generated records.
    import json
    mapping=json.dumps({ident:'/'+path for ident,path,title in links},ensure_ascii=True)
    mapping=mapping.replace('<','\\u003c')
    old="const filmURL=f=>'?film='+encodeURIComponent(f.id);"
    new="const staticPages=new Map(Object.entries("+mapping+"));const filmURL=f=>staticPages.get(f.id)||'?film='+encodeURIComponent(f.id);"
    if old not in template: raise ValueError('Не найдена функция ссылок каталога')
    index=template.replace(old,new,1)
    update_json=json.dumps(updates[:5],ensure_ascii=True).replace('<','\\u003c')
    if 'function recent(){' not in index: raise ValueError('Не найдена лента на главной')
    index=index.replace('function recent(){','const scUpdates='+update_json+';function recent(){',1)
    ep_mapping=json.dumps(episode_pages,ensure_ascii=True).replace('<','\\u003c')
    old_ep="const episodeURL=(f,ep)=>'/?film='+encodeURIComponent(f.id)+'&episode='+encodeURIComponent(ep.id);"
    index=index.replace(old_ep,"const episodePages=new Map(Object.entries("+ep_mapping+"));const episodeURL=(f,ep)=>episodePages.get(ep.id)||'/?film='+encodeURIComponent(f.id)+'&episode='+encodeURIComponent(ep.id);",1)
    if 'openCatalogCard(e,f)' not in index: raise ValueError('Не найден обработчик навигации')
    poster_json=json.dumps(poster_map,ensure_ascii=True).replace('<','\\u003c')
    old_poster = "function poster(f){const p=el('div','🎬','poster');if(f.poster&&/^https?:\\/\\//i.test(f.poster)){const im=el('img');im.src=f.poster;im.alt=f.title;im.loading='lazy';im.onerror=()=>im.remove();p.append(im);p.firstChild.remove()}return p}"
    if old_poster not in index: raise ValueError('Не найдена функция постеров в index.html')
    new_poster = "const localPosters=new Map(Object.entries("+poster_json+"));function poster(f){const p=el('div','','poster'),im=el('img');const candidates=[...new Set([localPosters.get(f.id),f.poster,'/assets/posters/placeholder.svg'].filter(x=>x&&(/^https:\\/\\//i.test(x)||x==='/assets/posters/placeholder.svg')))];let i=0;im.alt=f.title;im.loading='lazy';im.onerror=()=>{i++;if(i<candidates.length)im.src=candidates[i];else{im.remove();p.textContent='🎬'}};p.append(im);im.src=candidates[0];return p}"
    index=index.replace(old_poster,new_poster,1)
    # A real HTML directory gives crawlers links even without JavaScript.
    directory='<section class="panel"><details><summary>Все страницы произведений</summary>'+''.join(f'<p><a href="/{e(path)}">{e(title)}</a></p>' for _,path,title in links)+'</details></section>'
    index=index.replace('</main>',directory+'</main>',1)
    legacy_redirect = """<script>(function(){const p=new URLSearchParams(location.search);if(p.get('film')!=='MS00059')return;const ep=p.get('episode');const m=/^MS00059-S01E(0[1-9]|[1-3][0-9]|4[0-3])$/.exec(ep||'');location.replace(m?'/episodes/MS00058-S02E'+m[1]+'.html':'/films/MS00058.html');})();</script>"""
    index=index.replace('</head>',legacy_redirect+'</head>',1)
    old_card="$('cards').append(c)"
    old_detail="d.append(box);window.scrollTo(0,0)"
    if index.count(old_card)!=1 or index.count(old_detail)!=1:
        raise ValueError('Не найдены точки подключения избранного и истории в index.html')
    index=index.replace(old_card,"$('cards').append(window.scLibraryCard?window.scLibraryCard(c,f.id):c)",1)
    index=index.replace(old_detail,"d.append(box);window.scLibraryDetail?.(box,f.id);window.scrollTo(0,0)",1)
    index=index.replace('</head>',LIBRARY_TAG+'</head>',1)
    write_library(head, footer, banner, rows, sheets, episode_pages, poster_for)
    (OUT/'index.html').write_text(index,encoding='utf-8')
    ns='http://www.sitemaps.org/schemas/sitemap/0.9'; ET.register_namespace('',ns)
    tree=ET.Element(f'{{{ns}}}urlset')
    for url in urls: ET.SubElement(ET.SubElement(tree,f'{{{ns}}}url'),f'{{{ns}}}loc').text=url
    ET.ElementTree(tree).write(OUT/'sitemap.xml',encoding='utf-8',xml_declaration=True)
    print(f'Generated {len(rows)} works and {episode_count} episodes, {len(urls)} sitemap URLs')

if __name__=='__main__':
    build({name:read_sheet(name) for name in SHEETS},(ROOT/'index.html').read_text(encoding='utf-8'))
