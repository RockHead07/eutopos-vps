from dataclasses import asdict, dataclass
from typing import Literal

MIN_TEST_PHOTOS = 5
MIN_ACCEPT_PERCENT = 70


@dataclass(frozen=True)
class Reason:
    code: str
    message: str


@dataclass(frozen=True)
class Verdict:
    decision: Literal["publish", "hold", "reject"]
    reasons: tuple[Reason, ...]
    queries: int
    accepted: int


def evaluate(summary: dict) -> Verdict:
    inspect = summary.get("inspect") or {}
    queries = inspect.get("queries", 0)
    accepted = inspect.get("accepted", 0)
    parts = len(inspect.get("parts") or [])
    reasons = []
    if parts > 1:
        reasons.append(Reason("map_fragmented", f"The map has {parts} disconnected parts"))
    low_acceptance = queries >= MIN_TEST_PHOTOS and accepted * 100 < queries * MIN_ACCEPT_PERCENT
    if queries == 0:
        reasons.append(Reason("no_test_photos", "No test photos were provided"))
    elif queries < MIN_TEST_PHOTOS:
        reasons.append(
            Reason(
                "too_few_test_photos",
                f"Only {queries} test photos; at least {MIN_TEST_PHOTOS} are required",
            )
        )
    elif low_acceptance:
        reasons.append(
            Reason(
                "low_acceptance",
                f"{accepted} of {queries} test photos were accepted; "
                f"at least {MIN_ACCEPT_PERCENT}% are required",
            )
        )
    decision = "reject" if parts > 1 or low_acceptance else "hold" if reasons else "publish"
    return Verdict(decision, tuple(reasons), queries, accepted)


def as_dict(v: Verdict) -> dict:
    return {
        "decision": v.decision,
        "reasons": [asdict(reason) for reason in v.reasons],
        "queries": v.queries,
        "accepted": v.accepted,
    }


def reject_text(v: Verdict) -> str:
    return "Rejected by the test-photo gate: " + "; ".join(reason.message for reason in v.reasons)
