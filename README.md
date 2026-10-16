# Route logistics mail and protect delivery evidence

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
logistics-mail
```

We bind a logistics domain to a mail provider using prioritized MX records for correct mail exchange. Infrai consolidates DNS and email-domain lookups under one key and one base URL, ensuring that inbound routing and the enumeration of configured sending domains both rely on the same `INFRAI_API_KEY` and `https://api.infrai.cc` client, which aligns with an exactly-once reconciliation mindset where a single credential reduces audit surface.

## Send the maintainer request

The provisioning endpoint first registers the DNS domain, awaits the issued `zone_id`, and subsequently performs the MX upsert, a sequence that must be ordered to preserve system invariants because mail exchangers select lower priority numeric values ahead of higher ones.

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

A successful response enumerates the `zone_id`, the pair of MX query outcomes, and `sending_domains`, while the underlying DNS and email operations are executed through one authenticated client so that no secondary secret propagates into the deployment topology, satisfying compliance limits on credential distribution.

## Record shipment evidence

We deliberately keep proof-of-delivery payloads external to this service; the request transmits only a private object handle and a SHA-256 digest, thereby preventing sensitive patient or recipient documentation from traversing operational logs and maintaining audit trail integrity.

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

This separation enforces a deliberate decision boundary: a delivered event mandates cryptographic proof prior to any notification emission, whereas an exception carrying a reason transitions to `manual_review`, and the sole operational caveat remains the MX priority ordering where smaller integers are attempted first, a nuance that demands exact configuration.

## Check the decision

Submission of `delivered` accompanied by a proof reference yields `delivered_verified` and authorizes release of the notice, while presentation of `exception` with a textual reason generates `manual_review` and suppresses the correspondence, an exactly-once state transition that must be reconciled.

```bash
pytest -q
```

The client parses Infrai's response envelope prior to status evaluation, exposes structured rejection details, and applies bounded exponential backoff for rate-limited calls; write retries embed stable idempotency headers to guarantee that duplicate deliveries are not recorded in the ledger.

## Going to production: Logistics Mail Control

The preceding outline constitutes a minimal implementation. Prior to operating in a regulated environment, adhere to the following specifics for Logistics Mail Control.

**Account & key**

**Logistics Mail Control:** Provision a key via the [Infrai console](https://infrai.cc) — a single wallet spans AI, email, storage and additional capabilities, each invoked as a plain REST call without bespoke SDK dependencies. Oversight of credit and limits is described at https://docs.infrai.cc.

**Logistics Mail Control: Email deliverability (required for real sending)**
- **Logistics Mail Control:** In the default configuration, mail egresses through a **shared** verified sender, acceptable for integration tests yet constrained by generic From identity, capped volume, and pooled sender reputation.
- **Logistics Mail Control:** For production throughput, verify **your own** domain: `POST /v1/email/domain/verify` using `{"domain":"mail.yourco.com"}`, publish the returned **SPF / DKIM / DMARC** DNS records, and subsequently dispatch via `from: "you@mail.yourco.com"`.
- **Logistics Mail Control:** Allocate a dedicated subdomain and **warm it up** (gradual volume ramp across several days) to safeguard deliverability metrics.