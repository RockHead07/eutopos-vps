import json

import pytest

from server import gate


def summary(queries, accepted, parts=1):
    return {"inspect": {"queries": queries, "accepted": accepted, "parts": [{}] * parts}}


def test_publish_when_ratio_met():
    v = gate.evaluate(summary(10, 7))
    assert (v.decision, v.reasons, v.queries, v.accepted) == ("publish", (), 10, 7)


@pytest.mark.parametrize(
    "data, decision, codes",
    [
        (summary(10, 6), "reject", ["low_acceptance"]),
        (summary(10, 10, 2), "reject", ["map_fragmented"]),
        (summary(0, 0), "hold", ["no_test_photos"]),
        (summary(4, 4), "hold", ["too_few_test_photos"]),
        ({}, "hold", ["no_test_photos"]),
        (summary(4, 1, 2), "reject", ["map_fragmented", "too_few_test_photos"]),
    ],
    ids=["low-ratio", "fragmented", "no-photos", "too-few", "missing-inspect", "reject-outranks"],
)
def test_gate_decisions(data, decision, codes):
    v = gate.evaluate(data)
    assert v.decision == decision
    assert [reason.code for reason in v.reasons] == codes


def test_as_dict_is_json_safe():
    v = gate.evaluate(summary(10, 6))
    result = json.loads(json.dumps(gate.as_dict(v)))
    assert result == {
        "decision": "reject",
        "reasons": [{"code": v.reasons[0].code, "message": v.reasons[0].message}],
        "queries": 10,
        "accepted": 6,
    }


def test_reject_text_lists_messages():
    v = gate.evaluate(summary(4, 1, 2))
    result = gate.reject_text(v)
    assert result.startswith("Rejected by the test-photo gate: ")
    assert all(reason.message in result for reason in v.reasons)
