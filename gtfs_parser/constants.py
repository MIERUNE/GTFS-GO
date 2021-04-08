"""
The GTFS_JP_DATATYPES dict shows the files that are expected to be inside the zip file.
In case a required file is missing it will raise an error during the data load.
"""

GTFS_JP_DATATYPES = {
    'agency_jp': {
        'required': False
    },
    'agency': {
        'required': True
    },
    'calendar_dates': {
        'required': False
    },
    'calendar': {
        'required': True
    },
    'fare_attributes': {
        'required': False
    },
    'fare_rules': {
        'required': False
    },
    'feed_info': {
        'required': False
    },
    'frequencies': {
        'required': False
    },
    'office_jp': {
        'required': False
    },
    'routes_jp': {
        'required': False
    },
    'routes': {
        'required': True
    },
    'shapes': {
        'required': False
    },
    'stop_times': {
        'required': True
    },
    'stops': {
        'required': True
    },
    'transfers': {
        'required': False
    },
    'translations': {
        'required': False
    },
    'trips': {
        'required': True
    }
}
