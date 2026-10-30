"""Шаг 3. Фотографии из отчётов → docs/foto/.

Что делает (для каждого выезда из ОТЧЁТЫ в общее.py):
  1) Таблицы площадок отчёта: у каждой площадки 3 фото – общий вид участка, учётная рамка,
     измерение линейкой. Сохраняются как  <округ>_ts<N>_obshiy / _ramka / _lineyka <метка>.jpg
     (у августа метки нет, у сентября – «_sen»).
  2) Общие фото работ (подписи «Рисунок N» из ОТЧЁТЫ) → obshie<метка>_<N>_<порядковый>.jpg
     Сканы актов из приложения НЕ выкладываются (в них подписи и печати).
  3) Уменьшает снимки до 1000 px по длинной стороне, чтобы сайт быстро открывался.
  4) Добавляет СВОИ фото: всё, что лежит в папке  исходные_данные/фото_дополнительные/
     с именем вида  Карасуский_ТС1_вода_1.jpg  (округ_ТСномер_почва|вода|трава_порядковый).
     Такие фото показываются при любом выезде.

Уже сохранённые фото не пересжимаются; чтобы пересоздать все фото – удалите папку docs/foto.
Если файла отчёта нет на компьютере – фото этого выезда пропускаются (сайт соберётся без них).
Список фото для сайта сохраняется в build/фото.json.
"""
import io, json, re, zipfile
from PIL import Image, ImageOps
from общее import *

ФОТО.mkdir(parents=True, exist_ok=True)


def сохранить(img_bytes, имя, макс=1000):
    if not (ФОТО / имя).exists():          # уже готовые фото не пересжимаем
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(img_bytes))).convert('RGB')
        im.thumbnail((макс, макс))
        im.save(ФОТО / имя, 'JPEG', quality=72, optimize=True, progressive=True)
    return f'foto/{имя}'


ВИДЫ = [('obshiy', 'Общий вид участка'), ('ramka', 'Учётная рамка'), ('lineyka', 'Измерение линейкой')]
по_выездам = {}
for выезд, о in ОТЧЁТЫ.items():
    if not о['файл'].exists():
        print(f'  ! нет файла отчёта для «{выезд}»: {о["файл"].name} – фото пропущены')
        continue
    z = zipfile.ZipFile(о['файл'])
    x = z.read('word/document.xml').decode()
    rels = z.read('word/_rels/document.xml.rels').decode()
    R = {re.search(r'Id="([^"]+)"', т).group(1): re.search(r'Target="([^"]+)"', т).group(1)
         for т in re.findall(r'<Relationship [^>]+>', rels)}
    метка = о['метка']

    таблицы = re.findall(r'<w:tbl>.*?</w:tbl>', x, re.S)
    точки = {}
    for окр, t in zip(ПОРЯДОК_ОКРУГОВ, таблицы[о['площадки'][0]:о['площадки'][1]]):
        for r in re.findall(r'<w:tr[ >].*?</w:tr>', t, re.S)[1:]:
            cells = re.findall(r'<w:tc>.*?</w:tc>', r, re.S)
            тс = int(re.sub(r'<[^>]+>', '', cells[0]).strip())
            ключ = f'{окр}_ТС{тс}'
            точки[ключ] = []
            for (вид, подпись), c in zip(ВИДЫ, cells[2:5]):
                rid = re.search(r'r:embed="(rId\d+)"', c)
                if rid:
                    src = сохранить(z.read('word/' + R[rid.group(1)]), f'{ЛАТ[окр]}_ts{тс}_{вид}{метка}.jpg')
                    точки[ключ].append(dict(src=src, cap=подпись, kind='почва'))

    # Общие фото: картинки вне таблиц, сгруппированные по подписи «Рисунок N» после них
    body = re.search(r'<w:body>(.*)</w:body>', x, re.S).group(1)
    блоки = re.findall(r'<w:tbl>.*?</w:tbl>|<w:p[ >].*?</w:p>', body, re.S)
    общие, накоплено = {}, []
    for б in блоки:
        if б.startswith('<w:tbl>'):
            continue
        накоплено += [r for r in re.findall(r'r:embed="(rId\d+)"', б) if R.get(r, '').startswith('media/')]
        текст = re.sub(r'<[^>]+>', '', б).strip()
        for ключ_рис, группа in о['рисунки'].items():
            if re.match(ключ_рис + r'\b', текст) and накоплено:
                n = ключ_рис.split()[-1]
                общие[группа] = [dict(src=сохранить(z.read('word/' + R[rid]), f'obshie{метка}_{n}_{i + 1}.jpg'), cap='')
                                 for i, rid in enumerate(накоплено)]
        if текст.startswith('Рисунок'):
            накоплено = []
        if текст == 'Приложение':
            break   # дальше – сканы актов, их не публикуем
        if текст.startswith('Таблица') or текст.startswith('Анализ'):
            накоплено = []
    по_выездам[выезд] = dict(points=точки, general=общие)
    print(f'  {выезд}: фото площадок {sum(len(v) for v in точки.values())}, '
          f'общих {sum(len(v) for v in общие.values())} ({", ".join(общие)})')

# Дополнительные фото пользователя (для всех выездов)
доп_фото = {}
доп = ИСХОДНЫЕ / 'фото_дополнительные'
if доп.exists():
    for f in sorted(доп.glob('*.jp*g')) + sorted(доп.glob('*.png')):
        m = re.match(r'(.+?)_ТС(\d)_(почва|вода|трава)', f.stem, re.I)
        if not m:
            print('  пропущено (имя не по шаблону):', f.name); continue
        окр = округ(m.group(1)); ключ = f'{окр}_ТС{m.group(2)}'; вид = m.group(3).lower()
        src = сохранить(f.read_bytes(), f'{ЛАТ[окр]}_ts{m.group(2)}_{"voda" if вид == "вода" else "dop"}_{f.stem[-2:].strip("_")}.jpg')
        доп_фото.setdefault(ключ + ('_вода' if вид == 'вода' else ''), []).append(
            dict(src=src, cap='Источник воды' if вид == 'вода' else 'Доп. фото', kind=вид))

BUILD.mkdir(exist_ok=True)
json.dump(dict(trips=по_выездам, extra=доп_фото), open(BUILD / 'фото.json', 'w'), ensure_ascii=False)
print('Шаг 3 готов')
