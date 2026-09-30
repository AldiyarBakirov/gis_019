"""Шаг 1. Точки отбора + результаты анализов → слои «почва_трава» и «вода».

Что делает:
  1) Читает KML полевой группы: 79 точек с подписями вида «Аккудык, трава+почва, ТС#2».
     Из них берутся точки ВОДЫ (44).
  2) Координаты 44 точек ПОЧВЫ и ТРАВЫ берутся из отчёта (таблицы 2–12): там есть все
     площадки, а в KML части не хватает.
  3) Подтягивает анализы:
       - протокол № 212 (акт): гумус, N, P, K, pH;
       - отчёт, табл. 1: влажность и плотность почвы по горизонтам;
       - отчёт, табл. 13–14: травостой, покрытие, деградация, урожайность, доминанты;
       - отчёт, табл. 18: вода (EC, TDS, E. coli, колиформы, pH, мутность, оценка).
  4) Сохраняет всё в база/База_019.gpkg.

Ключ, по которому всё связывается: «округ + номер ТС», например «Карасуский_ТС1».
"""
import re
import numpy as np
import pandas as pd
import geopandas as gpd
from общее import *

T = таблицы_docx(ОТЧЁТ)

# ---------- 1. Координаты площадок почвы/травы из отчёта (табл. 2–12) ----------
def dms(s):
    g, m, sec = [float(a) for a in re.findall(r'(\d+)°(\d+)\'([\d.]+)"', s)[0]]
    return g + m / 60 + sec / 3600

порядок = ['Карасуский', 'Акбулакский', 'Кишкенекольский', 'Бидайыкский', 'Актуесайский',
           'Кулыкольский', 'Кайратский', 'Тельжанский', 'Коктерекский', 'Амангельдинский',
           'Каратерекский']
коорд = []
for окр, t in zip(порядок, T[1:12]):
    for r in t[1:]:
        lat, lon = [dms(p) for p in r[1].split(',')]
        коорд.append(dict(округ=окр, тс=int(r[0]), lat=lat, lon=lon))
C = pd.DataFrame(коорд)

# ---------- 2. Таблицы отчёта с «растянутой» первой колонкой ----------
def с_округом(t, cols):
    out, cur = [], None
    for r in t[1:]:
        if r[0]:
            cur = округ(r[0])
        out.append(dict(zip(cols, [cur, int(r[1])] + r[2:])))
    return pd.DataFrame(out)

B = с_округом(T[14], ['округ', 'тс', 'высота_min_см', 'высота_max_см', 'высота_ср_см',
                      'покрытие_%', 'деградация'])
for c in ['высота_min_см', 'высота_max_см', 'высота_ср_см', 'покрытие_%']:
    B[c] = B[c].apply(число)
B['деградация'] = B.деградация.str.replace(' -', '-').str.replace('II-III', 'II–III')

Y = с_округом(T[15], ['округ', 'тс', 'урож_зел_цга', 'урож_сух_цга', 'доминанты', 'субдоминанты'])
Y['урож_зел_примеч'] = Y.урож_зел_цга.apply(lambda s: 'менее 5,0' if 'менее' in s else None)
for c in ['урож_зел_цга', 'урож_сух_цга']:
    Y[c] = Y[c].apply(число)

# Табл. 1: плотность и влажность по горизонтам
строки, о, п = [], None, None
for r in T[0][1:]:
    if len(r) < 11:
        continue
    if r[0]: о = округ(r[0])
    if r[1]: п = int(r[1])
    строки.append(dict(округ=о, тс=п, гор=r[2], влаж=число(r[7]), плот=число(r[10])))
S = pd.DataFrame(строки).pivot_table(index=['округ', 'тс'], columns='гор',
                                     values=['влаж', 'плот'], aggfunc='first')
S.columns = [f"{'влажность_%' if a == 'влаж' else 'плотность_г_см3'}_{b.replace('-', '_')}"
             for a, b in S.columns]
S = S.reset_index()

# ---------- 3. Протокол № 212: агрохимия ----------
A = таблицы_docx(АКТ)[0]
K = []
for r in A[2:]:
    m = re.match(r'(.+?)\s+(\d)$', r[0])
    K.append({'округ': округ(m.group(1)), 'тс': int(m.group(2)), 'орг_вещество_%': число(r[1]),
              'N_легкогидр_мг100г': число(r[2]), 'P_подв_мг100г': число(r[3]),
              'K_подв_мг100г': число(r[4]), 'pH_почвы': число(r[5])})
K = pd.DataFrame(K)

P = C.merge(K, on=['округ', 'тс'], how='left').merge(S, on=['округ', 'тс'], how='left') \
     .merge(B, on=['округ', 'тс'], how='left').merge(Y, on=['округ', 'тс'], how='left')
assert len(P) == 44 and P['орг_вещество_%'].notna().all(), 'не все точки почвы получили анализы'

# ---------- 4. Вода: точки из KML + табл. 18 отчёта ----------
t = open(KML, encoding='utf-8').read()
kml = []
for pm in re.findall(r'<Placemark.*?</Placemark>', t, re.S):
    if '<Point>' not in pm:
        continue
    name = re.search(r'<name>(.*?)</name>', pm, re.S).group(1).strip()
    desc = re.search(r'<description>(.*?)</description>', pm, re.S)
    c = re.search(r'<coordinates>\s*([^<]+)', pm).group(1).split(',')
    части = [x.strip() for x in name.split(',')]
    kml.append(dict(округ=округ(части[0]), тип=части[1].lower().replace(' ', ''),
                    тс=int(re.search(r'(\d+)', части[2]).group(1)),
                    lon=float(c[0]), lat=float(c[1]), desc=desc.group(1) if desc else ''))
kml = pd.DataFrame(kml)
Wk = kml[~kml.тип.str.startswith('трава')].copy()
Wk['источник'] = np.where(Wk.тип.str.contains('скважин'), 'скважина', 'водоём')

def очистить(d):
    d = re.sub(r'<!\[CDATA\[|\]\]>', '', d)
    d = re.sub(r'<br\s*/?>|</div>', ' ; ', d)
    d = re.sub(r'<[^>]+>', '', d).replace('&nbsp;', ' ')
    d = re.sub(r'\s*;\s*(;\s*)*', ' ; ', d).strip(' ;')
    return d or None
Wk['примечание'] = Wk.desc.apply(очистить)

W = []
for r in T[19][1:]:
    tc = 2 if 'скважина' in r[1] else int(r[1])   # «скважина (баллон)» в Аккудыке = ТС#2
    W.append(dict(округ=округ(r[0]), тс=tc, EC_mS=число(r[2]), TDS_мг_л=число(r[3]),
                  E_coli=число(r[4]), колиформы=число(r[5]), pH_воды=число(r[6]),
                  мутность_NTU=число(r[7]), оценка_воды=r[8]))
Wv = Wk[['округ', 'тс', 'источник', 'примечание', 'lon', 'lat']].merge(pd.DataFrame(W), on=['округ', 'тс'])
assert len(Wv) == 44, 'не все точки воды сопоставились с таблицей 18'

# ---------- 5. Общие поля и запись в базу ----------
def оформить(df, источник):
    df = df.copy()
    df.insert(1, 'нп', df.округ.map(ОКРУГА))
    df.insert(3, 'тс_код', 'ТС#' + df.тс.astype(str))
    df.insert(4, 'ключ', df.округ + '_ТС' + df.тс.astype(str))
    df['долгота'] = df.lon.round(6)
    df['широта'] = df.lat.round(6)
    df['коорд_источник'] = источник
    g = gpd.GeoDataFrame(df.drop(columns=['lon', 'lat']),
                         geometry=gpd.points_from_xy(df.lon, df.lat), crs=4326)
    return g.to_crs(CRS).sort_values(['округ', 'тс'])

БАЗА.parent.mkdir(exist_ok=True)
if БАЗА.exists():
    БАЗА.unlink()
оформить(P, 'отчёт, табл. 2–12').to_file(БАЗА, layer='почва_трава', driver='GPKG')
оформить(Wv, 'KML').to_file(БАЗА, layer='вода', driver='GPKG')
print(f'Шаг 1 готов: почва_трава = {len(P)}, вода = {len(Wv)} → {БАЗА.name}')
