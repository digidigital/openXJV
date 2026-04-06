#!/usr/bin/env python3
# coding: utf-8
"""Validierungsmodule fuer openXJV.

Stellt XSD-Validierung fuer XJustiz-XML-Dateien bereit.
"""

from .xsd_validator import XSDValidator, ValidationError, ValidationResult
from .xsd_validator_dialog import XSDValidatorDialog

__all__ = [
    'XSDValidator',
    'XSDValidatorDialog',
    'ValidationError',
    'ValidationResult',
]
