# Political Shift

An interactive Dash map of county presidential election outcomes and voting
swings from 2000 to 2020. Click a county to view its voting history.

The public app is hosted at
[political-shift.akaisenghor.bottle.cloud](https://political-shift.akaisenghor.bottle.cloud/).

## Run locally

Use Python 3.12:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/gunicorn --bind 0.0.0.0:8080 --workers 2 wsgi:application
```

Open `http://localhost:8080`. Run the route and callback checks with
`.venv/bin/python -m unittest -v test_app`.

The Docker image uses the same pinned dependencies:

```sh
docker build -t political-shift .
docker run --rm -p 8080:8080 political-shift
```

## Deploy to Cloud in a Bottle

The root `cloudinabottle.toml` points to the Dockerfile, port 8080, and
`/healthz`. Every app route is public so portfolio visitors can load the map,
Dash assets, and callbacks without logging in. The app has no account system,
uploads, or persistent data. County selection lives in each browser's memory.

After committing and pushing the deployment files to `master`:

```sh
bottle app deploy https://github.com/AkaiS/political_shift --name political-shift --wait --instance akaisenghor.bottle.cloud
```

For updates, push to the same branch and rebuild the deployed app:

```sh
bottle app reload political-shift --update --wait --instance akaisenghor.bottle.cloud
bottle app logs political-shift --instance akaisenghor.bottle.cloud
```

## Data and map tiles

`counties_minus_alaskan.csv` contains the original election data. The bundled
`counties.geojson` comes from Plotly's
[county geometry dataset](https://github.com/plotly/datasets/blob/0c447c47b757ad74edecab31f0d72f849d2e67c2/geojson-counties-fips.json).
Both files load from the app directory, so server startup needs no network
requests. The browser loads OpenStreetMap basemap tiles through Plotly's
`open-street-map` style. No API key is required.

Direct dependency ranges live in `requirements.in`; `requirements.txt` pins
the full environment. Refresh the lock with
`uv pip compile requirements.in --python-version 3.12 --output-file requirements.txt`.
