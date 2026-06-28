import sys
try:
    import PyQt6
    import PyQt6.sip
    sys.modules['PyQt6.sip'] = PyQt6.sip
except ImportError:
    pass
