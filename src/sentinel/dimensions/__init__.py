from .injection import InjectionDimension
from .pii_leak import PiiLeakDimension

ALL_DIMENSIONS = [InjectionDimension(), PiiLeakDimension()]
