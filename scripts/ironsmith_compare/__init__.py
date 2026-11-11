"""Local, on-demand comparison of magic-cards-model with a pinned ironsmith checkout.

See `docs/ironsmith-compare.md`. ironsmith is reached only as separate processes (its own
unmodified binaries and test runner, fed our data files); nothing here imports, contains
or copies ironsmith code, and nothing here runs in CI.
"""
