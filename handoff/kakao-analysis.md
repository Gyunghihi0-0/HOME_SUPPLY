# Kakao / actual-trade analysis

GitHub Actions reads `KAKAO_REST_API_KEY` from repository secrets. Kakao authentication is sent only in the request header; raw geocoding responses are not persisted. `MOLIT_SERVICE_KEY` continues to use detailed apartment transactions (15126468). Existing comparison policy is unchanged.

Only a unique exact parcel/road-address match can verify coordinates. Development-block names such as 구름산지구 A6블록 remain unresolved until an authoritative parcel address is available. A sales-center location must never be substituted.

Neighboring districts are discovered from nine coordinate samples covering the enclosing square. This is not a polygon-intersection proof. Published calculations using this discovery carry low confidence and an explicit coverage limitation. Radius filtering still uses actual apartment-to-target coordinates, not district centroids.

The notice collector has a separate 120-second subprocess budget. Its failure retains previous announcements and does not prevent price/trade analysis. The analysis has a 540-second budget. Remaining incomplete sources keep the workflow marked incomplete even when Pages successfully publishes useful partial results.

Only units with confirmed price, exclusive area, and disability allocation are geocoded. Each unique plausible comparison address is queried once per analysis batch. At most 500 locations are attempted with four workers; exceeding that cap withholds the estimate. A missing or ambiguous address never receives invented coordinates.

Backend verification includes exact-address rejection, header-only authentication, ambiguous/block-address rejection, and an end-to-end regression from geocoding through verified transactions to a negative price gap. Test transactions are only fixtures, never published as real results.

Frontend is an existing contract 1.0.0 consumer. Updating `docs/data/latest.json` and `locations.json` updates the displayed calculations without changing frontend-owned code. Closed announcements remain under the history view.
