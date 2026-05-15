# NSOS verb handlers. One file per verb, each exposing:
#   def handle(envelope: dict) -> str
# router.py loads these dynamically at dispatch time.
