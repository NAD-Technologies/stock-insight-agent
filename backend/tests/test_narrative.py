from agent.narrative import ungrounded_numbers

PAYLOAD = {"rec": {"score": 72.4, "pe": 28.31}, "mc": 3_100_000_000_000, "upside": 12.46}


def test_grounded_numbers_pass():
    t = "Composite 72.4 with P/E 28.3, upside 12.5%, market cap $3.1 trillion."
    assert ungrounded_numbers(t, PAYLOAD) == []


def test_fabricated_number_flagged():
    assert "91.7" in ungrounded_numbers("Revenue grew 91.7% last year", PAYLOAD)
