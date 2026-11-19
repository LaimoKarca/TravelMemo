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

## Footprint drafts

The trip-specific assistant creates pending drafts from text. It is independent of Conversation and does not write events until explicit confirmation.
Base path: `/trips/{trip_id}/footprint-drafts`. The usual session, CSRF and owner checks apply; foreign trip or draft IDs return404.

| Method and path | Body | Result |
| --- | --- | --- |
| `POST /` | `{record_date,text}` | 201 Draft |
| `GET /` | — | `{items:[Draft]}` containing the latest active draft, or an empty list |
| `GET /{draft_id}` | — | Draft |
| `PATCH /{draft_id}` | `{version,record_date?,text?,items?}` | Updated Draft |
| `POST /{draft_id}/generate` | `{version,request_id}` | 202 Draft; poll the draft for progress |
| `POST /{draft_id}/commit` | `{version,trip_version,request_id}` | `{events,trip_version,draft}` |
| `DELETE /{draft_id}?version=N` | — | 204; discard the draft |

`request_id` is a UUID. Draft has `id`, `trip_id`, `version`, `status`, `record_date`, `text`, `items`, `issues`,
`trip_version`, `error`, `request_id` and timestamps. Status is `editing`, `queued`, `running`, `ready`, `failed` or `committed`.
`issues` maps item IDs to missing or invalid field messages. It helps editing and does not replace server validation at commit.

Items contain `id`, `selected`, `place_name`, `date`, `time`, `city`, `address`, `category` and `notes`; item array order is the preview order.
Place name, date and time may be null while drafting. Selected items must satisfy the regular Event creation rules before commit.
Record date is required within the trip bounds, text is limited to10,000 characters, and generated items are limited to20.
An empty description can be saved while editing, but generation requires nonblank text. Unselected incomplete items do not block committing the selected valid items.
Unspecified dates use record date; relative dates use it as the anchor in the trip timezone. Unknown time stays null and unclassified items use `其他`.

Generation saves its request and processing state, then runs outside the browser connection. One owner has at most one active assistant worker;
the default is two assistant workers overall, adjustable by server configuration. Queued and interrupted running work can resume after startup; failed generation preserves previous items and input.
A manual retry may call the external model again. Discard removes the draft; a late generation result cannot restore it.

Commit validates the selected items, draft version and current Trip version. Conflicts return409 and retain the draft for review.
The selected events, new Places, Categories, NEXT links and commit result are saved in one transaction; the Trip version advances once.
Existing same-day events retain their order and new same-day events append in preview order. A repeated confirmation of a committed draft returns its original result,
even when the confirmation response was lost; it does not create a second set of events. No existing events are changed by this assistant.
