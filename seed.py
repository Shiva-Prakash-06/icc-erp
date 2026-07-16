"""Legacy entry point retained only to prevent accidental unsafe seeding.

Use explicit Flask commands instead:

    flask --app run:app bootstrap-reference-data
    flask --app run:app bootstrap-admin
    flask --app run:app demo-import-supplied  # demonstrator environments only
"""

raise SystemExit(
    "Automatic synthetic seeding was retired. Use the explicit, environment-gated Flask commands documented in README.md."
)
