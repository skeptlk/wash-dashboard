import sys
sys.path.insert(0, 'pythonlib')

import pandas as pd
from enginewash import WashCalculator, FlightRecord, MaintenanceRecord, EGTHDM

# Записи о техническом обслуживании
# 223 — очистка коннекторов
# 224 — замена термопары
# 330-340 — промывка водой и растворами

# columns : engine_id, maint_datetime, ata_code, ata_classification, reason, creation_datetime
maintenance = pd.read_csv('https://storage.yandexcloud.net/ecm-data/ecmapp.maintenance_20260222.csv',
                          parse_dates=['creation_datetime', 'maint_datetime'])

# Отчеты, записанные в фазу круиза
# columns : ['aircraft_id', 'engine_position', 'flight_datetime', 'zpcn12', 'zpcn25',
    #    'zpoil', 'zt49', 'ztoil', 'zvb1f', 'zwf36', 'brat', 'degt', 'dpoil',
    #    'egtc', 'egthdm', 'gegtmc', 'gn2mc', 'gpcn25', 'gwfm', 'pcn12',
    #    'pcn12i', 'pcn1k', 'pcn2c', 'pip_bled', 'pip_etop', 'pip_oilm',
    #    'pip_pem', 'pip_vlcr', 'pip_xn1c', 'sloatl', 'wbi', 'wfmp', 'zpcn25_d',
    #    'zt49_d', 'zwf36_d', 'agw', 'ibe1', 'ibe2', 'ibp1', 'ibp2', 'ivs12',
    #    'sat', 'zalt', 'zt1a', 'zxm', 'engine_id', 'n1_modifier'],

data_cruise = pd.read_csv('https://storage.yandexcloud.net/ecm-data/s7.b737_cruise_20260222-merged.csv',
                           parse_dates=['flight_datetime'])

# Отчеты, записанные на взлете
data_takeoff  = pd.read_csv('https://storage.yandexcloud.net/ecm-data/s7.b737_takeoff_20260222-merged.csv',
                           parse_dates=['flight_datetime'])

# use engine wash library to calculate wash effects for takeoff (for EGTHDM parameter only)

wash_maint = maintenance[maintenance['ata_code'].astype(str).str.match(r'^3[34]\d$')]

takeoff = data_takeoff[['engine_id', 'flight_datetime', 'egthdm']].dropna()
takeoff = takeoff.assign(engine_id=takeoff['engine_id'].astype(int).astype(str))

flights = [
    FlightRecord(
        engine_id=row.engine_id,
        flight_datetime=row.flight_datetime,
        float_value=row.egthdm,
    )
    for row in takeoff.itertuples()
]

maintenance_records = [
    MaintenanceRecord(
        engine_id=str(row.engine_id),
        maint_datetime=row.maint_datetime.tz_localize(None),
        ata_code=str(row.ata_code),
    )
    for row in wash_maint[['engine_id', 'maint_datetime', 'ata_code']].itertuples()
]

calc = WashCalculator()
result = calc.process(flights=flights, maintenance=maintenance_records, parameter=EGTHDM)

print(result.df_event)