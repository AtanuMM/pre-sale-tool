from app.security.passwords import hash_password

# Constant-time placeholder when email is unknown (computed once at import).
DUMMY_PASSWORD_HASH = hash_password("scopedesk-timing-placeholder")
