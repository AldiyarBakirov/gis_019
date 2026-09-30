"""Шаг 3. Фотографии из отчёта → docs/foto/.

Что делает:
  1) Табл. 2–12 отчёта: у каждой площадки 3 фото — общий вид участка, учётная рамка,
     измерение линейкой. Сохраняются как  <округ>_ts<N>_obshiy / _ramka / _lineyka .jpg
  2) Общие фото работ (отбор почвы, лаборатория, отбор воды) → obshie_<группа>_<N>.jpg
     Сканы актов из приложения НЕ выкладываются (в них подписи и печати).
  3) Уменьшает снимки до 1400 px по длинной стороне, чтобы сайт быстро открывался.
  4) Добавляет СВОИ фото: всё, что лежит в папке  исходные_данные/фото_дополнительные/
     с именем вида  Карасуский_ТС1_вода_1.jpg  (округ_ТСномер_почва|вода|трава_порядковый).

Список фото для сайта сохраняется в build/фото.json.
"""
import io, json, re, zipfile
from PIL import Image, ImageOps
from общее import *

z = zipfile.ZipFile(ОТЧЁТ)
x = z.read('word/document.xml').decode()
rels = z.read('word/_rels/document.xml.rels').decode()
R = {}
for тег in re.findall(r'<Relationship [^>]+>', rels):
    i = re.search(r'Id="([^"]+)"', тег).group(1); t = re.search(r'Target="([^"]+)"', тег).group(1)
    R[i] = t

ФОТО.mkdir(parents=True, exist_ok=True)

def сохранить(img_bytes, имя, макс=1400):
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert('RGB')
    im.thumbnail((макс, макс))
    im.save(ФОТО / имя, 'JPEG', quality=72, optimize=True, progressive=True)
    return f'foto/{имя}'

порядок = ['Карасуский', 'Акбулакский', 'Кишкенекольский', 'Бидайыкский', 'Актуесайский',
           'Кулыкольский', 'Кайратский', 'Тельжанский', 'Коктерекский', 'Амангельдинский',
           'Каратерекский']
ВИДЫ = [('obshiy', 'Общий вид участка'), ('ramka', 'Учётная рамка'), ('lineyka', 'Измерение линейкой')]
таблицы = re.findall(r'<w:tbl>.*?</w:tbl>', x, re.S)
точки = {}
for окр, t in zip(порядок, таблицы[1:12]):
    for r in re.findall(r'<w:tr[ >].*?</w:tr>', t, re.S)[1:]:
        cells = re.findall(r'<w:tc>.*?</w:tc>', r, re.S)
        тс = int(re.sub(r'<[^>]+>', '', cells[0]).strip())
        ключ = f'{окр}_ТС{тс}'
        точки[ключ] = []
        for (вид, подпись), c in zip(ВИДЫ, cells[2:5]):
            rid = re.search(r'r:embed="(rId\d+)"', c).group(1)
            src = сохранить(z.read('word/' + R[rid]), f'{ЛАТ[окр]}_ts{тс}_{вид}.jpg')
            точки[ключ].append(dict(src=src, cap=подпись, kind='почва'))

# Общие фото: картинки вне таблиц, сгруппированные по подписи «Рисунок N» после них
body = re.search(r'<w:body>(.*)</w:body>', x, re.S).group(1)
блоки = re.findall(r'<w:tbl>.*?</w:tbl>|<w:p[ >].*?</w:p>', body, re.S)
ГРУППЫ = {'Рисунок 1': 'Отбор почвенных образцов',
          'Рисунок 2': 'Лабораторное определение плотности и влажности почвы',
          'Рисунок 3': 'Отбор проб воды', 'Рисунок 4': 'Определение качества воды в лаборатории'}
общие, накоплено = {}, []
for б in блоки:
    if б.startswith('<w:tbl>'):
        continue
    накоплено += re.findall(r'r:embed="(rId\d+)"', б)
    текст = re.sub(r'<[^>]+>', '', б).strip()
    for ключ_рис, группа in ГРУППЫ.items():
        if текст.startswith(ключ_рис) and накоплено:
            n = list(ГРУППЫ).index(ключ_рис) + 1
            общие[группа] = [dict(src=сохранить(z.read('word/' + R[rid]), f'obshie_{n}_{i+1}.jpg'), cap='')
                             for i, rid in enumerate(накоплено)]
            накоплено = []
    if текст == 'Приложение':
        break   # дальше — сканы актов, их не публикуем
    if текст.startswith('Таблица') or текст.startswith('Анализ'):
        накоплено = []

# Дополнительные фото пользователя
доп = ИСХОДНЫЕ / 'фото_дополнительные'
if доп.exists():
    for f in sorted(доп.glob('*.jp*g')) + sorted(доп.glob('*.png')):
        m = re.match(r'(.+?)_ТС(\d)_(почва|вода|трава)', f.stem, re.I)
        if not m:
            print('  пропущено (имя не по шаблону):', f.name); continue
        окр = округ(m.group(1)); ключ = f'{окр}_ТС{m.group(2)}'; вид = m.group(3).lower()
        src = сохранить(f.read_bytes(), f'{ЛАТ[окр]}_ts{m.group(2)}_{"voda" if вид == "вода" else "dop"}_{f.stem[-2:].strip("_")}.jpg')
        точки.setdefault(ключ + ('_вода' if вид == 'вода' else ''), []).append(
            dict(src=src, cap='Источник воды' if вид == 'вода' else 'Доп. фото', kind=вид))

BUILD.mkdir(exist_ok=True)
json.dump(dict(points=точки, general=общие), open(BUILD / 'фото.json', 'w'), ensure_ascii=False)
print(f'Шаг 3 готов: фото площадок {sum(len(v) for v in точки.values())}, общих {sum(len(v) for v in общие.values())}')
