# pywash

Python-библиотека для расчёта эффекта промывки авиационных двигателей по параметрам технического состояния. Портирование класса `CalculatorHistory_v2` с R6 на чистый Python.

## Структура

```
pywash/
├── __init__.py             # Экспорт публичного API
├── models.py               # WashParameter, WashEvent, WashResult, перечисления, пресеты
├── smoothing.py            # Центрированное скользящее среднее (аналог caTools::runmean)
├── detection.py            # Расчёт дельты до/после промывки и обнаружение потери эффективности
└── calculator.py           # WashCalculator — полный конвейер обработки
```

## Конвейер обработки

Соответствует реализации на R:

1. **Подготовка** — привязка событий промывки к первому полёту после даты технического обслуживания
2. **Сегментация** — `event_cum = cumsum(event)` разбивает временной ряд каждого двигателя на сегменты (0 = до первой промывки, 1 = между первой и второй промывками и т.д.)
3. **Сглаживание** — центрированное скользящее среднее (окно по умолчанию = 30 полётов) в пределах каждого сегмента
4. **Расчёт дельт** — опорные значения до и после промывки по худшему/лучшему из последних/первых N наблюдений
5. **Обнаружение потери эффективности** — поиск первого полёта, в котором сглаженное значение возвращается в зону порогового отклонения от уровня до промывки
6. **Формирование таблицы событий** — одна строка на промывку: дельта, дата потери эффективности, опциональные метрики налёта (циклы/часы)

## Параметры

В библиотеке предусмотрены три преднастроенных параметра двигателя:

| Константа | Параметр | Фаза полёта | Направление | Порог | Описание                                  |
| --------- | -------- | ----------- | ----------- | ----- | ----------------------------------------- |
| `GWFM`    | GWFM     | CRUISE      | DOWN (-1)   | 0.05  | Расход топлива — чем ниже, тем лучше      |
| `DEGT`    | DEGT     | CRUISE      | DOWN (-1)   | 2.0   | Дифференциальная ТГТ — чем ниже, тем лучше |
| `EGTHDM`  | EGTHDM   | TAKEOFF     | UP (+1)     | 2.0   | Запас по ТГТ — чем выше, тем лучше        |

`TrendDirection` обобщает алгоритм так, чтобы он одинаково работал для параметров с противоположным «направлением улучшения».

## Архитектура

- **Чистый Python** — без C/Cython-расширений и шага компиляции
- **Без зависимости от БД** — принимает на вход pandas DataFrame; доступ к данным остаётся на стороне вызывающего кода
- **Зависимости времени выполнения** — только pandas и numpy

## Установка

```bash
cd pythonlib
pip install -e .
```

С зависимостями для разработки (pytest):

```bash
pip install -e ".[dev]"
```

## Тесты

```bash
cd pythonlib
python -m pytest tests/ -v
```

## Использование

```python
import pandas as pd
from pywash import WashCalculator, WashConfig, GWFM, DEGT, EGTHDM

# Записи о полётах — одна строка на полёт на двигатель
flights_df = pd.DataFrame({
    "engine_id":          [...],
    "flight_datetime":    [...],
    "float_value":        [...],  # сырое значение параметра
    "float_value_smooth": [...],  # предсглаженное значение (опционально, fallback на сырое)
})

# События технического обслуживания (промывки)
maintenance_df = pd.DataFrame({
    "engine_id":      [...],
    "maint_datetime": [...],
    "ata_code":       [...],  # например, "206", "207", "209"
})

# Один параметр
calc = WashCalculator(WashConfig(smooth_window=30, n_obs_mean=15))
result = calc.process(flights_df, maintenance_df, parameter=GWFM)

result.df         # Полный временной ряд со сглаженными значениями и аннотациями
result.events     # Список объектов WashEvent
result.df_event   # Сводный DataFrame (одна строка на промывку)

# Все три параметра сразу — таблицы событий объединяются
result = calc.process_all(flights_df, maintenance_df, parameters=[GWFM, DEGT, EGTHDM])
# result.df_event содержит колонки: delta_GWFM_CRUISE, delta_DEGT_CRUISE, delta_EGTHDM_TAKEOFF, ...
```

### Пользовательские параметры

```python
from pywash import WashParameter, FlightPhase, TrendDirection

my_param = WashParameter(
    name="N1VIB",
    flight_phase=FlightPhase.CRUISE,
    trend_direction=TrendDirection.DOWN,
    threshold=0.5,
)
result = calc.process(flights_df, maintenance_df, parameter=my_param)
```

### Обогащение данными о налёте

Для получения количества циклов и часов между промывкой и потерей эффективности передайте DataFrame с данными о налёте:

```python
utilization_df = pd.DataFrame({
    "engine_id":      [...],
    "flight_datetime": [...],
    "tac":            [...],  # суммарное количество циклов (TAC)
    "tah":            [...],  # суммарный налёт в минутах (TAH)
})

result = calc.process(flights_df, maintenance_df, GWFM, utilization_df=utilization_df)
# result.df_event получает колонки: cyc_loe_GWFM_CRUISE, hrs_loe_GWFM_CRUISE, days_loe_GWFM_CRUISE
```
