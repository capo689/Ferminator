# Archived: proximity / "near Bend" location search

**Parked 2026-07-29 by Adam's decision.** Stage 1 of the funnel became
remote-only, which removes the need for city-name resolution and distance math.
Nothing here is wired into the running system. Restore from this directory if
local-area search comes back.

Excluded from lint and test collection. Do not import from here.

---

## Why this work existed

Gateway 1 decided **US vs not-US** before any remote or proximity logic ran. It
resolved a job's location label by looking the place up in a bundled GeoNames US
postal dataset. If the label did not resolve, the job was rejected as foreign.

## The defect

`data/geography` maps **ZIP to USPS preferred place name**, 41,490 rows and
29,547 city/state keys. It is a postal-routing file, not a gazetteer of US place
names. Common labels are simply absent, so they resolved to `None` and the job
was thrown out as non-US:

- `Foster City, CA`
- `Superior, CO`
- `Brooklyn, OH`
- `Turnersville, NJ`

## Measured scope

Against the corpus as of 2026-07-29:

| measure | count |
|---|---:|
| total geography rejections | 34,016 |
| carrying a US state code | 759 |
| ...with no foreign signal | 731 |
| of those 731: hybrid or on-site (correctly rejected anyway) | 108 |
| **of those 731: remote or near Bend (genuinely lost)** | **86** |
| **all rejections that were remote or near Bend** | **4,081** |

The headline lesson: the state-code fix was worth only 86 jobs. The real loss was
**4,081 remote-or-local jobs rejected as "not US"**, and only 86 of those were the
state-code case. The rest sat in strata never examined:

| stratum | count |
|---|---:|
| bare_token | 10,229 |
| multi_or_city_label | 6,406 |
| unparseable_placeholder | 6,102 |
| remote_unqualified | 1,357 |
| remote_but_foreign | 1,172 |

## The fix that was designed but never built

Not "make city names resolve." That chases cities Adam would never work in. The
correct shape was:

1. **A remote job must never be rejected on the strength of a city label.** A job
   with `workplace_type = remote` and label `Foster City, CA` was rejected because
   the fallback demanded the label name no place at all. Backwards: the provider
   already said remote.
2. **US-ness only needs deciding when the job is not remote**, and then only to
   check reachability, which is distance math rather than name lookup.
3. **The ZIP dataset should do distance, not identity.** It is good at coordinates
   for ZIPs it has and bad at "is this a US place," which is what was wrongly
   built on top of it.

Secondary fix, if this is ever revived: treat `City, ST` with a valid US state
code as US without requiring dataset presence, handling collisions such as
`Chennai, TN`, `Böblingen, DE`, and `Bengaluru, IN`.

## Artifacts

- `sample_geography_rejections.py` — stratified sampler across 8 strata. Emits
  XML-tagged Markdown with `<resolver_input>` (raw label, country_code,
  workplace_type), `<posting_says_about_location>`, and blank `<verdict>` /
  `<note>` fields for labelling.
- An 86-record labelled corpus was generated and sent to Adam for labelling. It
  was never returned, so no CI gate was ever built on it.

## What stayed live

`src/ferminator/geography.py` remains in the running system. Remote-only search
still uses `is_remote_job()`. `lookup_zip()`, `coordinates_for_label()` and
`distance_miles()` are only reachable through the location-mode filter, which is
being removed from Discover; they are dead weight but harmless, and they are what
this work would need if proximity search returns.
