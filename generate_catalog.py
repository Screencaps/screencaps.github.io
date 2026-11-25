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
    required = {'Жанр'} if name == 'Жанры' else ({'ID серии','ID произведения','Сезон','Номер серии','Статус','Альбом ВК','Пост ВК'} if name == 'Серии' else {'ID','Русское название','Статус'})
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
    local_posters = prepare_posters(rows, ROOT)
    if OUT.exists(): shutil.rmtree(OUT)
    OUT.mkdir(); (OUT/'films').mkdir(); (OUT/'episodes').mkdir()
    for p in ROOT.iterdir():
        if p.is_file() and p.suffix in {'.html','.js','.css','.svg','.png','.jpg','.jpeg','.webp','.ico','.txt','.xml'} and p.name not in {'index (1).html','sitemap.xml'}:
            shutil.copy2(p,OUT/p.name)
    if (ROOT/'assets').is_dir():
        shutil.copytree(ROOT/'assets', OUT/'assets', dirs_exist_ok=True)
    poster_dir = OUT / 'assets' / 'posters'
    poster_dir.mkdir(parents=True, exist_ok=True)
    placeholder = poster_dir / 'placeholder.svg'
    placeholder.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 600"><rect width="400" height="600" fill="#171c26"/><rect x="110" y="190" width="180" height="130" rx="12" fill="none" stroke="#b9a06a" stroke-width="5"/><path d="M110 225h180M150 190l25 35m35-35 25 35" stroke="#b9a06a" stroke-width="5"/><text x="200" y="375" text-anchor="middle" fill="#e8e3da" font-family="sans-serif" font-size="25">SCREENCAPS</text><text x="200" y="410" text-anchor="middle" fill="#b5b5b5" font-family="sans-serif" font-size="16">Постер недоступен</text></svg>', encoding='utf-8')
    poster_map = {}
    for _, r in rows:
        source = local_posters.get(r['ID'])
        if source:
            shutil.copy2(source, poster_dir / source.name)
        poster_map[r['ID']] = SITE + 'assets/posters/' + (source.name if source else placeholder.name)
    def poster_for(r):
        return poster_map[r['ID']]
    (OUT/'.nojekyll').touch()
    urls=[SITE,SITE+'services.html',SITE+'about.html',SITE+'privacy.html']
    collection = OUT/'hunger-games.html'
    if collection.is_file():
        page = collection.read_text(encoding='utf-8')
        for year in ('2012','2013','2014','2015','2023','2026'):
            matches = [r for category,r in rows if category == 'Фильмы' and r.get('Год выпуска','') == year and (r.get('Русское название','').casefold().startswith('голодные игры') or r.get('Оригинальное название','').casefold().startswith('the hunger games'))]
            if len(matches) != 1:
                continue
            r = matches[0]
            poster = poster_for(r)
if __name__=='__main__':
    build({name:read_sheet(name) for name in SHEETS},(ROOT/'index.html').read_text(encoding='utf-8'))
