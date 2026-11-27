"""Materialize a portable, owner-scoped Traditional Chinese retrieval benchmark."""

from __future__ import annotations

import argparse
import json
import random
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from experiments.fuzzy_scenes import CIRCUMSTANCES, SCENES

CITIES = (
    "臺中", "臺南", "宜蘭", "花蓮", "基隆", "新竹", "彰化", "屏東", "嘉義", "苗栗",
    "高雄", "臺東", "南投", "新北", "澎湖", "金門",
)
KINDS = tuple(SCENES)
CATEGORIES = ("semantic", "time_place", "relational")
VARIANTS = ("exact", "colloquial", "no_name", "weak")
BOUNDARIES = ("multi", "clarify", "missing")

# Stops are sequenced for two days: arrivals, morning visits, meals, afternoon visits and lodging.
ROUTES = (
    (0, 1, 2, 3, 4, 8, 6, 10, 7, 9, 5, 0),
    (0, 6, 7, 10, 3, 8, 1, 4, 2, 9, 11, 0),
    (0, 4, 7, 3, 10, 8, 11, 1, 2, 6, 9, 0),
    (0, 5, 7, 6, 1, 8, 4, 10, 2, 3, 9, 0),
    (0, 10, 2, 6, 9, 8, 5, 4, 7, 3, 1, 0),
    (0, 11, 7, 3, 5, 8, 6, 1, 2, 10, 9, 0),
    (0, 4, 7, 5, 9, 8, 1, 10, 2, 3, 6, 0),
    (0, 6, 2, 1, 10, 8, 11, 4, 7, 3, 9, 0),
)

STOP_TIMES = (
    "09:05", "10:10", "11:50", "13:45", "16:00", "20:25",
    "08:55", "10:20", "12:10", "14:05", "16:10", "18:15",
)
TITLES = ("站", "宮", "鍋坊", "咖啡室", "步徑", "市集", "展室", "食堂", "旅宿", "菓子舖", "書屋", "廣場")
VENUE_STEMS = (
    "霽禾", "岫青", "棠瀾", "拂石", "澄巷", "晴槐", "瀨岸", "折溪", "初燈", "棲弦",
    "帆集", "蘆垣", "欖影", "迴風", "橋棉", "雨硯", "映浦", "新棰", "晚楝", "白鶴",
    "雲箔", "野沚", "松磚", "午杉", "蘊痕", "斜井", "和礫", "栗沙", "溪帽", "水桐",
    "琉堤", "沿荷", "鷺磴", "鳶瓦", "烏正", "梧畔", "歸舟", "折岬", "川角", "北蘊",
)
MISSING_ACTIVITIES = (
    "跳傘", "搭熱氣球", "攀冰", "夜間水肺潛水", "開帆船出海", "跆拳道",
    "雕玻璃", "騎駱駝", "高空彈跳", "滑翔翼", "室內射箭", "搭私人直升機",
)


def _normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def _observations(path: Path | None) -> dict[str, tuple[tuple[str, ...], ...]]:
    if path is None:
        return SCENES
    additions = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(additions, dict) or set(additions) - set(KINDS):
        raise ValueError("Scene file must map supported categories to observation/cue triples")
    catalog = {}
    for category, curated in SCENES.items():
        extra = additions.get(category, [])
        if not isinstance(extra, list) or any(
            not isinstance(row, list)
            or len(row) != 3
            or any(not isinstance(value, str) or not value.strip() or len(value) > 160 for value in row)
            for row in extra
        ):
            raise ValueError(f"Invalid scene for category {category}")
        # Interleave observations so even relatively uncommon categories can use both sources.
        combined = []
        for index in range(max(len(curated), len(extra))):
            if index < len(curated):
                combined.append(curated[index])
            if index < len(extra):
                combined.append(tuple(value.strip() for value in extra[index]))
        catalog[category] = tuple(combined)
    return catalog


def _build_travel(
    traveler: int, scenes: dict[str, tuple[tuple[str, ...], ...]]
) -> tuple[list[dict], list[dict]]:
    owner = f"fictional-{traveler + 1:02d}"
    first_day = date(2025 + traveler % 2, 1 + traveler % 3, 3 + traveler // 3)
    trips, events = [], []
    occurrences: Counter[str] = Counter()
    for trip_index in range(8):
        city = CITIES[(traveler * 3 + (trip_index // 2) * 5) % len(CITIES)]
        city_index = CITIES.index(city)
        trip_id = f"{owner}-trip-{trip_index + 1:02d}"
        start = first_day + timedelta(days=24 * trip_index + (traveler * trip_index) % 7)
        end = start + timedelta(days=1)
        route = ROUTES[(trip_index + traveler) % len(ROUTES)]
        trips.append(
            {
                "id": trip_id, "owner_id": owner, "name": f"{city}短旅行・{start.month}月",
                "start_date": start.isoformat(), "end_date": end.isoformat(), "timezone": "Asia/Taipei",
                "description": f"留作回憶練習的{city}兩日行程。", "version": 1,
            }
        )
        for position, kind_index in enumerate(route):
            kind = KINDS[kind_index]
            used = occurrences[kind]
            occurrences[kind] += 1
            observation_index = ((traveler + kind_index) * 3 + used) % len(scenes[kind])
            circumstance_index = (traveler + kind_index * 2 + used // len(scenes[kind])) % len(CIRCUMSTANCES)
            seen, cue, weak = scenes[kind][observation_index]
            detail, detail_cue, detail_weak = CIRCUMSTANCES[circumstance_index]
            # Pair trips share a venue for each category. Transit uses separate arrival/departure venues.
            venue_index = (city_index * 7 + kind_index * 3 + traveler // 6 + int(position == 11)) % len(VENUE_STEMS)
            short_name = VENUE_STEMS[venue_index] + TITLES[kind_index]
            venue = city + short_name
            event_day = start + timedelta(days=position // 6)
            events.append(
                {
                    "id": f"{trip_id}-stop-{position + 1:02d}", "owner_id": owner, "trip_id": trip_id,
                    "place_id": f"{owner}-{city_index}-{kind_index}-{venue_index}",
                    "place_name": venue, "aliases": [short_name], "category": kind, "city": city,
                    "date": event_day.isoformat(), "time": STOP_TIMES[position], "position": position,
                    "address": "", "notes": f"{seen}。{detail}。", "record_scope": "trip",
                    "timezone": "Asia/Taipei", "version": 1,
                    "facts": {"observation": seen, "cue": cue, "weak": weak, "detail": detail,
                              "detail_cue": detail_cue, "detail_weak": detail_weak},
                }
            )
    return trips, events


def _distribution(traveler: int) -> dict[str, int]:
    # Rotating the short category gives exactly 200 items/category across thirty test owners.
    return {kind: 6 if offset == traveler % 3 else 7 for offset, kind in enumerate(CATEGORIES)}


def _event_hint(event: dict) -> dict:
    return {
        "city": event["city"], "category": event["category"], "date": event["date"], "time": event["time"],
        "clues": [event["facts"]["cue"], event["facts"]["detail_cue"]],
        "weak_clue": event["facts"]["weak"],
    }


def _known_text(event: dict, kind: str, variant: str, anchor: dict | None, direction: str | None) -> str:
    city, category, day, time = (event[k] for k in ("city", "category", "date", "time"))
    date_words = f"{int(day[5:7])}月{int(day[8:10])}日"
    facts = event["facts"]
    wording = (int(day[8:10]) + event["position"]) % 3
    if anchor is not None:
        anchor_facts = anchor["facts"]
        anchor_name, anchor_date = anchor["place_name"], anchor["date"]
        arrow = "下一站" if direction == "next" else "上一站"
        if variant == "exact":
            return f"在{anchor_name}{arrow}是哪裡？當時是{anchor_date}，紀錄分類是{category}。"
        if variant == "colloquial":
            return (
                f"我想不起來，在{anchor_name}{arrow}到底是哪裡？那次是{anchor_date}。",
                f"{anchor_date}那趟有到{anchor_name}，當時的{arrow}你記得嗎？",
                f"翻一下{anchor_date}那天好嗎，{anchor_name}{arrow}我去了哪？",
            )[wording]
        if variant == "no_name":
            return (
                f"那次在{city}，{anchor_facts['cue']}。我還記得{anchor_facts['detail_cue']}，{arrow}到了哪裡？",
                f"幫我想一下{city}那趟。好像{anchor_facts['cue']}，也有{anchor_facts['detail_cue']}。{arrow}呢？",
                f"在{city}{anchor_facts['cue']}的那站，{arrow}去哪了？有個細節是{anchor_facts['detail_cue']}。",
            )[wording]
        movement = "走完就去哪" if direction == "next" else "還沒到那裡時，我前一個地方在哪"
        return (
            f"那次{anchor_facts['weak']}，{anchor_facts['detail_weak']}……{movement}？",
            f"我只想到{anchor_facts['weak']}。好像{anchor_facts['detail_weak']}吧？記得{movement}嗎？",
            f"欸，有一站{anchor_facts['weak']}，還有就是{anchor_facts['detail_weak']}。然後，{movement}？",
        )[wording]
    if kind == "time_place":
        if variant == "exact":
            return f"{day}在{city}，{time}到訪的{category}地點是哪裡？"
        if variant == "colloquial":
            return (
                f"{date_words}我在{city}，{time}好像有去一個跟{category}有關的地方，是哪一處？",
                f"幫我看{city}那本，{date_words}的{time}寫了哪個{category}地點啊？",
                f"有筆{category}的足跡我找不到，好像是{city}的{date_words}，大概{time}。",
            )[wording]
        if variant == "no_name":
            return (
                f"{date_words}左右我在{city}，好像{facts['cue']}，那天去了哪裡？",
                f"我記得{facts['cue']}。有可能是{date_words}在{city}，能查是在哪裡嗎？",
                f"想找{city}那次{facts['cue']}的紀錄，應該是{date_words}附近。",
            )[wording]
        month = int(day[5:7])
        return (
            f"差不多{month}月，在{city}有一次{facts['weak']}，在哪裡啊？",
            f"我在{city}有去過那個地方，就是{facts['weak']}。月份好像{month}月。",
            f"應該{month}月吧，去{city}的時候{facts['weak']}……是在哪一筆？",
        )[wording]
    if variant == "exact":
        return f"{city}的{category}地點，記錄說{facts['observation']}。是哪一筆？"
    if variant == "colloquial":
        return (
            f"我之前在{city}記了個{category}，{facts['cue']}那家是叫什麼？",
            f"{city}那個{category}我記得{facts['cue']}，我在哪裡記的啊？",
            f"可以幫我找一下{city}的{category}嗎？我有印象{facts['cue']}。",
        )[wording]
    if variant == "no_name":
        return (
            f"我好像有在{city}{facts['cue']}，還記得{facts['detail_cue']}。是哪裡？",
            f"我想找{city}那一筆。有印象{facts['cue']}，也記得{facts['detail_cue']}。",
            f"{facts['cue']}，那次{facts['detail_cue']}。在{city}哪裡來著？",
        )[wording]
    return (
        f"想不起來……有一次{facts['weak']}，那是在{city}哪裡？",
        f"有印象{facts['weak']}。我好像也記了{facts['detail_weak']}，你能找嗎？",
        f"在{city}有個地方，{facts['weak']}。是哪一處啊？",
    )[wording]


def _hard_negative(event: dict, events: list[dict], anchor: dict | None, direction: str | None) -> dict:
    if anchor:
        opposite = anchor["position"] - (1 if direction == "next" else -1)
        for candidate in events:
            if candidate["trip_id"] == anchor["trip_id"] and candidate["position"] == opposite:
                return candidate
    choices = [candidate for candidate in events if candidate["id"] != event["id"]]
    return min(
        choices,
        key=lambda candidate: (
            candidate["place_id"] != event["place_id"],
            candidate["category"] != event["category"],
            candidate["city"] != event["city"],
            abs((date.fromisoformat(candidate["date"]) - date.fromisoformat(event["date"])).days),
        ),
    )


def _row(owner: str, split: str, family: str, query_type: str, text: str, expected: str,
         relevant: list[str], **fields) -> dict:
    variant = fields.pop("variant", "boundary")
    return {
        "query_id": f"{family}-{variant}", "family_id": family, "user_id": owner, "split": split,
        "query_type": query_type, "variant": variant, "query_text": text, "expected": expected,
        "target_event_id": relevant[0] if expected == "unique" else None,
        "relevant_event_ids": relevant, "hard_negative_id": None, "anchor_event_id": None,
        "direction": None, **fields,
    }


def _queries_for_owner(traveler: int, split: str, events: list[dict]) -> list[dict]:
    rng = random.Random(8921 + traveler)
    owner = events[0]["owner_id"]
    budget = _distribution(traveler)
    by_trip = defaultdict(list)
    for event in events:
        by_trip[event["trip_id"]].append(event)
    nominations = events.copy()
    rng.shuffle(nominations)
    # A weak memory can distinguish these groups using the remembered observation alone
    # (with the regional qualifier for the time/place group).
    # Assign strict relation candidates first, because anchors must have two neighbors.
    used = set()
    used_anchors = set()
    known = []
    for kind in ("relational", "semantic", "time_place"):
        for index in range(budget[kind]):
            anchor, direction = None, None
            if kind == "relational":
                direction = "next" if (index + traveler) % 2 == 0 else "prev"
                step = 1 if direction == "next" else -1
                anchor = next(
                    event for event in nominations
                    if 1 <= event["position"] <= 10
                    and event["id"] not in used_anchors
                    and by_trip[event["trip_id"]][event["position"] + step]["id"] not in used
                    and sum(e["facts"]["weak"] == event["facts"]["weak"] for e in events) == 1
                )
                used_anchors.add(anchor["id"])
                target = by_trip[anchor["trip_id"]][anchor["position"] + step]
            else:
                target = next(
                    event for event in nominations
                    if event["id"] not in used
                    and sum(
                        candidate["facts"]["weak"] == event["facts"]["weak"]
                        and (kind == "semantic" or candidate["city"] == event["city"])
                        for candidate in events
                    ) == 1
                )
            used.add(target["id"])
            family = f"{owner}-{kind}-{index + 1:02d}"
            distractor = _hard_negative(target, events, anchor, direction)
            for variant in VARIANTS:
                # Name-free hints omit the target for relation questions, so no answer information leaks
                # into the question through an optional generation overlay.
                clue_source = anchor if anchor else target
                hint = _event_hint(clue_source)
                hint["direction"] = direction
                hint["target_category"] = target["category"] if anchor else None
                hint["protected_names"] = [
                    target["place_name"], *target["aliases"],
                    *([anchor["place_name"], *anchor["aliases"]] if anchor else []),
                ]
                known.append(
                    _row(
                        owner, split, family, kind, _known_text(target, kind, variant, anchor, direction),
                        "unique", [target["id"]], variant=variant, hard_negative_id=distractor["id"],
                        anchor_event_id=anchor["id"] if anchor else None, direction=direction,
                        generation_hint=hint,
                    )
                )

    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for event in events:
        grouped[(event["city"], event["category"])].append(event["id"])
    multi = [(key, values) for key, values in grouped.items() if len(values) > 1]
    rng.shuffle(multi)
    ambiguity_sources = [event for event in nominations if event["position"] % 6 <= 3]
    missing_choices = [(city, activity) for city in sorted({event["city"] for event in events})
                       for activity in MISSING_ACTIVITIES]
    rng.shuffle(missing_choices)
    boundary = []
    for kind, amount in zip(BOUNDARIES, budget.values(), strict=True):
        for index in range(amount):
            family = f"{owner}-{kind}-{index + 1:02d}"
            if kind == "multi":
                (city, category), event_ids = multi[index]
                boundary.append(
                    _row(owner, split, family, kind, f"我在{city}去過的{category}足跡，可以每次都列一下嗎？",
                         "multi", event_ids, generation_hint={"city": city, "category": category})
                )
            elif kind == "clarify":
                anchor = ambiguity_sources[index]
                stops = by_trip[anchor["trip_id"]]
                alternatives = [stops[anchor["position"] + step]["id"] for step in (1, 2)]
                text = (
                    f"在{anchor['city']}那次{anchor['facts']['cue']}之後，"
                    f"我還去哪裡？我只記得{anchor['facts']['detail_cue']}。"
                )
                boundary.append(
                    _row(owner, split, family, kind, text, "clarify", [],
                         anchor_event_id=anchor["id"], alternative_event_ids=alternatives,
                         generation_hint=_event_hint(anchor))
                )
            else:
                city, activity = missing_choices[index]
                boundary.append(
                    _row(owner, split, family, kind, f"我上回在{city}{activity}是在哪個地方？",
                         "no_evidence", [], generation_hint={"city": city, "unrecorded_activity": activity})
                )
    return known + boundary


def build_corpus(scenes_path: Path | None = None) -> dict:
    """Freeze independent owner partitions and all label-side evidence from structured records."""
    scenes = _observations(scenes_path)
    corpus: dict = {
        "name": "TravelMemo 繁中模糊回憶基準",
        "synthetic": True,
        "source": "curated plus model-generated observations" if scenes_path else "curated observations",
        "trips": [], "events": [], "queries": [],
    }
    for traveler in range(40):
        split = "pilot" if traveler < 5 else "dev" if traveler < 10 else "test"
        trips, events = _build_travel(traveler, scenes)
        corpus["trips"].extend(trips)
        corpus["events"].extend(events)
        corpus["queries"].extend(_queries_for_owner(traveler, split, events))
    corpus["counts"] = validate_corpus(corpus)
    return corpus


def validate_corpus(corpus: dict, *, require_official_size: bool = True) -> dict:
    """Verify corpus boundaries and evidence against records without consulting retrieval outputs."""
    if corpus.get("synthetic") is not True:
        raise ValueError("Only synthetic data are accepted")
    events = {event["id"]: event for event in corpus["events"]}
    trips = {trip["id"]: trip for trip in corpus["trips"]}
    if len(events) != len(corpus["events"]) or len(trips) != len(corpus["trips"]):
        raise ValueError("Duplicate event or trip ID")
    names_by_owner: dict[str, set[str]] = defaultdict(set)
    positions = set()
    for event in events.values():
        trip = trips.get(event["trip_id"])
        place = (event["trip_id"], event["position"])
        owner = event["owner_id"]
        if (
            not owner.startswith("fictional-") or not trip or trip["owner_id"] != owner
            or not trip["start_date"] <= event["date"] <= trip["end_date"]
            or place in positions
        ):
            raise ValueError(f"Invalid synthetic event: {event['id']}")
        positions.add(place)
        names_by_owner[owner].update(map(_normalize, [event["place_name"], *event.get("aliases", [])]))

    partitions = defaultdict(set)
    families = defaultdict(list)
    query_ids, seen_queries = set(), set()
    count_test: Counter[str] = Counter()
    count_known: Counter[str] = Counter()
    for query in corpus["queries"]:
        qid, owner = query["query_id"], query["user_id"]
        norm = _normalize(query["query_text"])
        key = (owner, norm)
        if qid in query_ids or not norm or key in seen_queries:
            raise ValueError(f"Duplicate or blank query: {qid}")
        query_ids.add(qid)
        seen_queries.add(key)
        partitions[owner].add(query["split"])
        families[query["family_id"]].append(query)
        if query["split"] == "test":
            count_test[query["query_type"]] += 1

        expected = query["expected"]
        targets = query["relevant_event_ids"]
        target = query["target_event_id"]
        hard_negative = query["hard_negative_id"]
        anchor = query["anchor_event_id"]
        alternatives = query.get("alternative_event_ids", [])
        for event_id in [*targets, *alternatives, target, hard_negative, anchor]:
            if event_id is not None and (event_id not in events or events[event_id]["owner_id"] != owner):
                raise ValueError(f"Unsupported or cross-owner evidence: {qid}")
        if expected == "unique":
            if targets != [target] or not target or not hard_negative or target == hard_negative:
                raise ValueError(f"Invalid unique label or hard negative: {qid}")
            if query["variant"] in {"no_name", "weak"} and any(
                name and name in norm for name in names_by_owner[owner]
            ):
                raise ValueError(f"Exact venue or alias leaked into name-free question: {qid}")
            direction = query["direction"]
            if query["query_type"] == "relational":
                if direction not in {"next", "prev"} or not anchor:
                    raise ValueError(f"Missing directed relation: {qid}")
                source, destination = events[anchor], events[target]
                step = 1 if direction == "next" else -1
                if source["trip_id"] != destination["trip_id"] or source["position"] + step != destination["position"]:
                    raise ValueError(f"Relation is not a true one-hop neighbor: {qid}")
            if query["split"] == "test":
                count_known[query["variant"]] += 1
        elif expected == "multi":
            hint = query["generation_hint"]
            if len(targets) < 2 or set(targets) != {
                event["id"] for event in events.values()
                if event["owner_id"] == owner and event["category"] == hint["category"] and event["city"] == hint["city"]
            }:
                raise ValueError(f"Incomplete answer set: {qid}")
        elif expected == "clarify":
            if targets or not anchor or len(alternatives) != 2:
                raise ValueError(f"Clarification requires two distinct interpretations: {qid}")
            event = events[anchor]
            for step, event_id in enumerate(alternatives, 1):
                alternative = events[event_id]
                if alternative["trip_id"] != event["trip_id"] or alternative["date"] != event["date"] or alternative["position"] != event["position"] + step:
                    raise ValueError(f"Invalid alternative interpretation: {qid}")
        elif expected == "no_evidence":
            hint = query["generation_hint"]
            if targets or any(hint["unrecorded_activity"] in event["notes"] for event in events.values()
                              if event["owner_id"] == owner):
                raise ValueError(f"Unsupported no-evidence label: {qid}")
        else:
            raise ValueError(f"Unknown expected response: {qid}")

    if any(len(splits) != 1 or not splits <= {"pilot", "dev", "test"} for splits in partitions.values()):
        raise ValueError("A synthetic owner appears in more than one partition")
    seen_targets = set()
    for family, rows in families.items():
        if rows[0]["expected"] == "unique":
            target = rows[0]["target_event_id"]
            if (
                sorted(row["variant"] for row in rows) != sorted(VARIANTS)
                or len({row["target_event_id"] for row in rows}) != 1 or target in seen_targets
                or len({row["user_id"] for row in rows}) != 1
            ):
                raise ValueError(f"Inconsistent variants or duplicate target family: {family}")
            seen_targets.add(target)
        elif len(rows) != 1:
            raise ValueError(f"Boundary query cannot share a family: {family}")
    counts = {
        "events": len(events), "trips": len(trips), "queries": len(query_ids),
        "owners_by_split": dict(Counter(next(iter(splits)) for splits in partitions.values())),
        "test_by_type": dict(count_test), "test_by_variant": dict(count_known),
    }
    if require_official_size and (
        len(trips) != 320 or len(events) != 3840 or len(query_ids) != 4000
        or counts["owners_by_split"] != {"pilot": 5, "dev": 5, "test": 30}
        or any(count_test[kind] != 800 for kind in CATEGORIES)
        or any(count_test[kind] != 200 for kind in BOUNDARIES)
        or any(count_known[variant] != 600 for variant in VARIANTS)
    ):
        raise ValueError(f"Official corpus counts do not match the protocol: {counts}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenes", type=Path, help="Optional Traditional Chinese observation triples")
    parser.add_argument("--output", type=Path, default=Path("data/closeout/fuzzy-corpus.json"))
    args = parser.parse_args()
    corpus = build_corpus(args.scenes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(corpus["counts"], ensure_ascii=True))


if __name__ == "__main__":
    main()
