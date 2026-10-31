"""Шаг 6. Сборка сайта docs/index.html.

Что делает:
  1) Переводит слои базы в формат для веб-карты (GeoJSON, координаты WGS 84).
     У каждой точки – общие сведения (округ, ТС, координаты) и результаты по каждому выезду.
  2) Молоко: все пробы из листа «молоко» с проверкой по нормам (НОРМЫ_МОЛОКА ниже).
  3) Берёт шаблон  шаблон/index_шаблон.html  и вставляет в него все данные:
     точки, округа, оценки (build/оценка.json), фото (build/фото.json), подписи соседей,
     данные о районе и металлы (build/район.json, шаг 5).
  4) Пишет docs/index.html – это и есть сайт. GitHub Pages публикует папку docs.

Внешний вид сайта (цвета, тексты кнопок, раскладка) правится в шаблоне, а не здесь.
"""
import json, re
import numpy as np
import pandas as pd
import geopandas as gpd
from общее import *

ВЫЕЗДЫ = выезды()
ИДЫ = [v['id'] for v in ВЫЕЗДЫ]
p = gpd.read_file(БАЗА, layer='почва_трава'); w = gpd.read_file(БАЗА, layer='вода')
d = gpd.read_file(БАЗА, layer='граница_района'); o = gpd.read_file(БАЗА, layer='сельские_округа')
D = d.geometry.iloc[0]
оценка = json.load(open(BUILD / 'оценка.json'))


def чисто(v):
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    return v


def geojson(g, упростить=None, поля=None):
    g = g.copy()
    if упростить:
        g['geometry'] = g.geometry.simplify(упростить, preserve_topology=True)
    js = json.loads(g.to_crs(4326).to_json(drop_id=True))
    def rnd(c):
        return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 5), round(c[1], 5)]
    for f in js['features']:
        f['geometry']['coordinates'] = rnd(f['geometry']['coordinates'])
        f['properties'] = {k: чисто(v) for k, v in f['properties'].items() if поля is None or k in поля}
    return js


def по_точкам(g, общие, вода=False):
    """Одна точка на карте, результаты – по выездам: properties.t[выезд] = {...}."""
    js = geojson(g)
    out = {}
    for f in js['features']:
        pr = f['properties']; к = pr['ключ']
        if к not in out:
            out[к] = dict(type='Feature', geometry=f['geometry'],
                          properties={**{x: pr.get(x) for x in общие}, 't': {}})
        t = {x: v for x, v in pr.items() if x not in общие and x != 'выезд'}
        if вода:
            о = оценка['trips'][pr['выезд']]['water'][к]
            t['оценка_воды'] = о['grade']; t['оценка_расчётная'] = о['calc']
        out[к]['properties']['t'][pr['выезд']] = t
    return dict(type='FeatureCollection', features=list(out.values()))


ОБЩИЕ = ['округ', 'нп', 'тс', 'тс_код', 'ключ', 'долгота', 'широта', 'коорд_источник']
данные = dict(trips=ВЫЕЗДЫ, district=geojson(d, 40), okr=geojson(o, 40),
              soil=по_точкам(p, ОБЩИЕ), water=по_точкам(w, ОБЩИЕ + ['источник', 'примечание'], вода=True))

# ---------- молоко ----------
# Нормы – ТР ТС 033/2013 и СТ РК 1760-2019 (это не данные, поэтому заданы здесь).
# (поле, подпись, текст нормы, проверка: True – в норме)
НОРМЫ_МОЛОКА = [
    ('белок_%', 'Белок, %', 'не менее 2,8', lambda v: v >= 2.8),
    ('жир_%', 'Жир, %', 'не менее 2,8', lambda v: v >= 2.8),
    ('СОМО_%', 'СОМО, %', 'не менее 8,2', lambda v: v >= 8.2),
    ('сухое_вещество_%', 'Сухое вещество, %', '–', None),
    ('лактоза_%', 'Лактоза, %', '–', None),
    ('точка_замерзания_C', 'Точка замерзания, °C', 'не выше −0,505', lambda v: v <= -0.505),
    ('мочевина_%', 'Мочевина, %', '–', None),
    ('кислотность_T', 'Кислотность, °Т', '16–21', lambda v: 16 <= v <= 21),
    ('сомат_клетки_тыс_мл', 'Соматические клетки, тыс./мл', 'не более 750', lambda v: v <= 750),
]
M = pd.read_excel(ДАННЫЕ, sheet_name='молоко').dropna(subset=['Выезд'])
пробы = []
for _, r in M.iterrows():
    знач = []
    for поле, подпись, норма, ок in НОРМЫ_МОЛОКА:
        v = r.get(МОЛОКО[поле])
        if pd.isna(v):
            continue
        v = float(v)
        txt = f'{v:.3f}' if поле == 'точка_замерзания_C' else (str(int(v)) if v == int(v) and поле == 'сомат_клетки_тыс_мл' else str(round(v, 4)))
        знач.append(dict(k=поле, label=подпись, v=v, txt=txt.replace('.', ',').replace('-', '−'),
                         norm=норма, ok=None if ок is None else bool(ок(v))))
    la, lo = r.get('Широта'), r.get('Долгота')
    пробы.append(dict(trip=str(r['Выезд']).strip(), n=str(r['Проба']).replace('.0', ''),
                      date=None if pd.isna(r.get('Дата отбора')) else str(r['Дата отбора']),
                      okr=None if pd.isna(r.get('Сельский округ')) else округ(str(r['Сельский округ'])),
                      place=None if pd.isna(r.get('Место отбора')) else str(r['Место отбора']),
                      lat=None if pd.isna(la) else float(la), lon=None if pd.isna(lo) else float(lo),
                      coord_src=None if pd.isna(r.get('Откуда координаты')) else str(r['Откуда координаты']),
                      note=None if pd.isna(r.get('Примечание')) else str(r['Примечание']), vals=знач))
# пробы из одного села – немного разносим по долготе, чтобы обе были видны на карте
for (trip, la, lo), grp in pd.DataFrame(пробы).dropna(subset=['lat']).groupby(['trip', 'lat', 'lon']):
    for j, i in enumerate(grp.index):
        пробы[i]['shift'] = round((j - (len(grp) - 1) / 2) * 0.012, 4)
данные['milk'] = пробы

# ---------- оценки, фото, соседи ----------
данные['interp'] = оценка
данные['photos'] = json.load(open(BUILD / 'фото.json'))
данные['ctx'] = json.load(open(BUILD / 'соседи.json'))
данные['raion'] = json.load(open(BUILD / 'район.json'))   # шаг 5: район в целом, металлы, документы

# ---------- сборка страницы ----------
css = re.sub(r'url\([^)]*\)', 'none', open(ШАБЛОН / 'leaflet.css').read())
html = open(ШАБЛОН / 'index_шаблон.html').read()
html = html.replace('/*LEAFLET_CSS*/', css).replace(
    '/*ДАННЫЕ*/', 'window.GIS=' + json.dumps(данные, ensure_ascii=False, separators=(',', ':'), default=чисто) + ';')
САЙТ.mkdir(exist_ok=True)
# Для GitHub Pages нужен полноценный HTML-документ
if not html.lstrip().lower().startswith('<!doctype'):
    html = ('<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '</head>\n<body>\n' + html + '\n</body>\n</html>\n')
(САЙТ / 'index.html').write_text(html, encoding='utf-8')
(САЙТ / '.nojekyll').write_text('')   # GitHub Pages: отдавать файлы как есть
print(f'Шаг 6 готов: docs/index.html ({len(html) // 1024} КБ), выездов {len(ИДЫ)}, проб молока {len(пробы)}')
