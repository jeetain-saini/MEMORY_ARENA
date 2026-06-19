"""Application services — orchestration of use cases.

Services coordinate use cases and read-side repository access into a single
entry point for the delivery layer. They contain orchestration only: no
persistence details (those live behind the Unit of Work / repository ports) and
no HTTP details (those live in the API layer).
"""
