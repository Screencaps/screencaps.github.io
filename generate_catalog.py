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
        body='<header><div><h1><a class="brand" href="/">SCREEN<span>CAPS</span></a></h1><p>Кино в кадрах · каталог фильмов и сериалов</p><nav class="topnav"><a href="/">Каталог</a><a href="/services.html">Услуги</a><a href="/about.html">О проекте</a><a id="groupLink" href="https://vk.ru/screencaps" target="_blank" rel="noopener noreferrer">Группа ВКонтакте</a></nav></div></header><main><section id="detail"><a href="/" data-sc-back>← Назад к каталогу</a><article class="panel">'
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
    (OUT/'index.html').write_text(index,encoding='utf-8')
    ns='http://www.sitemaps.org/schemas/sitemap/0.9'; ET.register_namespace('',ns)
    tree=ET.Element(f'{{{ns}}}urlset')
    for url in urls: ET.SubElement(ET.SubElement(tree,f'{{{ns}}}url'),f'{{{ns}}}loc').text=url
    ET.ElementTree(tree).write(OUT/'sitemap.xml',encoding='utf-8',xml_declaration=True)
    print(f'Generated {len(rows)} works and {episode_count} episodes, {len(urls)} sitemap URLs')

if __name__=='__main__':
    build({name:read_sheet(name) for name in SHEETS},(ROOT/'index.html').read_text(encoding='utf-8'))
