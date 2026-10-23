"""GENERATED from PlantModule/interface.yaml by Gateway/scripts/gen_hub_params.py. Do not edit:
change the interface file and run the generator again (a hub test fails while they differ)."""

CONFIG = {'report_interval_s': {'default': 300, 'min': 10, 'max': 3600},
 'fast_report_interval_s': {'default': 30, 'min': 10, 'max': 300},
 'fast_report_hold_s': {'default': 120, 'min': 0, 'max': 1800},
 'batt_low_mv': {'default': 3600, 'min': 3000, 'max': 4000},
 'batt_critical_mv': {'default': 3400, 'min': 3000, 'max': 4000},
 'batt_cal_permille': {'default': 1000, 'min': 900, 'max': 1100}}

BATTERY = {'chemistry': 'li-ion-1s',
 'present_min_mv': 500,
 'history_reports': 5,
 'stale_factor': 2,
 'percent_curves': {'li-ion-1s': [(3900, 100),
                                  (3840, 90),
                                  (3780, 80),
                                  (3720, 70),
                                  (3660, 60),
                                  (3600, 50),
                                  (3540, 40),
                                  (3480, 30),
                                  (3420, 20),
                                  (3380, 10),
                                  (3320, 5),
                                  (3300, 0)]}}
