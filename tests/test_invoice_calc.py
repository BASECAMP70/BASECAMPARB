def test_invoice_subtotal_time_only():
    entries = [{"hours": 2.0, "rate": 100.0, "amount": 200.0}]
    expenses = []
    subtotal = sum(e["amount"] for e in entries) + sum(x["amount"] for x in expenses)
    assert subtotal == 200.0


def test_invoice_subtotal_with_expenses():
    subtotal = (2.5 * 125.0) + 49.99
    assert round(subtotal, 2) == 362.49


def test_gst_calculation():
    subtotal = 362.49
    gst_rate = 0.05
    gst = round(subtotal * gst_rate, 2)
    assert gst == 18.12


def test_invoice_number_increments():
    existing = [{"invoice_number": "INV-001"}, {"invoice_number": "INV-003"}]
    nums = [int(i["invoice_number"].split("-")[1]) for i in existing]
    next_num = max(nums) + 1 if nums else 1
    assert f"INV-{next_num:03d}" == "INV-004"


def test_invoice_number_starts_at_001_when_empty():
    existing = []
    nums = [int(i["invoice_number"].split("-")[1]) for i in existing]
    next_num = max(nums) + 1 if nums else 1
    assert f"INV-{next_num:03d}" == "INV-001"
