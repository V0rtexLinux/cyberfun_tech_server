"""
================================================================================
TESTES UNITÁRIOS - Cyber Fun Endoskeleton v3.1.0
================================================================================
Suite completa de testes para validação do sistema animatrônico.

Executar todos os testes:
    pytest tests/ -v

Executar com cobertura:
    pytest tests/ --cov=core --cov-report=html

Executar testes específicos:
    pytest tests/test_hardware.py -v
    pytest tests/test_expression.py::TestFacialExpression::test_emotion_presets -v
================================================================================
"""

import sys
import os

# Adicionar root ao path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
