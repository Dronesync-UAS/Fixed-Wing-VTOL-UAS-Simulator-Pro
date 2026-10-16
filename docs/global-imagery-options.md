# Global imagery with no strings attached: what is actually available

12 October 2026.

The question was whether there is a free, global, unencumbered
alternative to Google Photorealistic 3D Tiles. The short answer is that
**everything pre-made is encumbered in some way**, and the one genuinely
unencumbered global path requires processing the raw data yourself.

## What this project already has

| Provider | Key needed | Global | Terms |
|---|---|---|---|
| **USGS National Map** | no | **no - USA only** | public domain |
| **Esri World Imagery** | no | yes | "check Esri's terms of use" - not unencumbered |
| **Mapbox Satellite** | yes | yes | token, Mapbox's terms, no offline use |
| **Mapbox Outdoors** | yes | yes | as above |

## What was looked at, and what the licences actually say

### Copernicus Sentinel-2 - the raw data

The official Copernicus legal notice grants free access for
"reproduction, distribution, communication to the public, and adaptation
or combination with other data". The only condition is attribution, in
the form "Copernicus Sentinel data [Year]".

**That is genuinely unencumbered**: self-host, work offline, use
commercially, redistribute. 10 m resolution, global.

**The catch**: there is no ready-made XYZ tile service for it under
those terms. The raw data is scenes, not tiles. Using it means a free
Copernicus Data Space Ecosystem account, downloading scenes, and
mosaicking them. That is real work - a day or two - and it is the only
path on this page with no restriction at the end of it.

### EOX "Sentinel-2 cloudless" - the pre-made mosaic

This is the obvious candidate: a global, cloud-free Sentinel-2 mosaic
served as WMTS, no account needed. **Its licensing is the problem.**

| Layer | Licence | Commercial use |
|---|---|---|
| **2016** | CC BY 4.0 | **yes** |
| 2018 to 2023 | CC BY-NC-SA 4.0 | **no** |
| any year, commercially | EOX Commercial Attribution-RestrictedUse 1.1 | yes, paid, and "you just can't transfer this license to your users" |

So the only EOX layer a commercial training provider may use freely is
the **2016** one. For a flight trainer that is a smaller problem than it
sounds: the ground does not move much, and 2016 imagery of Norfolk is
still Norfolk. But it has to be the 2016 layer, with EOX's own
attribution string, and that string includes links which must be kept in
online use.

**I could not verify EOX's exact tile URL or their licence text
directly.** eox.at, s2maps.eu and tiles.maps.eox.at are all DNS-blocked
from the machine this was researched on. The licence summary above comes
from search results quoting their pages, not from their pages. Before
any of it is written into a tool, somebody has to open s2maps.eu and
read the terms and the endpoint.

### The others

| Source | Resolution | Coverage | Terms | Use to us |
|---|---|---|---|---|
| Copernicus DEM GLO-30 | 30 m elevation | global | Copernicus, free | good - terrain, not imagery |
| USGS Landsat | 30 m | global | public domain | too coarse for low flying |
| USGS NAIP | 1 m | **USA only** | public domain | excellent for Black Rock, useless for Norfolk |
| OpenStreetMap | vector | global | ODbL - share-alike on derived databases | buildings, roads and land use to extrude into real scenery |
| Environment Agency LIDAR | **1 m elevation** | England, >95% | **NOT CONFIRMED** - records say "no public access constraints" but do not name a licence, and reference approval product AfA458 | would beat Google for Norfolk and Thetford if the licence permits it |

## What open data will never give you

Google's product is a **textured 3D mesh** - buildings and trees as real
geometry, photographed from the air. No open dataset is that. The open
world gives imagery draped over elevation, and buildings as footprints
you extrude yourself from OpenStreetMap.

For a UAS trainer that gap matters less than it would for a city
simulator: a student is learning to fly, to manage an envelope and to
operate a sensor, and 10 m imagery over real terrain with extruded
buildings is a long way past where this project is now.

## Recommendation, in order

1. **Ask EOX about the 2016 layer, and ask the Environment Agency about
   the LIDAR licence.** Two emails. The answers decide whether there is
   a free global option and a 1 m British one.
2. **If the answers are no, build the Copernicus Sentinel-2 path.** It
   is the only one with no restriction at the end, and its terms are
   already clear. Cost: a free account and a day or two of mosaicking.
3. **Keep Mapbox for now.** It works, the token is in place, and the
   imagery is already downloaded for all twelve areas. It is the wrong
   foundation for a sold product that must run offline, and the right
   thing for a demonstration next week.

## Sources

- Copernicus Sentinel data legal notice: https://ecds.ecmwf.int/licences/ec-sentinel
- EOX Sentinel-2 cloudless 2022: https://www.eox.at/2023/10/sentinel-2-cloudless-2022/
- EOX Sentinel-2 cloudless 2023: https://eox.at/2024/08/sentinel-2-cloudless-2023/
- OpenStreetMap wiki on Sentinel-2: https://wiki.openstreetmap.org/wiki/Sentinel-2
- Environment Agency LIDAR composite DTM 1m: https://www.data.gov.uk/dataset/lidar-composite-dtm-2020-1m
