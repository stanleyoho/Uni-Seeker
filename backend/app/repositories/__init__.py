"""Repository layer — CRUD-only abstractions over ORM models.

Per design plan §11 anti-coupling rules: repos MUST NOT contain business
logic. They CRUD + simple queries, nothing else.
"""
