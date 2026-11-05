def test_home_is_the_sales_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Стоимость" in response.text
    assert 'href="/demo"' in response.text


def test_offer_lists_both_payment_models(client):
    response = client.get("/v1/offer")
    assert response.status_code == 200
    body = response.json()
    tiers = body["subscription"]["tiers"]
    assert [tier["tryons"] for tier in tiers] == [300, 1000, 3000]
    assert tiers[0]["price_rub"] == 9900
    assert body["subscription"]["extra_tryon_rub"] == 40
    assert body["commission"]["percent"] == 8
    assert body["commission"]["monthly_rub"] == 0


def test_shop_can_leave_a_lead(client):
    response = client.post(
        "/v1/leads",
        json={
            "shop": "Ателье Север",
            "contact": "shop@example.com",
            "plan": "commission",
            "note": "Хотим процент с покупки",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "accepted"


def test_lead_rejects_unknown_plan(client):
    response = client.post(
        "/v1/leads",
        json={"shop": "Ателье", "contact": "shop@example.com", "plan": "free"},
    )
    assert response.status_code == 422
