"""Local workspace configuration.

API credentials for OKX exchange.
"""
import os

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = WORKSPACE

# OKX API credentials (read from env vars first, fallback to direct values)
OKX_API_KEY = os.environ.get('OKX_API_KEY', 'd7cde2ad-9941-4e7b-ab69-d6bdfde2a0b6')
OKX_SECRET_KEY = os.environ.get('OKX_SECRET_KEY', '5DCF29283C642D2C09308357E5ADFA6D')
OKX_PASSPHRASE = os.environ.get('OKX_PASSPHRASE', 'LMM123456lbl@')
