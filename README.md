# FR24_Node

A Tesserae widget that shows the aircraft nearest to you, using the
Flightradar24 feeder already running on your network.

Shows the callsign, altitude and when the aircraft was last heard. When
public lookups know the flight, it also shows the airline, the route
(origin → destination), the aircraft's manufacturer and type, and the
airline's logo.

## What it shows

| Size | Contents |
|------|----------|
| xs | Callsign and altitude |
| sm | Adds the title, the airline logo (or a plane icon), origin and destination codes, and the last-heard time |
| md, lg | Adds the airline name, the aircraft manufacturer and type, and the airport cities |

The plane icon and the altitude chip are coloured by altitude band, using
the theme's accent colours: below 3,000 ft, 3,000–10,000 ft, and above
10,000 ft.

## Requirements

- A Flightradar24 feeder (`fr24feed`) on your network. Its local web
  interface publishes the aircraft it is tracking at
  `http://<feeder>:8754/flights.json`.
- Outbound internet access from the Tesserae server, for the optional
  lookups below. Without it the widget still shows the callsign, altitude
  and time.

## Install

Choose one of these methods.

**Upload (simplest).** Package the folder and upload it from the Widgets
page:

```sh
tar czf fr24_node.tar.gz -C plugins fr24_node
```

In Tesserae, go to **Widgets → Upload widget** and choose `fr24_node.tar.gz`. The
widget lands in `data/authored/fr24_node/`, which survives upgrades, and can be
used straight away.

**Copy the folder.** Copy `fr24_node/` into the `plugins/` directory of a
Tesserae checkout (or of the Docker image) and restart the server.

## Configure

Add an **FR24_Node** cell to a dashboard (it's under **Transport**). Then set its
options:

| Option | Default | Notes |
|--------|---------|-------|
| Radar node | `http://<feeder IP>:8754/flights.json` | Your feeder's `flights.json` address. Change this to your feeder's IP. |
| Latitude | `45.0000` | Where you're watching from, in decimal degrees. North is positive. |
| Longitude | `-95.0000` | Decimal degrees. East is positive, so anywhere west of Greenwich is negative. |

The defaults are nearish to the author's own location; replace them with yours.

The widget has its own latitude and longitude rather than using Tesserae's
location setting, to match with where your feeder is running.

## How "nearest" is chosen

- **Skipped:** aircraft without a callsign or a position fix, and any not
  heard within two minutes of the feeder's newest report.
- **Ranking:** the rest are scored by ground distance plus three times
  their altitude, so a low aircraft a few miles away beats an airliner
  cruising directly overhead.
- **Refresh:** the result is cached for 5 minutes.

## Data sources and privacy

Apart from the feeder, the widget contacts two free public services:

| Service | Sent | Used for | Cached for |
|---------|------|----------|------------|
| [adsbdb.com](https://www.adsbdb.com) | The aircraft's Mode S hex code | Manufacturer and type | 30 days (7 days if unknown) |
| [adsbdb.com](https://www.adsbdb.com) | The callsign | Airline and route | 1 day |
| [soaringsymbols.org](https://soaringsymbols.org) | The three-letter airline code (e.g. `DAL`) | Airline logo (SVG) | 180 days (7 days if unknown) |

- **No location is sent.** Your coordinates never leave the server.
- **Lookups are best-effort.** If a service is slow or down, that detail is
  left out and retried on the next refresh.
- **Logos need an airline callsign.** A logo is only looked up when the
  callsign starts with a three-letter airline code. Private aircraft flying
  under their registration (e.g. `N693BB`) keep the plane icon.
- **Logos are checked before use.** A logo must be an SVG under 64 KB. It's
  passed to the card as an embedded image, so the browser fetches nothing
  itself and scripts inside the file can't run.
- **Cache location:** everything is stored under the widget's data folder
  (`data/plugins/fr24/`).

Route data comes from adsbdb's crowd-sourced database. It can be missing or
out of date for some flights, especially regional and charter ones. The route 
you get for a callsign may well not be correct. Nothing this widget can do about that.

## Permissions

The plugin declares `network:*`. It needs this because the feeder's address
is whatever you enter, so it can't be listed in advance. The address is
still checked by Tesserae's network guard: LAN addresses are allowed, while
link-local and cloud-metadata addresses are refused.

## Troubleshooting

| Message | Meaning |
|---------|---------|
| Can't reach the radar node right now. | The feeder is off, the address is wrong, or the Tesserae server can't reach it on the network. Open the address in a browser from the same machine. |
| The radar node didn't return flight data. | Something answered, but not with `flights.json`. Check the path ends in `/flights.json`. |
| That radar node address isn't allowed. | The address isn't a valid http(s) URL, or the network guard refused it. |
| No aircraft in range | The feeder is working, but nothing qualifying is being tracked right now. |

## Development

The tests use canned feeder and lookup responses, so they need no network:

```sh
uv run pytest plugins/fr24_node
```

Preview a size at `/_test/render?plugin=fr24_node&size=md` on a running server.

## Credits

- Aircraft and route data: [adsbdb](https://www.adsbdb.com).
- Airline logos: [Soaring Symbols](https://soaringsymbols.org). Logos are
  trademarks of their respective airlines.
- "FR24" refers to the Flightradar24 feeder software that supplies the
  data. This widget is not affiliated with Flightradar24.
