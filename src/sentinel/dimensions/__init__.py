from .hallucination import HallucinationDimension
from .injection import InjectionDimension
from .nondeterminism import NonDeterminismDimension
from .pii_leak import PiiLeakDimension

ALL_DIMENSIONS = [
    InjectionDimension(),
    PiiLeakDimension(),
    HallucinationDimension(),
    NonDeterminismDimension(),
]
