"""Шаг 2. Границы района и сельских округов из OpenStreetMap.

Что делает:
  1) Из osm_границы.gpkg (скачан в QGIS плагином QuickOSM) берёт контур Уалихановского
     района и 11 сельских округов внутри него.
  2) Убирает анклав Кайратского округа (~51 км² к востоку от района): в нём нет точек,
     и на карте он выглядел как ошибка. Чтобы вернуть его – поставьте УБРАТЬ_АНКЛАВ = False.
  3) Переводит казахские названия округов в официальные русские.
  4) Считает средние значения по каждому округу и выезду (таблица «средние_по_округам»).
  5) Добавляет слои «граница_района» и «сельские_округа» в базу и сохраняет
     готовое оформление для QGIS (цвета точек, пунктир округов, подписи).
  6) Готовит подписи соседних территорий по сторонам района (build/соседи.json).
"""
import json, math, sqlite3
import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon
from общее import *

УБРАТЬ_АНКЛАВ = True
osm = gpd.read_file(OSM).to_crs(CRS)
район = osm[osm.full_id == OSM_РАЙОН].geometry.iloc[0]
D_полный = район

def без_анклавов(g, мин_км2=100):
    if g.geom_type == 'MultiPolygon':
        части = [p for p in g.geoms if p.area / 1e6 > мин_км2]
        return MultiPolygon(части)
    return MultiPolygon([g])

if УБРАТЬ_АНКЛАВ:
    район = без_анклавов(район)

# ---------- сельские округа ----------
KZ = {'Қарасу': 'Карасуский', 'Ақбұлақ': 'Акбулакский', 'Кішкенекөл': 'Кишкенекольский',
      'Телжан': 'Тельжанский', 'Ақтүесай': 'Актуесайский', 'Бидайық': 'Бидайыкский',
      'Қаратерек': 'Каратерекский', 'Амангелді': 'Амангельдинский', 'Көктерек': 'Коктерекский',
      'Қайрат': 'Кайратский', 'Құлыкөл': 'Кулыкольский'}
o = osm[osm.admin_level == '8'].copy()
o = o[o.geometry.representative_point().within(D_полный)]
o['округ'] = o.name.str.replace(' ауылдық округі', '').map(KZ)
assert o.округ.notna().all() and len(o) == 11, 'ожидалось 11 сельских округов'
if УБРАТЬ_АНКЛАВ:
    o['geometry'] = o.geometry.apply(без_анклавов)
o['название_kk'] = o.name
o['osm_id'] = o.full_id
o['площадь_км2'] = (o.area / 1e6).round(0)

# проверка: каждая точка (и проба молока) лежит в своём округе
p = gpd.read_file(БАЗА, layer='почва_трава')
w = gpd.read_file(БАЗА, layer='вода')
m = gpd.read_file(БАЗА, layer='молоко')
for L in (p.drop_duplicates('ключ'), w.drop_duplicates('ключ'), m[m.округ.notna()]):
    j = gpd.sjoin(L, o[['округ', 'geometry']].rename(columns={'округ': 'окр_osm'}), predicate='within')
    плохие = j[j.округ != j.окр_osm]
    имя = 'ключ' if 'ключ' in L else 'проба'
    assert len(j) == len(L) and плохие.empty, f'точки вне своих округов: {list(плохие[имя])}'

# средние по округам для каждого выезда – отдельная таблица (без геометрии) для QGIS
ap = p.groupby(['округ', 'выезд']).agg(ср_орг_вещество_pct=('орг_вещество_%', 'mean'),
                                       ср_pH_почвы=('pH_почвы', 'mean'), ср_N=('N_легкогидр_мг100г', 'mean'),
                                       ср_P=('P_подв_мг100г', 'mean'), ср_K=('K_подв_мг100г', 'mean'),
                                       ср_урож_сух_цга=('урож_сух_цга', 'mean'),
                                       ср_покрытие_pct=('покрытие_%', 'mean'),
                                       ср_высота_см=('высота_ср_см', 'mean'),
                                       ср_протеин_pct=('протеин_%', 'mean')).round(2)
aw = w.groupby(['округ', 'выезд']).agg(ср_TDS_мг_л=('TDS_мг_л', 'mean'), ср_pH_воды=('pH_воды', 'mean'),
                                       проб_с_E_coli=('E_coli', lambda s: int((s > 0).sum())),
                                       проб_TDS_выше_1000=('TDS_мг_л', lambda s: int((s > 1000).sum()))).round(1)
средние = ap.join(aw, how='outer').reset_index()
o = o[['округ', 'название_kk', 'площадь_км2', 'osm_id', 'geometry']]
o.insert(0, 'сельский_округ', o.округ + ' сельский округ')
o = gpd.GeoDataFrame(o, geometry='geometry', crs=CRS).sort_values('округ')

d = gpd.GeoDataFrame({'название': ['Уалихановский район'], 'название_kk': ['Уәлиханов ауданы'],
                      'источник': [f'OpenStreetMap, relation {OSM_РАЙОН[1:]}']},
                     geometry=[район], crs=CRS)
d['площадь_км2'] = (d.area / 1e6).round(0)
d.to_file(БАЗА, layer='граница_района', driver='GPKG')
o.to_file(БАЗА, layer='сельские_округа', driver='GPKG')
import pyogrio
pyogrio.write_dataframe(средние, БАЗА, layer='средние_по_округам', driver='GPKG')

# ---------- оформление слоёв для QGIS (открывается автоматически) ----------
def точки(цвет):
    return f'''<qgis version="3.40" styleCategories="Symbology"><renderer-v2 type="singleSymbol"><symbols>
<symbol type="marker" name="0" alpha="1"><layer class="SimpleMarker"><Option type="Map">
<Option name="color" type="QString" value="{цвет}"/><Option name="name" type="QString" value="circle"/>
<Option name="outline_color" type="QString" value="255,255,255,255"/><Option name="outline_width" type="QString" value="0.4"/>
<Option name="size" type="QString" value="3"/></Option></layer></symbol></symbols></renderer-v2></qgis>'''
def контур(цвет, ширина, пунктир):
    return f'''<qgis version="3.40" styleCategories="Symbology|Labeling"><renderer-v2 type="singleSymbol"><symbols>
<symbol type="fill" name="0" alpha="1"><layer class="SimpleFill"><Option type="Map">
<Option name="style" type="QString" value="no"/><Option name="outline_color" type="QString" value="{цвет}"/>
<Option name="outline_style" type="QString" value="{'dash' if пунктир else 'solid'}"/>
<Option name="outline_width" type="QString" value="{ширина}"/></Option></layer></symbol></symbols></renderer-v2>
{'<labeling type="simple"><settings><text-style fieldName="округ" fontSize="9" fontItalic="1" textColor="80,80,80,255"><text-buffer bufferDraw="1" bufferSize="0.8" bufferColor="255,255,255,200"/></text-style><placement placement="1"/></settings></labeling>' if пунктир else ''}</qgis>'''
стили = {'почва_трава': точки('51,160,44,255'), 'вода': точки('31,120,200,255'),
         'молоко': точки('214,150,40,255'),
         'граница_района': контур('60,60,60,255', 0.7, False),
         'сельские_округа': контур('120,120,120,255', 0.35, True)}
con = sqlite3.connect(БАЗА)
con.execute('DROP TABLE IF EXISTS layer_styles')
con.execute('''CREATE TABLE layer_styles (id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT,
  f_table_schema TEXT, f_table_name TEXT, f_geometry_column TEXT, styleName TEXT, styleQML TEXT,
  styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT, ui TEXT,
  update_time DATETIME DEFAULT CURRENT_TIMESTAMP)''')
for t, q in стили.items():
    con.execute('INSERT INTO layer_styles (f_table_catalog,f_table_schema,f_table_name,f_geometry_column,'
                'styleName,styleQML,styleSLD,useAsDefault,description,owner) VALUES (?,?,?,?,?,?,?,?,?,?)',
                ('', '', t, 'geom', 'по умолчанию', q, '', 1, '', ''))
con.execute("INSERT OR IGNORE INTO gpkg_contents (table_name,data_type,identifier,last_change) "
            "VALUES ('layer_styles','attributes','layer_styles',strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
con.commit(); con.close()

# ---------- подписи соседних территорий ----------
def регион(fid): return osm[osm.full_id == fid].geometry.iloc[0]
c = район.centroid
в4326 = lambda g: gpd.GeoSeries([g], crs=CRS).to_crs(4326)[0]
соседи = [('РОССИЙСКАЯ ФЕДЕРАЦИЯ', регион('r60189'), 90),
          ('ПАВЛОДАРСКАЯ ОБЛАСТЬ', регион('r215772'), -30),
          ('АКМОЛИНСКАЯ ОБЛАСТЬ', регион('r215743'), -110),
          ('СЕВЕРО-КАЗАХСТАНСКАЯ ОБЛАСТЬ', регион('r215760').difference(D_полный), 175)]
подписи = []
for имя, g, угол in соседи:
    z = g.intersection(район.buffer(42000)).difference(район.buffer(22000))
    части = list(z.geoms) if z.geom_type.startswith('Multi') else [z]
    def оценка(q):
        t = q.representative_point()
        a = math.degrees(math.atan2(t.y - c.y, t.x - c.x))
        return abs((a - угол + 180) % 360 - 180) - q.area / 1e9
    т = в4326(min(части, key=оценка).representative_point())
    подписи.append(dict(name=имя, lat=round(т.y, 4), lon=round(т.x, 4)))
BUILD.mkdir(exist_ok=True)
json.dump(dict(labels=подписи), open(BUILD / 'соседи.json', 'w'), ensure_ascii=False)
print(f'Шаг 2 готов: район {d.площадь_км2.iloc[0]:.0f} км², округов {len(o)}; '
      f'все точки и пробы молока ({len(m)}) в своих округах')
