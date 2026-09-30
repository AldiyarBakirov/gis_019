"""Пересобрать всё: базу, фото, оценки и сайт — по порядку, шаги 01–05.

Запуск из папки проекта:
    python3 скрипты/run_all.py
"""
import runpy, sys, time
from pathlib import Path

папка = Path(__file__).resolve().parent
sys.path.insert(0, str(папка))
ШАГИ = ['01_точки_и_анализы.py', '02_границы.py', '03_фото.py',
        '04_оценка_и_рекомендации.py', '05_сайт.py']
t0 = time.time()
for шаг in ШАГИ:
    print(f'▶ {шаг}')
    runpy.run_path(str(папка / шаг), run_name='__main__')
print(f'Готово за {time.time() - t0:.0f} с. Откройте docs/index.html в браузере.')
