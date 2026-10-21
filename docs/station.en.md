# Station

[Русский](station.md) · [Documentation](README.en.md)

## Run

Python 3 is required; no third-party libraries are needed. From the repository root, run:

```sh
python3 station/server.py
```

Open `http://127.0.0.1:8321`. The server listens only on this computer's loopback address. Stop it with `Ctrl+C`.

Set `FVZ_PORT` to change the port or `FVZ_DB` to change the SQLite database path. By default the database is created at `station/data/station.sqlite`; keep it to preserve the reading log and dashboard layouts.

## Readings

Enter a row in the page form or send JSON to `POST /api/readings`. The server accepts a single object, an array of objects, or an object containing a `readings` array. Each row requires `sensor_id`, `quantity`, `unit`, and a numeric `value`; `node_id` defaults to `station`. Optional fields are `observed_at`, `experiment`, and `note`.

Supported quantities and units:

| `quantity` | `unit` |
| --- | --- |
| `air_temperature` | `celsius` |
| `relative_humidity` | `percent_rh` |
| `reference_temperature` | `celsius` |

Other API routes serve page state, the reading log, and dashboard settings; their implementation is in `station/server.py`.
