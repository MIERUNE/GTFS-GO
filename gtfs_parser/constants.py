"""
The GTFS_DATATYPES dict shows the files that are expected to be inside the zip file.
In case a required file is missing while loading it will raise an error.
"""

GTFS_DATATYPES = {
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
