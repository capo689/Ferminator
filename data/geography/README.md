# United States postal geography

The packaged `src/ferminator/data/geonames-us-postal.zip` file is the United
States postal-code export from
[GeoNames](https://download.geonames.org/export/zip/US.zip), retrieved
2026-07-25. GeoNames data is licensed under
[Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).

Ferminator reads this compressed file locally to resolve ZIP codes and common
`City, ST` job locations. It never sends a user's ZIP code to a third party.
Postal coordinates are representative points, so mileage is an estimate rather
than a street-routing distance.
