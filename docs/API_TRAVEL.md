# 旅程與事件 API

Scope: authenticated private trip/event CRUD, explicit Place reuse, timeline and NEXT, optimistic versions. API prefix /api/v1, JSON errors {detail:string}. All writes require X-CSRF-Token and existing session; owner derived server-side. Cross-owner IDs 404. Validation422, version409.

Trip JSON: {id,name,start_date,end_date,timezone,description,version}. Dates YYYY-MM-DD required; timezone IANA or fixed UTC offset, default Asia/Taipei; name1..200, description max10000. start<=end. Versions start1, increment on every trip or contained event mutation.
The create form defaults the end date to the following day and adjusts an end date made too early by a changed start date. Same-day trips remain valid. API validation independently rejects start>end.
Event JSON: {id,trip_id,place_id,place_name,city,address,category,date,time,notes,position,version}. time HH:mm or null, date required in trip bounds, notes max20000; strings name1..200, city/category up to200, address1000. category required. Unknown time remains null. Each visit separate ID. Event versions start1, increment on edit only.
Place JSON: {id,name,city,address}; owner scoped, reused only by explicit id. If supplied place_id, use authoritative existing place fields. Without place_id create fresh Place, never merge names. On editing without place_id create a new Place rather than mutate one used by another event. Category nodes owner-scoped by normalized name.

Endpoints:
- GET /trips -> {items:Trip[]} sort start_date descending,id.
- POST /trips body name,start_date,end_date,timezone,description ->201 Trip.
- GET /trips/{id} -> {trip:Trip,events:Event[],next_edges:[{from_id,to_id}]}.
- PUT /trips/{id} body same fields + version -> Trip. Reject shrinking bounds excluding existing events.
- DELETE /trips/{id}?version=N ->204; delete own events/NEXT, retain reusable Places.
- GET /places -> {items:Place[]}.
- POST /trips/{id}/events body place_id?:str|null,place_name,city,address,category,date,time,notes ->201 Event.
- PUT /events/{id} same fields +version -> Event. Keep trip fixed.
- DELETE /events/{id}?version=N ->204.
- PUT /trips/{id}/event-order body {version,event_ids:[...]} -> same shape as trip detail. Must include exactly all IDs once, dates nondecreasing; within day arbitrary. No cross-date reorder allowed.

Create events: append after existing same-date events. Edit date: move to end of new date group; unchanged date preserves order. Unknown time never used for ordering; explicit order wins. All event mutations/reorder/delete and NEXT rebuild in one Neo4j transaction with trip node write lock then version validation. NEXT only adjacent same owner/trip, direction preserved, including cross-day, no cycle. Every transaction filters owner. Avoid using AuthRecord JSON for travel data: real Trip/Event/Place/Category nodes + User-OWNS-Trip-HAS_EVENT-Event, Event-AT-Place, Event-HAS_CATEGORY-Category, NEXT. No APOC required.

## Draft polishing

`POST /writing/polish` accepts `{text,kind}` where kind is `trip` or `event`, and returns `{text}`.
The draft must be nonblank and at most 10,000 characters. This authenticated, CSRF-protected operation uses the configured AI model and does not create or update a Trip or Event.
The frontend previews the result before applying it, keeps the original available for undo, and still uses the regular save endpoint to persist edits.
Invalid input returns422, rejected content400, concurrent requests429, and unavailable AI503. Existing draft text remains available when polishing fails.
