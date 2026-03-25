# O2C Data System — Build Specification

> Schema · Graph Model · Query Planner  
> Version 1.0 — 2025  
> _Input document for automated build steps. Feed directly into the pipeline._

---

## Table of Contents

1. [Relational Schema](#1-relational-schema)
2. [Graph Model](#2-graph-model)
3. [Query Planner](#3-query-planner)
4. [Ingestion Checklist](#4-ingestion-checklist)

---

## 1. Relational Schema

19 tables across three layers: **Master Data**, **Transactional**, and **Financial**. All transactions use company code `ABCD` and currency `INR`.

### 1.1 Table Catalogue

| Table name | Layer | Primary key | Key fields |
|---|---|---|---|
| `business_partners` | Master | `businessPartner` | fullName, category, isBlocked, isMarkedForArchiving |
| `business_partner_addresses` | Master | `(businessPartner, addressId)` | cityName, region, country, postalCode, validityStartDate |
| `customer_company_assignments` | Master | `(customer, companyCode)` | reconciliationAccount, paymentTerms, deletionIndicator |
| `customer_sales_area_assignments` | Master | `(customer, salesOrg, distCh, division)` | currency, incoterms, shippingCondition, paymentTerms |
| `products` | Master | `product` | productType, productGroup, division, isMarkedForDeletion |
| `product_descriptions` | Master | `(product, language)` | productDescription |
| `plants` | Master | `plant` | plantName, salesOrganization, valuationArea |
| `product_plants` | Master | `(product, plant)` | mrpType, profitCenter, countryOfOrigin |
| `product_storage_locations` | Master | `(product, plant, storageLocation)` | physicalInventoryBlockInd, dateOfLastPostedCnt |
| `sales_order_headers` | Transaction | `salesOrder` | soldToParty (FK), totalNetAmount, status, creationDate |
| `sales_order_items` | Transaction | `(salesOrder, salesOrderItem)` | material (FK), netAmount, quantity, productionPlant (FK) |
| `sales_order_schedule_lines` | Transaction | `(salesOrder, item, scheduleLine)` | confirmedDeliveryDate, confdOrderQty |
| `outbound_delivery_headers` | Transaction | `deliveryDocument` | pickingStatus, goodsMovementStatus, shippingPoint |
| `outbound_delivery_items` | Transaction | `(deliveryDocument, item)` | referenceSdDocument (FK→SO), plant (FK), batch |
| `billing_document_headers` | Transaction | `billingDocument` | soldToParty (FK), accountingDocument (FK), isCancelled |
| `billing_document_items` | Transaction | `(billingDocument, item)` | referenceSdDocument (FK→SO), material (FK), netAmount |
| `billing_document_cancellations` | Transaction | `billingDocument` | Subset of billing_headers where isCancelled = true |
| `journal_entry_items_ar` | Financial | `(accountingDocument, item)` | customer (FK), referenceDocument (FK→billing), clearingDoc |
| `payments_accounts_receivable` | Financial | `(accountingDocument, item)` | customer (FK), clearingAccountingDocument, postingDate |

### 1.2 Foreign Key Map

| Child table.field | → Parent table | Join field | Notes |
|---|---|---|---|
| `business_partner_addresses.businessPartner` | `business_partners` | `businessPartner` | 1:N — one partner, many addresses |
| `customer_company_assignments.customer` | `business_partners` | `businessPartner` | 1:N — one customer, many company codes |
| `customer_sales_area_assignments.customer` | `business_partners` | `businessPartner` | 1:N — one customer, many sales areas |
| `product_descriptions.product` | `products` | `product` | 1:N — one product, many languages |
| `product_plants.product` | `products` | `product` | N:M junction — product ↔ plant |
| `product_plants.plant` | `plants` | `plant` | N:M junction |
| `product_storage_locations.(product,plant)` | `product_plants` | `(product, plant)` | Composite FK |
| `sales_order_headers.soldToParty` | `business_partners` | `businessPartner` | N:1 — many orders per customer |
| `sales_order_items.salesOrder` | `sales_order_headers` | `salesOrder` | 1:N |
| `sales_order_items.material` | `products` | `product` | N:1 |
| `sales_order_items.productionPlant` | `plants` | `plant` | N:1 |
| `sales_order_schedule_lines.(salesOrder,item)` | `sales_order_items` | `(salesOrder, item)` | 1:N — one item, many schedule lines |
| `outbound_delivery_items.deliveryDocument` | `outbound_delivery_headers` | `deliveryDocument` | 1:N |
| `outbound_delivery_items.referenceSdDocument` | `sales_order_items` | `salesOrder + item` | ⚠ Indirect — no header-level FK |
| `outbound_delivery_items.plant` | `plants` | `plant` | N:1 |
| `billing_document_headers.soldToParty` | `business_partners` | `businessPartner` | N:1 |
| `billing_document_headers.accountingDocument` | `journal_entry_items_ar` | `accountingDocument` | 1:1 expected, 1:N on reversal |
| `billing_document_items.billingDocument` | `billing_document_headers` | `billingDocument` | 1:N |
| `billing_document_items.referenceSdDocument` | `sales_order_items` | `salesOrder + item` | ⚠ May point to delivery (8xxxxxx range) |
| `billing_document_cancellations.billingDocument` | `billing_document_headers` | `billingDocument` | ⚠ Subset — deduplicate before join |
| `journal_entry_items_ar.customer` | `business_partners` | `businessPartner` | N:1 |
| `journal_entry_items_ar.referenceDocument` | `billing_document_headers` | `billingDocument` | N:1 |
| `payments_accounts_receivable.customer` | `business_partners` | `businessPartner` | N:1 |
| `payments_accounts_receivable.accountingDocument` | `journal_entry_items_ar` | `accountingDocument` | ⚠ Duplicate of journal entry rows |

### 1.3 Known Data Hazards

#### Hazard 1 — Cancellations duplication
`billing_document_cancellations` and `billing_document_headers` share identical columns and overlap on all `isCancelled=true` rows. Treat cancellations as a filtered view, not a separate table. Deduplicate on `billingDocument` before any join.

#### Hazard 2 — referenceSdDocument ambiguity
This field appears in both `billing_document_items` and `outbound_delivery_items`. It is assumed to point to `salesOrder` (6–7 digit range: `74xxxx`), but billing items with values in the `8xxxxxx` range likely point to delivery documents instead. Validate range at ingestion.

#### Hazard 3 — payments / journal entry overlap
`payments_accounts_receivable` and `journal_entry_items_ar` share identical PKs (`accountingDocument`, `accountingDocumentItem`) and identical amounts. They are dual-API representations of the same posting. Deduplicate by `accountingDocument` before aggregation — never union them.

#### Hazard 4 — Active transactions on blocked partners
`businessPartnerIsBlocked=true` and `deletionIndicator=true` partners (e.g. `320000083`) appear in live billing and journal entries. Do not reject these rows — flag them with `reason='active_txn_on_blocked_partner'` and route to a review queue.

#### Hazard 5 — billing→delivery link is indirect
There is no `deliveryDocument` field in `billing_document_headers` or `billing_document_items`. The only way to reconstruct the delivery→billing link is by matching `(referenceSdDocument, referenceSdDocumentItem)` across both tables. This breaks when a sales order item is partially delivered across multiple deliveries.

---

## 2. Graph Model

7 node types and 10 directed edge types. Edges are built programmatically from relational joins — no graph-native storage required for the build step.

### 2.1 Node Types

| Node type | ID field | Source table | Key properties | Color token |
|---|---|---|---|---|
| `Customer` | `businessPartner` | `business_partners` | name, isBlocked, region, grouping | gray |
| `Product` | `product` | `products` | description, productGroup, division | blue |
| `Plant` | `plant` | `plants` | plantName, salesOrganization | teal |
| `SalesOrder` | `salesOrder` | `sales_order_headers` | totalNetAmount, status, creationDate | purple |
| `Delivery` | `deliveryDocument` | `outbound_delivery_headers` | pickingStatus, goodsMovementStatus | teal |
| `BillingDocument` | `billingDocument` | `billing_document_headers` | totalNetAmount, isCancelled, fiscalYear | coral |
| `AccountingDocument` | `accountingDocument` | `journal_entry_items_ar` | amount, glAccount, clearingDoc, postingDate | amber |

### 2.2 Edge Types

| Edge type | Source node | Target node | Join key | Build logic |
|---|---|---|---|---|
| `SOLD_TO` | SalesOrder | Customer | `soldToParty = businessPartner` | `sales_order_headers JOIN business_partners ON soldToParty` |
| `CONTAINS_MATERIAL` | SalesOrder | Product | `items.material = product` | `sales_order_items JOIN products ON material` — deduplicate on `(salesOrder, material)` |
| `FULFILLED_BY` | SalesOrder | Delivery | `delivery_items.referenceSdDocument = salesOrder` | `outbound_delivery_items.groupby(deliveryDocument).agg(referenceSdDocument.mode)` |
| `SHIPS_FROM` | Delivery | Plant | `delivery_items.plant = plant` | `outbound_delivery_items JOIN plants ON plant` — deduplicate on `deliveryDocument` |
| `BILLED_AS` | SalesOrder | BillingDocument | `(refSdDoc, refSdDocItem)` match across tables | `billing_items JOIN so_items ON (referenceSdDocument, referenceSdDocumentItem)` |
| `BILLED_TO` | BillingDocument | Customer | `soldToParty = businessPartner` | `billing_document_headers JOIN business_partners ON soldToParty` |
| `POSTS_TO` | BillingDocument | AccountingDocument | `accountingDocument = accountingDocument` | `billing_document_headers.accountingDocument` — 1:1 expected, flag 1:N (reversals) |
| `CLEARED_BY` | AccountingDocument | AccountingDocument | `clearingAccountingDocument` | `journal_entry_items_ar` — self-join on `clearingAccountingDocument`. Drop null clearing. |
| `CANCELLED_BY` | BillingDocument | BillingDocument | `billing_cancellations.billingDocument` | Use `billing_document_headers WHERE isCancelled=true`. Deduplicate vs cancellations table first. |
| `STORED_AT` | Product | Plant | `(product, plant)` | `product_plants` — one edge per `(product, plant)` pair |

### 2.3 Edge Construction — Python Reference

Run in this order. Each step depends on nodes built in the prior step.

```python
# Step 1 — SOLD_TO: SalesOrder → Customer
edges_sold_to = (
    so_headers[['salesOrder', 'soldToParty']]
    .rename(columns={'salesOrder': 'src', 'soldToParty': 'tgt'})
    .assign(edge_type='SOLD_TO')
)

# Step 2 — FULFILLED_BY: SalesOrder → Delivery (via items)
so_map = (
    del_items.groupby('deliveryDocument')['referenceSdDocument']
    .agg(lambda x: x.mode()[0]).reset_index()
    .rename(columns={'referenceSdDocument': 'src', 'deliveryDocument': 'tgt'})
    .assign(edge_type='FULFILLED_BY')
)

# Step 3 — POSTS_TO: BillingDocument → AccountingDocument
edges_posts_to = (
    billing_headers[['billingDocument', 'accountingDocument']]
    .rename(columns={'billingDocument': 'src', 'accountingDocument': 'tgt'})
    .assign(edge_type='POSTS_TO')
)

# Step 4 — CLEARED_BY: AccountingDocument → AccountingDocument
edges_cleared = (
    journal_items[['accountingDocument', 'clearingAccountingDocument']]
    .dropna(subset=['clearingAccountingDocument'])
    .rename(columns={'accountingDocument': 'src',
                     'clearingAccountingDocument': 'tgt'})
    .assign(edge_type='CLEARED_BY')
)

# Step 5 — CANCELLED_BY flag (self-edge on BillingDocument)
cancelled = billing_headers[billing_headers['billingDocumentIsCancelled']]
# Deduplicate: ensure cancellations table adds no phantom rows
ghost_check = set(cancellations['billingDocument']) - set(billing_headers['billingDocument'])
assert len(ghost_check) == 0, f'Ghost cancellation rows: {ghost_check}'
```

### 2.4 Graph Traversal Patterns

| Intent | Graph path |
|---|---|
| `trace_flow (SO)` | `SalesOrder →[FULFILLED_BY]→ Delivery →[BILLED_AS]→ BillingDocument →[POSTS_TO]→ AccountingDocument →[CLEARED_BY]→ AccountingDocument` |
| `trace_flow (billing)` | `BillingDocument →[BILLED_TO]→ Customer` \| `BillingDocument →[POSTS_TO]→ AccountingDocument` \| `BillingDocument →[CANCELLED_BY]→ BillingDocument` |
| `top_products` | `Product ←[CONTAINS_MATERIAL]← SalesOrder` joined with `BillingDocument` via `BILLED_AS`; aggregate `netAmount` on `BillingDocument` |
| `find_broken_flows` | Walk each edge type; collect src nodes with no corresponding tgt. Also check `CLEARED_BY` null; `POSTS_TO` 1:N; `SOLD_TO` where `Customer.isBlocked=true` |
| `lookup_entity` | Single node fetch + optional 1-hop expansion along `include_related` edges |

---

## 3. Query Planner

The LLM outputs structured JSON only. It never generates SQL. The backend executes all queries from the plan object. The LLM is a classification and extraction layer, not a query engine.

### 3.1 Intent Reference

| Intent | Trigger condition | Required fields | Reject condition |
|---|---|---|---|
| `trace_flow` | User asks to follow a document/entity through O2C pipeline | `entity_type`, `entity_id`, `stages[]`, `filters{}` | No entity ID provided; entity_type unrecognised |
| `top_products_by_billing` | User asks about product rankings, top sellers, revenue aggregated at product level | `limit` (1–100), `sort_by`, `filters{}` | No sort dimension; limit out of range |
| `find_broken_flows` | User asks about data quality, missing links, orphaned records, amount mismatches | `break_types[]` (min 1), `filters{}` | break_type value not in allowed enum |
| `lookup_entity` | User asks to retrieve or describe a single known entity | `entity_type`, `entity_id`, `include_related[]` | Entity name given instead of ID |
| `reject` | Mutation request; ambiguous query; out of O2C scope; multiple intents; missing ID | `reason` (enum), `clarification_needed` (10–400 chars) | Never reject a reject — that loops |

### 3.2 JSON Schema (oneOf)

Each intent maps to one schema branch. `additionalProperties: false` is enforced on all branches — any extra key causes a Tier 1 validation failure.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "QueryPlan",
  "oneOf": [
    {
      "title": "trace_flow",
      "required": ["intent", "entity_type", "entity_id", "stages", "filters"],
      "additionalProperties": false,
      "properties": {
        "intent":      { "enum": ["trace_flow"] },
        "entity_type": { "enum": ["sales_order", "billing_document", "delivery", "customer"] },
        "entity_id":   { "type": "string", "minLength": 1 },
        "stages": {
          "type": "array", "minItems": 1, "uniqueItems": true,
          "items": { "enum": ["sales_order", "schedule_lines", "delivery",
                              "billing", "journal_entry", "payment", "cancellation"] }
        },
        "filters": {
          "type": "object", "additionalProperties": false,
          "properties": {
            "company_code":      { "type": ["string", "null"] },
            "fiscal_year":       { "type": ["string", "null"] },
            "include_cancelled": { "type": "boolean" }
          }
        }
      }
    },
    {
      "title": "top_products_by_billing",
      "required": ["intent", "limit", "sort_by", "filters"],
      "additionalProperties": false,
      "properties": {
        "intent":  { "enum": ["top_products_by_billing"] },
        "limit":   { "type": "integer", "minimum": 1, "maximum": 100 },
        "sort_by": { "enum": ["total_net_amount", "invoice_count", "quantity"] },
        "filters": {
          "type": "object", "additionalProperties": false,
          "properties": {
            "date_from":         { "type": ["string", "null"], "format": "date" },
            "date_to":           { "type": ["string", "null"], "format": "date" },
            "company_code":      { "type": ["string", "null"] },
            "customer_id":       { "type": ["string", "null"] },
            "exclude_cancelled": { "type": "boolean" },
            "product_group":     { "type": ["string", "null"] }
          }
        }
      }
    },
    {
      "title": "find_broken_flows",
      "required": ["intent", "break_types", "filters"],
      "additionalProperties": false,
      "properties": {
        "intent": { "enum": ["find_broken_flows"] },
        "break_types": {
          "type": "array", "minItems": 1, "uniqueItems": true,
          "items": { "enum": [
            "billing_without_delivery",
            "delivery_without_sales_order",
            "billing_without_journal_entry",
            "journal_entry_without_clearing",
            "cancelled_without_accounting_doc",
            "active_txn_on_blocked_partner",
            "amount_mismatch_billing_vs_journal"
          ]}
        },
        "filters": {
          "type": "object", "additionalProperties": false,
          "properties": {
            "date_from":    { "type": ["string", "null"], "format": "date" },
            "date_to":      { "type": ["string", "null"], "format": "date" },
            "company_code": { "type": ["string", "null"] },
            "fiscal_year":  { "type": ["string", "null"] }
          }
        }
      }
    },
    {
      "title": "lookup_entity",
      "required": ["intent", "entity_type", "entity_id", "include_related"],
      "additionalProperties": false,
      "properties": {
        "intent":      { "enum": ["lookup_entity"] },
        "entity_type": { "enum": ["customer", "product", "plant",
                                  "sales_order", "delivery", "billing_document"] },
        "entity_id":   { "type": "string", "minLength": 1 },
        "include_related": {
          "type": "array", "uniqueItems": true,
          "items": { "enum": [
            "addresses", "sales_area_config", "company_config",
            "items", "schedule_lines", "billing_documents",
            "journal_entries", "payments", "cancellations",
            "product_descriptions", "storage_locations"
          ]}
        }
      }
    },
    {
      "title": "reject",
      "required": ["intent", "reason", "clarification_needed"],
      "additionalProperties": false,
      "properties": {
        "intent": { "enum": ["reject"] },
        "reason": { "enum": [
          "out_of_scope",
          "ambiguous_entity",
          "unsupported_operation",
          "missing_required_parameter",
          "multiple_intents_detected"
        ]},
        "clarification_needed": { "type": "string", "minLength": 10, "maxLength": 400 }
      }
    }
  ]
}
```

### 3.3 Example Query / Output Pairs

**"Show me the full journey for sales order 740509"**
```json
{
  "intent": "trace_flow",
  "entity_type": "sales_order",
  "entity_id": "740509",
  "stages": ["sales_order", "schedule_lines", "delivery", "billing", "journal_entry", "payment"],
  "filters": { "company_code": null, "fiscal_year": null, "include_cancelled": false }
}
```

**"What happened to billing doc 90504274 — I think it was cancelled"**
```json
{
  "intent": "trace_flow",
  "entity_type": "billing_document",
  "entity_id": "90504274",
  "stages": ["billing", "cancellation", "journal_entry"],
  "filters": { "company_code": null, "fiscal_year": "2025", "include_cancelled": true }
}
```

**"Top 10 products by revenue this April, excluding cancelled invoices"**
```json
{
  "intent": "top_products_by_billing",
  "limit": 10,
  "sort_by": "total_net_amount",
  "filters": {
    "date_from": "2025-04-01", "date_to": "2025-04-30",
    "company_code": null, "customer_id": null,
    "exclude_cancelled": true, "product_group": null
  }
}
```

**"Show me all data quality issues for fiscal year 2025"**
```json
{
  "intent": "find_broken_flows",
  "break_types": [
    "billing_without_delivery", "delivery_without_sales_order",
    "billing_without_journal_entry", "journal_entry_without_clearing",
    "cancelled_without_accounting_doc", "active_txn_on_blocked_partner",
    "amount_mismatch_billing_vs_journal"
  ],
  "filters": { "date_from": null, "date_to": null, "company_code": null, "fiscal_year": "2025" }
}
```

**"Tell me about customer 320000083 with address and payment terms"**
```json
{
  "intent": "lookup_entity",
  "entity_type": "customer",
  "entity_id": "320000083",
  "include_related": ["addresses", "sales_area_config", "company_config"]
}
```

**"Delete all invoices for customer 320000083"**
```json
{
  "intent": "reject",
  "reason": "unsupported_operation",
  "clarification_needed": "This system is read-only. Mutations must be made in the source ERP system."
}
```

**"Show me the orders"**
```json
{
  "intent": "reject",
  "reason": "missing_required_parameter",
  "clarification_needed": "Which orders? Please provide a sales order ID, customer ID, or a date range."
}
```

### 3.4 Validation Rules

| Tier | Check name | Rule | On failure |
|---|---|---|---|
| 1 — Structural | `is_valid_json` | Output must parse as JSON; no markdown fences | Block. Retry once with error appended. If retry fails → surface reject to user. |
| 1 — Structural | `schema_oneOf` | Must match exactly one intent schema (`additionalProperties: false`) | Block. Log as prompt drift. Retry once. |
| 1 — Structural | `intent_in_enum` | `intent` field must be one of the 5 known values | Block. Do not execute. |
| 2 — Semantic | `entity_id_format` | ID must match numeric pattern for entity_type (e.g. salesOrder: 6–8 digits) | Warn + flag. Route to review. Do not execute. |
| 2 — Semantic | `date_range_coherence` | `date_from` < `date_to`; both present or both null | Warn + flag. Return clarification to user. |
| 2 — Semantic | `stages_include_anchor` | `trace_flow` stages must include the entity_type's anchor stage | Warn. Auto-inject anchor stage. Log correction. |
| 2 — Semantic | `include_related_valid` | `include_related` fields must be valid for the given entity_type | Warn. Strip invalid fields. Execute with reduced scope. |
| 3 — Business | `fiscal_vs_date_ambiguity` | `fiscal_year` and `date_from`/`to` must not both be set | Block. Return `clarification_needed` to user. |
| 3 — Business | `reject_wellformed` | `clarification_needed`: 10–400 chars; reason in enum | Block. Return generic rejection message. |
| 3 — Business | `no_mutation_verbs` | Scan raw user query for: delete, update, create, cancel, reverse, post | Force `reject` with `unsupported_operation` before LLM call. |

### 3.5 LLM System Prompt

Paste this verbatim as the system message. Do not paraphrase. The model must see this prompt unchanged on every call.

```
You are a query planner for an Order-to-Cash (O2C) data system. Your only job is to convert
natural language questions into a structured JSON query plan. You do not answer questions
directly. You do not write SQL. You do not explain your reasoning. You output JSON only.

────────────────────────────────────────────
OUTPUT CONTRACT
────────────────────────────────────────────
Your entire response must be a single, valid JSON object.
- No markdown. No code fences. No explanation text before or after.
- No keys outside the schema. No null placeholders for required fields.
- If you are not certain of a value, use the reject intent.

────────────────────────────────────────────
AVAILABLE INTENTS — choose exactly one per response
────────────────────────────────────────────
  trace_flow              — follow a document/entity through the O2C pipeline
  top_products_by_billing — rank products by billed amount, count, or quantity
  find_broken_flows       — surface data quality issues and missing links
  lookup_entity           — fetch a single entity record with optional related data
  reject                  — mutation request / ambiguous / out of scope / multiple intents

────────────────────────────────────────────
FIELD RULES
────────────────────────────────────────────
  entity_id:  output exactly as given. If user gives a name not an ID → reject(ambiguous_entity).
  dates:      ISO-8601 (YYYY-MM-DD). Resolve relative dates. If year unknown → reject.
  null:       only for optional filter fields not specified by the user.
  filters:    always include the filters object even if all values are null.
  include_cancelled / exclude_cancelled: default false; set true only if user says so.

────────────────────────────────────────────
DECISION RULES
────────────────────────────────────────────
  Two questions in one message → reject(multiple_intents_detected).
  Vague request with no ID or scope → reject(missing_required_parameter).
  Mutation verb (delete/update/create/cancel/reverse/post) → reject(unsupported_operation).
  Schema or system design question → reject(out_of_scope).
  Customer name instead of ID → reject(ambiguous_entity).

────────────────────────────────────────────
NEVER
────────────────────────────────────────────
  Write SQL, SOQL, OData, or any query language fragment.
  Include prose, chain-of-thought, or commentary in your response.
  Invent entity IDs, product names, or dates not in the user message.
  Add keys not in the schema for the chosen intent.
  Return a partial JSON object.

────────────────────────────────────────────
EXAMPLES (user → JSON, no explanation)
────────────────────────────────────────────
"Show order 740506"
→ {"intent":"lookup_entity","entity_type":"sales_order","entity_id":"740506","include_related":["items","schedule_lines","billing_documents"]}

"Delete invoices for customer X"
→ {"intent":"reject","reason":"unsupported_operation","clarification_needed":"This system is read-only. Mutations must be made in the source ERP system."}

"Show me the orders"
→ {"intent":"reject","reason":"missing_required_parameter","clarification_needed":"Please provide a sales order ID, customer ID, or date range."}
```

---

## 4. Ingestion Checklist

Run checks in order. Tier 1 failures block the load. Tier 2 and 3 write to a `_validation_log` table and alert when flagged row % exceeds threshold.

| # | Check | Logic | Tier | On fail | Threshold |
|---|---|---|---|---|---|
| 1 | PK uniqueness | No duplicate PKs per table | 1 — Block | Abort load | 0% |
| 2 | Non-null required fields | All required fields present and non-empty | 1 — Block | Abort load | 0% |
| 3 | Numeric amount fields | `totalNetAmount`, `netAmount`, `amount` parseable as float ≥ 0 | 1 — Block | Abort load | 0% |
| 4 | FK existence | Every FK value present in parent table | 2 — Warn | Flag rows, continue | 5% |
| 5 | referenceSdDocument range | Values < 80000000 → SO; ≥ 80000000 → delivery. Flag cross-range. | 2 — Warn | Flag rows, continue | 5% |
| 6 | Blocked partner transactions | billing/journal rows where `soldToParty.isBlocked=true` | 2 — Warn | Flag rows, continue | 1% |
| 7 | Cancellation consistency | Every `billingDocument` in cancellations must be in billing_headers | 2 — Warn | Log ghost rows | 0% |
| 8 | Amount reconciliation | `\|billing.totalNetAmount - journal.amount\|` ≤ 0.02 INR per accountingDoc | 3 — Alert | Route to finance review | 1% |
| 9 | Duplicate journal/payment | `payments_ar.accountingDocument` must not duplicate journal entries | 3 — Alert | Deduplicate, log | 0% |
| 10 | Date coherence | `billingDocumentDate` ≤ `creationDate`; `postingDate` ≥ `billingDocumentDate` | 3 — Alert | Flag rows, continue | 2% |
