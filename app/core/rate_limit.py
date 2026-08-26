from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared by main.py (middleware + exception handler registration) and any
# router that needs per-IP limits on abuse-prone endpoints (auth in
# particular — brute-force / credential-stuffing / email-bombing targets).
limiter = Limiter(key_func=get_remote_address)
