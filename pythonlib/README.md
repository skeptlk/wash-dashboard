# pywash

Python-библиотека для расчёта эффекта промывки авиационных двигателей по параметрам технического состояния.

## Структура

```
pywash/
├── __init__.py             # Экспорт публичного API
├── models.py               # Модели: WashParameter, WashEvent
├── smoothing.py            # Центрированное скользящее среднее
├── detection.py            # Расчёт дельты до/после промывки и обнаружение потери эффективности
└── calculator.py           # WashCalculator - основной модуль-обработчик
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

| Константа | Параметр | Фаза полёта | Направление | Порог | Описание                              |
| --------- | -------- | ----------- | ----------- | ----- | ------------------------------------- |
| `GWFM`    | GWFM     | CRUISE      | DOWN (-1)   | 0.05  | Delta Fuel Flow — чем ниже, тем лучше |
| `DEGT`    | DEGT     | CRUISE      | DOWN (-1)   | 2.0   | Delta EGT — чем ниже, тем лучше       |
| `EGTHDM`  | EGTHDM   | TAKEOFF     | UP (+1)     | 2.0   | EGT Margin — чем выше, тем лучше      |

## Архитектура

- **Python** — без C/Cython-расширений и компиляции
- **Без зависимости от БД** — принимает на вход а; доступ к данным остаётся на стороне вызывающего кода
- **Runtime зависимости** — только pandas и numpy

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
from pywash import WashCalculator, WashConfig, FlightRecord, FlightPhase, MaintenanceRecord, GWFM, DEGT, EGTHDM

# Записи о полётах — одна строка на полёт на двигатель на параметр.
# parameter_name и flight_phase должны соответствовать анализируемому параметру.
flights = [
    FlightRecord(
        engine_id="12345",
        flight_datetime=dt,
        parameter_name="GWFM",
        flight_phase=FlightPhase.CRUISE,
        float_value=raw_value,
        float_value_smooth=smooth_value,  # optional
    ),
    ...
]

# События технического обслуживания (промывки)
maintenances = [
    MaintenanceRecord(engine_id="ENG001", maint_datetime=dt, ata_code="330"),
    ...
]

# Один параметр
calc = WashCalculator(WashConfig(smooth_window=30, n_obs_mean=15))
result = calc.process(flights, maintenances, parameter=GWFM)

result     # Список объектов WashEventSummary

# Все три параметра сразу — process_all фильтрует записи по parameter_name + flight_phase
# и объединяет результаты в единый список WashEventSummary
result = calc.process_all(flight_data, maintenances, parameters=[GWFM, DEGT, EGTHDM])
```

### Кастомные параметры

```python
from pywash import WashParameter, FlightPhase, TrendDirection

custom_param = WashParameter(
    name="N1VIB",
    flight_phase=FlightPhase.CRUISE,
    trend_direction=TrendDirection.DOWN,
    threshold=0.5,
)
result = calc.process(flights, maintenances, parameter=custom_param)
```

### Обогащение данными о налёте

Для получения количества полетных циклов и часов наработки двигателя между промывкой и потерей эффективности передайте DataFrame с данными о налёте:

```python
utilization_df = pd.DataFrame({
    "engine_id":      [...],
    "flight_datetime": [...],
    "tac":            [...],  # суммарное количество циклов (TAC)
    "tah":            [...],  # суммарный налёт в минутах (TAH)
})

result = calc.process(flights, maintenances, GWFM, utilization_df=utilization_df)
# result получает обогащённые WashEvent с колонками: cyc_loe_GWFM_CRUISE, hrs_loe_GWFM_CRUISE, days_loe_GWFM_CRUISE
```
