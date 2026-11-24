import csv
import io
import re
import shutil
import urllib.request
from pathlib import Path
from html import escape
from urllib.parse import urlencode, urlsplit
import xml.etree.ElementTree as ET

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
    required = {'Жанр'} if name == 'Жанры' else ({'ID произведения','Номер серии','Статус'} if name == 'Серии' else {'ID','Русское название','Статус'})
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
def vk_link(s,label):
    return f'<a class="vk" href="{e(s)}" target="_blank" rel="noopener noreferrer">{e(label)}</a>' if safe_url(s,True) else ''
def filter_link(key,value,label): return f'<a class="chip" href="/?{e(urlencode({key:value}))}">{e(label)}</a>'
def number_key(s): return (0,int(s)) if s.isdigit() else (1,s)

def build(sheets, template):
    head=template.split('</head>',1)[0]
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
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir(); (OUT/'films').mkdir()
    for p in ROOT.iterdir():
        if p.is_file() and p.suffix in {'.html','.js','.css','.svg','.png','.jpg','.jpeg','.webp','.ico','.txt','.xml'} and p.name not in {'index (1).html','sitemap.xml'}:
            shutil.copy2(p,OUT/p.name)
    (OUT/'.nojekyll').touch()
    urls=[SITE,SITE+'services.html',SITE+'about.html',SITE+'privacy.html']
    links=[]
    for category,r in rows:
        ident=r['ID']; title=r['Русское название']; year=r.get('Год выпуска',''); desc=r.get('Описание',''); poster=safe_url(r.get('Постер','')); path=f'films/{ident}.html'; url=SITE+path; urls.append(url)
        page_title=title+(f' ({year})' if year else '')+' — SCREENCAPS'
        summary=' '.join(desc.split())[:300] or f'{title} — {category.lower()}, кадры и материалы ВКонтакте.'
        h=re.sub(r'<title>.*?</title>',lambda m:f'<title>{e(page_title)}</title>',head,count=1,flags=re.S)
        h=re.sub(r'<meta name="description"[^>]*>',lambda m:f'<meta name="description" content="{e(summary)}">',h,count=1)
        h=h.replace('href="favicon.svg"','href="/favicon.svg"').replace('src="vk-config.js"','src="/vk-config.js"')
        h+=f'<link rel="canonical" href="{e(url)}"><meta property="og:type" content="website"><meta property="og:title" content="{e(page_title)}"><meta property="og:description" content="{e(summary)}"><meta property="og:url" content="{e(url)}">'
        if poster: h+=f'<meta property="og:image" content="{e(poster)}">'
        h+='</head><body>'
        body='<header><div><h1><a class="brand" href="/">SCREEN<span>CAPS</span></a></h1><p>Кино в кадрах · каталог фильмов и сериалов</p><nav class="topnav"><a href="/">Каталог</a><a href="/services.html">Услуги</a><a href="/about.html">О проекте</a><a id="groupLink" href="https://vk.ru/screencaps" target="_blank" rel="noopener noreferrer">Группа ВКонтакте</a></nav></div></header><main><section id="detail"><a href="/">← Назад к каталогу</a><article class="panel">'
        if poster: body+=f'<div class="poster"><img src="{e(poster)}" alt="{e(title)}"></div>'
        body+=f'<h2>{e(title)}</h2><p>{e(r.get("Оригинальное название"))}</p><div class="detailmeta">'
        if year: body+=filter_link('year',year,year+('–'+r['Год окончания'] if r.get('Год окончания') else ''))
        body+=filter_link('category',category,category)
        for genre in re.split('[,;]',r.get('Жанры','')):
            if genre.strip(): body+=filter_link('genre',genre.strip(),genre.strip())
        body+='</div><p>'+e(' · '.join(r[k] for k in ['Страна','Режиссёр','Продолжительность'] if r.get(k)))+'</p>'
        if r.get('Количество сезонов') or r.get('Количество серий'):
            body+='<p>'+e(' · '.join(label+r[k] for k,label in [('Количество сезонов','Сезонов: '),('Количество серий','Серий: ')] if r.get(k)))+'</p>'
        body+=f'<h3>Описание</h3><p>{e(desc or "Описание пока не добавлено")}</p><h3>Материалы ВКонтакте</h3>'
        body+=vk_link(r.get('Альбом ВК',''),'Фотоальбом ВКонтакте')+vk_link(r.get('Пост ВК',''),'Публикация ВКонтакте')
        if category in {'Сериалы','Дорамы','Мультсериалы'}:
            body+='<h3>Сезоны и серии</h3>'; groups={}
            for ep in sheets['Серии']:
                if published(ep) and ep.get('ID произведения')==ident and ep.get('Номер серии'): groups.setdefault(ep.get('Сезон') or '1',[]).append(ep)
            for season,eps in sorted(groups.items(),key=lambda x:number_key(x[0])):
                body+=f'<details><summary>Сезон {e(season)}</summary>'
                for ep in sorted(eps,key=lambda x:number_key(x['Номер серии'])):
                    body+=f'<p>Серия {e(ep["Номер серии"])} — {e(ep.get("Название серии"))}</p><p>{e(ep.get("Описание"))}</p><small>{e(ep.get("Дата выхода"))}</small>'+vk_link(ep.get('Альбом ВК',''),'Фотоальбом')+vk_link(ep.get('Пост ВК',''),'Публикация')
                body+='</details>'
            if not groups: body+='<p>Серии пока не добавлены.</p>'
        body+='<p><a class="vk" id="orderFilm" href="https://vk.me/screencaps" target="_blank" rel="noopener noreferrer">Заказать кадры</a></p>'
        body+='<p><button type="button" onclick="navigator.clipboard.writeText(location.href).then(()=>this.textContent=\'Ссылка скопирована\').catch(()=>prompt(\'Ссылка\',location.href))">Скопировать ссылку на карточку</button></p></article></section></main>'
        (OUT/path).write_text(h+body+footer+banner+'</body></html>',encoding='utf-8')
        links.append((ident,path,title))
    # Keep the live catalogue and old query URLs; provide stable links for generated records.
    import json
    mapping=json.dumps({ident:'/'+path for ident,path,title in links},ensure_ascii=True)
    mapping=mapping.replace('<','\\u003c')
    old="const filmURL=f=>'?film='+encodeURIComponent(f.id);"
    new="const staticPages=new Map(Object.entries("+mapping+"));const filmURL=f=>staticPages.get(f.id)||'?film='+encodeURIComponent(f.id);"
    if old not in template: raise ValueError('Не найдена функция ссылок каталога')
    index=template.replace(old,new,1)
    old_click="if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();history.pushState(null,'',filmURL(f));route()"
    if old_click not in index: raise ValueError('Не найден обработчик карточек')
    index=index.replace(old_click,"if(staticPages.has(f.id)||e.ctrlKey||e.metaKey||e.shiftKey||e.altKey)return;e.preventDefault();history.pushState(null,'',filmURL(f));route()",1)
    marker='recent();render();route();'
    if marker not in index: raise ValueError('Не найдено завершение загрузки каталога')
    index=index.replace(marker,"const filters=new URLSearchParams(location.search);if(cats.includes(filters.get('category')))category=filters.get('category');if(filters.has('year'))$('from').value=$('to').value=filters.get('year');if(filters.has('genre'))for(const o of $('genres').options)o.selected=o.value.toLowerCase()===filters.get('genre').toLowerCase();"+marker,1)
    # A real HTML directory gives crawlers links even without JavaScript.
    directory='<section class="panel"><details><summary>Все страницы произведений</summary>'+''.join(f'<p><a href="/{e(path)}">{e(title)}</a></p>' for _,path,title in links)+'</details></section>'
    index=index.replace('</main>',directory+'</main>',1)
    (OUT/'index.html').write_text(index,encoding='utf-8')
    ns='http://www.sitemaps.org/schemas/sitemap/0.9'; ET.register_namespace('',ns)
    tree=ET.Element(f'{{{ns}}}urlset')
    for url in urls: ET.SubElement(ET.SubElement(tree,f'{{{ns}}}url'),f'{{{ns}}}loc').text=url
    ET.ElementTree(tree).write(OUT/'sitemap.xml',encoding='utf-8',xml_declaration=True)
    print(f'Generated {len(rows)} pages, {len(urls)} sitemap URLs')

if __name__=='__main__':
    build({name:read_sheet(name) for name in SHEETS},(ROOT/'index.html').read_text(encoding='utf-8'))
