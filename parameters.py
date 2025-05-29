processing_graph = {
    'P1': {'P3': (20, 'T1')},
    'P3': {'P4': (20, 'T2')},
    'P4': {'P5': (45, 'T3'), 'P9': (20, 'T2')},
    'P5': {'P8': (45, 'T4'), 'P7': (30, 'T6')},
    'P8': {'P6': (30, 'T5')},
    'P2': {'P9': (15, 'T6')},
    'P9': {'P10': (20, 'T5'), 'P11': (30, 'T1')},
    'P6': {},
    'P7': {},
    'P10': {},
    'P11': {}
}

machines_tools = {
    "M1a": ["T1", "T2", "T3"],
    "M1b": ["T1", "T3", "T4"],
    "M2a": ["T2", "T3", "T4"],
    "M2b": ["T3", "T4", "T5"],
    "M3a": ["T3", "T4", "T5"],
    "M3b": ["T4", "T5", "T6"],
    "M4a": ["T4", "T5", "T6"],
    "M4b": ["T5", "T6", "T1"],
    "M5a": ["T5", "T6", "T1"],
    "M5b": ["T6", "T1", "T2"],
    "M6a": ["T6", "T1", "T2"],
    "M6b": ["T1", "T2", "T3"]
}

MACHINE_PARTNERS = {
    'M1b': 'M1a',
    'M2b': 'M2a',
    'M3b': 'M3a',
    'M4b': 'M4a',
    'M5b': 'M5a',
    'M6b': 'M6a',
}

PASS_THROUGH_DURATION_ON_A = 5
PASS_THROUGH_DURATION_ON_B = 5
TIME_TOOL_CHANGE = 30


order = {
    'name': 'Alpha Client',
    'nif': 333444,
    'orderID': 102,
    'orders': [
        {
            'type': 5,
            'quantity': 3,
            'dDate': 10,
            'penalty': 1.0
        },
        {
            'type': 7,
            'quantity': 1,
            'dDate': 9,
            'penalty': 2.0
        }
    ]
}

'''

order = {
    'name': 'Alpha Client',
    'nif': 333444,
    'orderID': 102,
    'orders': [
        {
            'type': 5,
            'quantity': 3,
            'dDate': 10,
            'penalty': 1.0
        },
        {
            'type': 9,
            'quantity': 1,
            'dDate': 9,
            'penalty': 2.0
        },
        {
            'type': 6,
            'quantity': 5,
            'dDate': 9,
            'penalty': 2.0
        }
    ]
}
'''