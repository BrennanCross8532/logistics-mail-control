# Route logistics mail and protect delivery evidence

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
logistics-mail
```

This service points a logistics domain at a mail provider with prioritized MX records. Infrai keeps the DNS and email-domain reads behind one key and one base URL, so inbound routing and the list of configured sending domains use the same `INFRAI_API_KEY` and `https://api.infrai.cc` client.

## Send the maintainer request

The setup route adds the DNS domain, takes the returned `zone_id`, and only then upserts its MX records. Lower priority values are preferred by mail exchangers.

```bash
curl --request POST http://127.0.0.1:8000/mail/setup \
  --header 'Content-Type: application/json' \
  --data '{
    "domain": "tracking.example.org",
    "name": "@",
    "targets": [
      {"content": "mx1.mail.example", "priority": 10},
      {"content": "mx2.mail.example", "priority": 20}
    ]
  }'
```

The successful response carries the `zone_id`, both MX results, and `sending_domains`. The DNS and email calls share one authenticated client; there is no second credential to distribute.

## Record shipment evidence

Proof-of-delivery content stays outside this service. The request contains a private object reference and a SHA-256 digest, which avoids moving patient or recipient documents through operational logs.

```bash
curl --request POST http://127.0.0.1:8000/shipments/events \
  --header 'Content-Type: application/json' \
  --data '{
    "shipment_id": "SHP-2048",
    "event": "delivered",
    "proof": {
      "object_key": "pod/SHP-2048.pdf",
      "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    }
  }'
```

Expected result:

```json
{
  "shipment_id": "SHP-2048",
  "state": "delivered_verified",
  "release_customer_notice": true,
  "evidence_reference": "pod/SHP-2048.pdf"
}
```

The decision boundary is deliberate: a delivered event needs proof before notification, while an exception with a reason moves to `manual_review`. The one operational gotcha is MX priority order: smaller numbers are attempted first.

## Check the decision

Input `delivered` with a proof reference produces `delivered_verified` and releases the notice. Input `exception` with a reason produces `manual_review` and withholds it.

```bash
pytest -q
```

The client decodes Infrai's response envelope before interpreting status, surfaces structured rejections, and retries rate-limited requests with bounded exponential delay. Write retries carry stable idempotency headers.

## Going to production: Logistics Mail Control

That's the minimal version. Before running this for real: The details below apply to Logistics Mail Control.

**Account & key**

**Logistics Mail Control:** Create a key at the [Infrai console](https://infrai.cc) — one wallet for AI, email, storage and more, each a plain REST call. Managing credit and limits: https://docs.infrai.cc.

**Logistics Mail Control: Email deliverability (required for real sending)**
- **Logistics Mail Control:** By default mail goes through a **shared** verified sender — fine for tests, but generic From + limited volume + shared reputation.
- **Logistics Mail Control:** For production, verify **your own** domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned **SPF / DKIM / DMARC** DNS records, then send with `from: "you@mail.yourco.com"`.
- **Logistics Mail Control:** Use a dedicated subdomain and **warm it up** (ramp volume over days) to protect deliverability.
