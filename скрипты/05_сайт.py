"""Шаг 5. Сборка сайта docs/index.html.

Что делает:
  1) Переводит слои базы в формат для веб-карты (GeoJSON, координаты WGS 84).
  2) Считает интерполяцию IDW по 7 показателям почвы и пастбищ: сетка ~420 px по ширине
     района, вес = 1/расстояние², значения обрезаются по контуру района.
     Каждая поверхность сохраняется картинкой PNG внутри страницы.
  3) Берёт шаблон  шаблон/index_шаблон.html  и вставляет в него все данные:
     точки, округа, оценки (build/оценка.json), фото (build/фото.json), подписи соседей.
  4) Пишет docs/index.html — это и есть сайт. GitHub Pages публикует папку docs.

Внешний вид сайта (цвета, тексты кнопок, раскладка) правится в шаблоне, а не здесь.
"""
import base64, io, json
import numpy as np
import geopandas as gpd
import shapely
from PIL import Image
from pyproj import Transformer
from общее import *

p = gpd.read_file(БАЗА, layer='почва_трава'); w = gpd.read_file(БАЗА, layer='вода')
d = gpd.read_file(БАЗА, layer='граница_района'); o = gpd.read_file(БАЗА, layer='сельские_округа')
D = d.geometry.iloc[0]

def geojson(g, упростить=None, поля=None):
    g = g.copy()
    if упростить:
        g['geometry'] = g.geometry.simplify(упростить, preserve_topology=True)
    js = json.loads(g.to_crs(4326).to_json(drop_id=True))
    def rnd(c):
        return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 5), round(c[1], 5)]
    for f in js['features']:
        f['geometry']['coordinates'] = rnd(f['geometry']['coordinates'])
        f['properties'] = {k: (None if isinstance(v, float) and np.isnan(v) else v)
                           for k, v in f['properties'].items() if поля is None or k in поля}
    return js

ГРУППЫ = {'Карасуский': 'Устойчивое / благоприятное', 'Тельжанский': 'Устойчивое / благоприятное',
          'Коктерекский': 'Устойчивое / благоприятное', 'Каратерекский': 'Устойчивое / благоприятное',
          'Бидайыкский': 'В целом устойчивое, неоднородное', 'Актуесайский': 'В целом устойчивое, неоднородное',
          'Амангельдинский': 'В целом устойчивое, неоднородное', 'Кишкенекольский': 'Повышенная пастбищная нагрузка',
          'Акбулакский': 'Требует восстановительных мероприятий', 'Кайратский': 'Требует восстановительных мероприятий',
          'Кулыкольский': 'Наиболее приоритетный для восстановления'}
o['состояние_пастбищ'] = o.округ.map(ГРУППЫ)
данные = dict(district=geojson(d, 40), okr=geojson(o, 40), soil=geojson(p), water=geojson(w))

# ---------- IDW ----------
ПОКАЗАТЕЛИ = {
    'орг_вещество_%': ('Органическое вещество, %', ['#f3ead2', '#d9b77e', '#a8743e', '#6b4423', '#3b2413']),
    'pH_почвы': ('pH почвы', ['#d9582b', '#f2b35e', '#f4eed7', '#86b7d6', '#3d5fa8']),
    'N_легкогидр_мг100г': ('N лёгкогидролизуемый, мг/100 г', ['#f1eef6', '#bdc9e1', '#74a9cf', '#2b8cbe', '#045a8d']),
    'P_подв_мг100г': ('P подвижный, мг/100 г', ['#fef0d9', '#fdcc8a', '#fc8d59', '#e34a33', '#b30000']),
    'K_подв_мг100г': ('K подвижный, мг/100 г', ['#f2f0f7', '#cbc9e2', '#9e9ac8', '#756bb1', '#54278f']),
    'урож_сух_цга': ('Урожайность сухой массы, ц/га', ['#f7fcb9', '#d9f0a3', '#addd8e', '#41ab5d', '#005a32']),
    'покрытие_%': ('Проективное покрытие, %', ['#ffffcc', '#c2e699', '#78c679', '#31a354', '#006837'])}
в_utm = Transformer.from_crs(3857, CRS, always_xy=True)
d3 = d.to_crs(3857).geometry.iloc[0]
minx, miny, maxx, maxy = d3.bounds; pad = 3000
minx -= pad; miny -= pad; maxx += pad; maxy += pad
Wpx = 420; Hpx = int(Wpx * (maxy - miny) / (maxx - minx))
xs = minx + (np.arange(Wpx) + .5) * (maxx - minx) / Wpx
ys = maxy - (np.arange(Hpx) + .5) * (maxy - miny) / Hpx
X, Y = np.meshgrid(xs, ys)
маска = shapely.contains_xy(d3, X, Y)
UX, UY = в_utm.transform(X, Y)
px, py = p.geometry.x.values, p.geometry.y.values
вес = 1 / np.maximum(np.sqrt((UX[..., None] - px) ** 2 + (UY[..., None] - py) ** 2), 50) ** 2
hex2rgb = lambda h: np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)])
слои = {}
for k, (подпись, шкала) in ПОКАЗАТЕЛИ.items():
    v = p[k].values.astype(float); ok = ~np.isnan(v)
    Z = (вес[..., ok] * v[ok]).sum(-1) / вес[..., ok].sum(-1)
    lo, hi = np.nanpercentile(v, 2), np.nanpercentile(v, 98)
    s = np.clip((Z - lo) / (hi - lo), 0, 1) * (len(шкала) - 1)
    cols = np.array([hex2rgb(c) for c in шкала])
    i0 = np.floor(s).astype(int).clip(0, len(cols) - 2); f = (s - i0)[..., None]
    img = np.zeros((Hpx, Wpx, 4), np.uint8)
    img[..., :3] = (cols[i0] * (1 - f) + cols[i0 + 1] * f).astype(np.uint8)
    img[..., 3] = np.where(маска, 255, 0)
    b = io.BytesIO(); Image.fromarray(img, 'RGBA').save(b, 'PNG', optimize=True)
    слои[k] = dict(label=подпись, ramp=шкала, min=round(float(lo), 2), max=round(float(hi), 2),
                   png='data:image/png;base64,' + base64.b64encode(b.getvalue()).decode())
в_4326 = Transformer.from_crs(3857, 4326, always_xy=True)
lo1, la1 = в_4326.transform(minx, miny); lo2, la2 = в_4326.transform(maxx, maxy)
данные['idw'] = dict(bounds=[[la1, lo1], [la2, lo2]], layers=слои)

# ---------- молоко, оценки, фото, соседи ----------
данные['milk'] = [['Белок, %', '2,81', 'не менее 2,8'], ['Жир, %', '5,34', 'не менее 2,8'],
                  ['СОМО, %', '8,11', 'не менее 8,2'], ['Сухое вещество, %', '13,48', '–'],
                  ['Лактоза, %', '4,59', '–'], ['Точка замерзания, °C', '−0,504', 'не выше −0,505'],
                  ['Мочевина, %', '0,02', '–'], ['Кислотность, °Т', '17,5', '16–21']]
данные['interp'] = json.load(open(BUILD / 'оценка.json'))
данные['photos'] = json.load(open(BUILD / 'фото.json'))
данные['ctx'] = json.load(open(BUILD / 'соседи.json'))

# ---------- сборка страницы ----------
import re
css = re.sub(r'url\([^)]*\)', 'none', open(ШАБЛОН / 'leaflet.css').read())
html = open(ШАБЛОН / 'index_шаблон.html').read()
html = html.replace('/*LEAFLET_CSS*/', css).replace(
    '/*ДАННЫЕ*/', 'window.GIS=' + json.dumps(данные, ensure_ascii=False, separators=(',', ':')) + ';')
САЙТ.mkdir(exist_ok=True)
# Для GitHub Pages нужен полноценный HTML-документ
if not html.lstrip().lower().startswith('<!doctype'):
    html = ('<!doctype html>\n<html lang="ru">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '</head>\n<body>\n' + html + '\n</body>\n</html>\n')
(САЙТ / 'index.html').write_text(html, encoding='utf-8')
(САЙТ / '.nojekyll').write_text('')   # GitHub Pages: отдавать файлы как есть
print(f'Шаг 5 готов: docs/index.html ({len(html) // 1024} КБ)')
