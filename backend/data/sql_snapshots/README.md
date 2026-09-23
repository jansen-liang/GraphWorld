# Scene and object catalog snapshot

`scene_catalog_data.sql` is a data-only PostgreSQL snapshot of the `scenes`,
`scene_versions`, `scene_nodes`, `scene_edges`, and `object_catalog` tables. It
does not contain users, credentials, run records, or database schema.

Restore it into an empty GraphWorld database after applying the schema
migrations:

```bash
alembic upgrade head
psql "$GRAPHWORLD_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f backend/data/sql_snapshots/scene_catalog_data.sql
```

Do not run the scene/catalog seed scripts before restoring this snapshot. The
snapshot includes the current complete scene-version history and catalog rows.
Reviewable JSON exports are also kept in `backend/data/scene_versions/` and
`backend/data/object_catalog/object_catalog.json`.
