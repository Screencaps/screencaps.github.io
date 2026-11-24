        summary=' '.join(desc.split())[:300] or f'{title} — {category.lower()}, кадры и материалы ВКонтакте.'
        h=re.sub(r'<title>.*?</title>',lambda m:f'<title>{e(page_title)}</title>',head,count=1,flags=re.S)
        h=re.sub(r'<meta name="description"[^>]*>',lambda m:f'<meta name="description" content="{e(summary)}">',h,count=1)
        h=h.replace('href="favicon.svg"','href="/favicon.svg"').replace('src="vk-config.js"','src="/vk-config.js"')
        h+=f'<link rel="canonical" href="{e(url)}"><meta property="og:type" content="website"><meta property="og:title" content="{e(page_title)}"><meta property="og:description" content="{e(summary)}"><meta property="og:url" content="{e(url)}">'
        if poster: h+=f'<meta property="og:image" content="{e(poster)}">'
        h+='</head><body>'
        body='<header><div><h1><a class="brand" href="/">SCREEN<span>CAPS</span></a></h1><p>Кино в кадрах · каталог фильмов и сериалов</p><nav class="topnav"><a href="/">Каталог</a><a href="/services.html">Услуги</a><a id="groupLink" href="https://vk.ru/screencaps" target="_blank" rel="noopener noreferrer">Группа ВКонтакте</a></nav></div></header><main><section id="detail"><a href="/">← Назад к каталогу</a><article class="panel">'
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
