from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    BillingDocumentCancellation,
    BillingDocumentHeader,
    BillingDocumentItem,
    BusinessPartner,
    BusinessPartnerAddress,
    CustomerCompanyAssignment,
    CustomerSalesAreaAssignment,
    GraphEdge,
    JournalEntryItemsAR,
    OutboundDeliveryHeader,
    OutboundDeliveryItem,
    Plant,
    Product,
    ProductDescription,
    ProductPlant,
    ProductStorageLocation,
    PaymentsAccountsReceivable,
    SalesOrderHeader,
    SalesOrderItem,
    SalesOrderScheduleLine,
)
from app.query.plans import (
    FindBrokenFlowsPlan,
    FindBrokenFlowsFilters,
    LookupEntityPlan,
    LookupEntityPlan as _LookupEntityPlan,
    TraceFlowPlan,
    TopProductsPlan,
)


@dataclass(frozen=True)
class NodeRef:
    node_type: str
    node_id: str


def _node_dict(n: NodeRef) -> dict[str, str]:
    return {"type": n.node_type, "id": n.node_id}


def _edge_dict(edge: GraphEdge) -> dict[str, Any]:
    return {
        "edge_type": edge.edge_type,
        "source": {"type": edge.source_type, "id": edge.source_id},
        "target": {"type": edge.target_type, "id": edge.target_id},
    }


def _apply_billing_filters(stmt, *, filters: Any):
    # Works for BillingDocumentHeader-based queries.
    # Filters is a Pydantic model but we access via attributes.
    if getattr(filters, "company_code", None):
        stmt = stmt.where(BillingDocumentHeader.companyCode == filters.company_code)
    if getattr(filters, "fiscal_year", None):
        stmt = stmt.where(BillingDocumentHeader.fiscalYear == filters.fiscal_year)
    if getattr(filters, "date_from", None):
        stmt = stmt.where(BillingDocumentHeader.billingDocumentDate >= datetime.combine(filters.date_from, datetime.min.time()))
    if getattr(filters, "date_to", None):
        stmt = stmt.where(BillingDocumentHeader.billingDocumentDate <= datetime.combine(filters.date_to, datetime.max.time()))
    return stmt


def _apply_journal_filters(stmt, *, filters: Any):
    if getattr(filters, "company_code", None):
        stmt = stmt.where(JournalEntryItemsAR.companyCode == filters.company_code)
    if getattr(filters, "fiscal_year", None):
        stmt = stmt.where(JournalEntryItemsAR.fiscalYear == filters.fiscal_year)
    if getattr(filters, "date_from", None):
        stmt = stmt.where(JournalEntryItemsAR.postingDate >= datetime.combine(filters.date_from, datetime.min.time()))
    if getattr(filters, "date_to", None):
        stmt = stmt.where(JournalEntryItemsAR.postingDate <= datetime.combine(filters.date_to, datetime.max.time()))
    return stmt


def handle_trace_flow(session: Session, plan: TraceFlowPlan) -> dict[str, Any]:
    start_node = NodeRef(plan.entity_type if plan.entity_type != "billing_document" else "billing_document", plan.entity_id)
    # Normalize entity_type to our graph node types.
    start_type_map = {
        "sales_order": "sales_order",
        "billing_document": "billing_document",
        "delivery": "delivery",
        "customer": "customer",
    }
    start_node = NodeRef(start_type_map[plan.entity_type], plan.entity_id)

    # Derive sales_orders as the backbone of the traversal.
    sales_order_ids: set[str] = set()
    if plan.entity_type == "sales_order":
        sales_order_ids.add(plan.entity_id)
    elif plan.entity_type == "delivery":
        so_ids = session.execute(
            select(GraphEdge.source_id).where(
                GraphEdge.source_type == "sales_order",
                GraphEdge.target_type == "delivery",
                GraphEdge.edge_type == "FULFILLED_BY",
                GraphEdge.target_id == plan.entity_id,
            )
        ).scalars().all()
        sales_order_ids.update(str(x) for x in so_ids)
    elif plan.entity_type == "billing_document":
        so_ids = session.execute(
            select(GraphEdge.source_id).where(
                GraphEdge.source_type == "sales_order",
                GraphEdge.target_type == "billing_document",
                GraphEdge.edge_type == "BILLED_AS",
                GraphEdge.target_id == plan.entity_id,
            )
        ).scalars().all()
        sales_order_ids.update(str(x) for x in so_ids)
    elif plan.entity_type == "customer":
        so_ids = session.execute(
            select(GraphEdge.source_id).where(
                GraphEdge.source_type == "sales_order",
                GraphEdge.target_type == "customer",
                GraphEdge.edge_type == "SOLD_TO",
                GraphEdge.target_id == plan.entity_id,
            )
        ).scalars().all()
        sales_order_ids.update(str(x) for x in so_ids)

    # If we cannot derive sales orders, return an empty path.
    nodes: dict[tuple[str, str], NodeRef] = {}
    edges: list[GraphEdge] = []

    # Add start node to output regardless.
    nodes[(start_node.node_type, start_node.node_id)] = start_node

    if not sales_order_ids:
        return {
            "intent": "trace_flow",
            "entity_type": plan.entity_type,
            "entity_id": plan.entity_id,
            "path": {"nodes": list(nodes.values()), "edges": []},
        }

    stages = set(plan.stages)

    # Schedule lines (side nodes)
    schedule_line_nodes: list[NodeRef] = []
    if "schedule_lines" in stages:
        schedule_rows = session.execute(
            select(SalesOrderScheduleLine).where(SalesOrderScheduleLine.salesOrder.in_(sales_order_ids))
        ).scalars().all()
        for r in schedule_rows:
            node_id = f"{r.salesOrder}:{r.item}:{r.scheduleLine}"
            schedule_line_nodes.append(NodeRef("schedule_line", node_id))
        for n in schedule_line_nodes:
            nodes[(n.node_type, n.node_id)] = n

    # Deliveries
    delivery_nodes: list[NodeRef] = []
    if "delivery" in stages:
        del_edges = session.execute(
            select(GraphEdge).where(
                GraphEdge.source_type == "sales_order",
                GraphEdge.source_id.in_(sales_order_ids),
                GraphEdge.edge_type == "FULFILLED_BY",
            )
        ).scalars().all()
        edges.extend(del_edges)
        for e in del_edges:
            nodes[(e.target_type, e.target_id)] = NodeRef(e.target_type, e.target_id)
            nodes[(e.source_type, e.source_id)] = NodeRef(e.source_type, e.source_id)
            delivery_nodes.append(NodeRef(e.target_type, e.target_id))

    # Billing
    billing_nodes: list[NodeRef] = []
    billing_edges: list[GraphEdge] = []
    if "billing" in stages:
        billing_edges = session.execute(
            select(GraphEdge).where(
                GraphEdge.source_type == "sales_order",
                GraphEdge.source_id.in_(sales_order_ids),
                GraphEdge.edge_type == "BILLED_AS",
            )
        ).scalars().all()

        billing_ids = {e.target_id for e in billing_edges}
        billing_headers = session.execute(
            select(BillingDocumentHeader).where(BillingDocumentHeader.billingDocument.in_(billing_ids))
        ).scalars().all()
        header_by_id = {h.billingDocument: h for h in billing_headers}

        # Apply cancellation/company/year filters.
        filtered_billing_ids: set[str] = set()
        for bid, h in header_by_id.items():
            if (not plan.filters.include_cancelled) and h.isCancelled:
                continue
            if plan.filters.company_code and h.companyCode != plan.filters.company_code:
                continue
            if plan.filters.fiscal_year and h.fiscalYear != plan.filters.fiscal_year:
                continue
            filtered_billing_ids.add(bid)

        for e in billing_edges:
            if e.target_id in filtered_billing_ids:
                edges.append(e)
                nodes[(e.target_type, e.target_id)] = NodeRef(e.target_type, e.target_id)
                nodes[(e.source_type, e.source_id)] = NodeRef(e.source_type, e.source_id)
                billing_nodes.append(NodeRef(e.target_type, e.target_id))

    # Journal entry + payment
    if "journal_entry" in stages:
        # POSTS_TO from billing docs -> accounting docs
        billing_ids = {n.node_id for n in billing_nodes if n.node_type == "billing_document"}
        if not billing_ids:
            # If billing stage isn't requested but journal_entry is, derive from all billing docs reachable.
            billing_ids = set(
                session.execute(
                    select(GraphEdge.target_id).where(
                        GraphEdge.source_type == "sales_order",
                        GraphEdge.source_id.in_(sales_order_ids),
                        GraphEdge.edge_type == "BILLED_AS",
                    )
                ).scalars().all()
            )
        posts = session.execute(
            select(GraphEdge).where(
                GraphEdge.source_type == "billing_document",
                GraphEdge.source_id.in_(billing_ids),
                GraphEdge.edge_type == "POSTS_TO",
            )
        ).scalars().all()
        edges.extend(posts)
        for e in posts:
            nodes[(e.target_type, e.target_id)] = NodeRef(e.target_type, e.target_id)
            nodes[(e.source_type, e.source_id)] = NodeRef(e.source_type, e.source_id)

    payment_nodes: list[NodeRef] = []
    if "payment" in stages:
        accounting_ids = {
            n.node_id for n in nodes.values() if n.node_type == "accounting_document"
        }
        clears = session.execute(
            select(GraphEdge).where(
                GraphEdge.source_type == "accounting_document",
                GraphEdge.source_id.in_(accounting_ids),
                GraphEdge.edge_type == "CLEARED_BY",
            )
        ).scalars().all()
        edges.extend(clears)
        for e in clears:
            nodes[(e.target_type, e.target_id)] = NodeRef(e.target_type, e.target_id)
            nodes[(e.source_type, e.source_id)] = NodeRef(e.source_type, e.source_id)
            payment_nodes.append(NodeRef(e.target_type, e.target_id))

    # Cancellations: CANCELLED_BY is a self-edge on billing_document
    if "cancellation" in stages and (plan.filters.include_cancelled):
        cancelled_ids = session.execute(
            select(BillingDocumentHeader.billingDocument).where(
                BillingDocumentHeader.billingDocument.in_(
                    {n.node_id for n in nodes.values() if n.node_type == "billing_document"}
                ),
                BillingDocumentHeader.isCancelled.is_(True),
            )
        ).scalars().all()
        cancelled_ids_set = {str(x) for x in cancelled_ids}
        cancels = session.execute(
            select(GraphEdge).where(
                GraphEdge.edge_type == "CANCELLED_BY",
                GraphEdge.source_type == "billing_document",
                GraphEdge.source_id.in_(cancelled_ids_set),
            )
        ).scalars().all()
        edges.extend(cancels)
        for e in cancels:
            nodes[(e.target_type, e.target_id)] = NodeRef(e.target_type, e.target_id)
            nodes[(e.source_type, e.source_id)] = NodeRef(e.source_type, e.source_id)

    # Deduplicate edges by PK.
    unique_edge_keys: set[tuple[str, str, str, str, str]] = set()
    unique_edges: list[GraphEdge] = []
    for e in edges:
        k = (e.source_type, str(e.source_id), e.target_type, str(e.target_id), e.edge_type)
        if k in unique_edge_keys:
            continue
        unique_edge_keys.add(k)
        unique_edges.append(e)

    return {
        "intent": "trace_flow",
        "entity_type": plan.entity_type,
        "entity_id": plan.entity_id,
        "path": {
            "nodes": [ _node_dict(n) for n in nodes.values() ],
            "edges": [ _edge_dict(e) for e in unique_edges ],
        },
    }


def handle_top_products_by_billing(session: Session, plan: TopProductsPlan) -> dict[str, Any]:
    # Base filters come from BillingDocumentHeader.
    stmt = (
        select(
            BillingDocumentItem.material.label("product_id"),
            func.sum(BillingDocumentItem.netAmount).label("total_net_amount"),
            func.count(func.distinct(BillingDocumentItem.billingDocument)).label("invoice_count"),
            func.count().label("quantity"),
        )
        .join(BillingDocumentHeader, BillingDocumentHeader.billingDocument == BillingDocumentItem.billingDocument)
        .join(Product, Product.product == BillingDocumentItem.material)
        .where(BillingDocumentItem.material.is_not(None))
    )

    f = plan.filters
    if f.company_code:
        stmt = stmt.where(BillingDocumentHeader.companyCode == f.company_code)
    if f.customer_id:
        stmt = stmt.where(BillingDocumentHeader.soldToParty == f.customer_id)
    if f.product_group:
        stmt = stmt.where(Product.productGroup == f.product_group)
    if f.exclude_cancelled:
        stmt = stmt.where(or_(BillingDocumentHeader.isCancelled.is_(None), BillingDocumentHeader.isCancelled.is_(False)))
    if f.date_from:
        stmt = stmt.where(BillingDocumentHeader.billingDocumentDate >= datetime.combine(f.date_from, datetime.min.time()))
    if f.date_to:
        stmt = stmt.where(BillingDocumentHeader.billingDocumentDate <= datetime.combine(f.date_to, datetime.max.time()))

    stmt = stmt.group_by(BillingDocumentItem.material)

    if plan.sort_by == "total_net_amount":
        stmt = stmt.order_by(func.sum(BillingDocumentItem.netAmount).desc())
    elif plan.sort_by == "invoice_count":
        stmt = stmt.order_by(func.count(func.distinct(BillingDocumentItem.billingDocument)).desc())
    elif plan.sort_by == "quantity":
        stmt = stmt.order_by(func.count().desc())
    else:
        stmt = stmt.order_by(func.sum(BillingDocumentItem.netAmount).desc())

    rows = session.execute(stmt.limit(plan.limit)).all()

    results: list[dict[str, Any]] = []
    for product_id, total_net_amount, invoice_count, quantity in rows:
        results.append(
            {
                "product_id": str(product_id),
                "total_net_amount": float(total_net_amount or 0.0),
                "invoice_count": int(invoice_count or 0),
                "quantity": int(quantity or 0),
            }
        )

    return {
        "intent": "top_products_by_billing",
        "limit": plan.limit,
        "sort_by": plan.sort_by,
        "results": results,
    }


def handle_find_broken_flows(session: Session, plan: FindBrokenFlowsPlan) -> dict[str, Any]:
    f = plan.filters

    # Billing doc universe (filtered).
    billing_stmt = select(BillingDocumentHeader.billingDocument).where(BillingDocumentHeader.billingDocument.is_not(None))
    billing_stmt = _apply_billing_filters(billing_stmt, filters=f)
    billing_ids = {str(x) for x in session.execute(billing_stmt).scalars().all()}

    issues: list[dict[str, Any]] = []

    # Helper sets from graph.
    billed_as_edges = session.execute(
        select(GraphEdge.source_id, GraphEdge.target_id).where(
            GraphEdge.edge_type == "BILLED_AS",
            GraphEdge.target_type == "billing_document",
            GraphEdge.target_id.in_(billing_ids) if billing_ids else False,
        )
    ).all()
    # Map billing -> sales orders
    billing_to_so: dict[str, set[str]] = defaultdict(set)
    for so_id, bill_id in billed_as_edges:
        billing_to_so[str(bill_id)].add(str(so_id))

    # Map sales orders -> deliveries
    fulfilled_edges = session.execute(
        select(GraphEdge.source_id, GraphEdge.target_id).where(
            GraphEdge.edge_type == "FULFILLED_BY",
            GraphEdge.target_type == "delivery",
        )
    ).all()
    so_to_deliveries: dict[str, set[str]] = defaultdict(set)
    for so_id, del_id in fulfilled_edges:
        so_to_deliveries[str(so_id)].add(str(del_id))

    # Billing -> accounting
    posts_edges = session.execute(
        select(GraphEdge.source_id, GraphEdge.target_id).where(
            GraphEdge.edge_type == "POSTS_TO",
            GraphEdge.source_type == "billing_document",
            GraphEdge.source_id.in_(billing_ids) if billing_ids else False,
        )
    ).all()
    billing_to_acct: dict[str, set[str]] = defaultdict(set)
    for bill_id, acct_id in posts_edges:
        billing_to_acct[str(bill_id)].add(str(acct_id))

    # Accounting -> clearing
    cleared_edges = session.execute(
        select(GraphEdge.source_id, GraphEdge.target_id).where(
            GraphEdge.edge_type == "CLEARED_BY",
            GraphEdge.source_type == "accounting_document",
        )
    ).all()
    acct_to_clears: dict[str, set[str]] = defaultdict(set)
    for a, c in cleared_edges:
        acct_to_clears[str(a)].add(str(c))

    for break_type in plan.break_types:
        if break_type == "billing_without_delivery":
            for bill_id in sorted(billing_ids):
                so_ids = billing_to_so.get(bill_id, set())
                deliveries = set()
                for so_id in so_ids:
                    deliveries |= so_to_deliveries.get(so_id, set())
                if not deliveries:
                    issues.append(
                        {
                            "break_type": break_type,
                            "billing_document": bill_id,
                            "sales_orders": sorted(so_ids),
                        }
                    )
        elif break_type == "delivery_without_sales_order":
            # Candidate deliveries: deliveries not present as target of FULFILLED_BY.
            delivery_stmt = select(OutboundDeliveryHeader.deliveryDocument).where(
                OutboundDeliveryHeader.deliveryDocument.is_not(None)
            )
            candidate_delivery_ids = {str(x) for x in session.execute(delivery_stmt).scalars().all()}
            fulfilled_delivery_ids = {str(x) for x in session.execute(
                select(GraphEdge.target_id).where(
                    GraphEdge.edge_type == "FULFILLED_BY",
                    GraphEdge.target_type == "delivery",
                )
            ).scalars().all()}
            broken_deliveries = candidate_delivery_ids - fulfilled_delivery_ids
            # Optional: apply filters by requiring they connect to at least one filtered billing doc.
            for del_id in sorted(broken_deliveries):
                # Derive sales orders for this delivery (by reverse fulfillment); if none, it is already broken.
                so_ids = session.execute(
                    select(GraphEdge.source_id).where(
                        GraphEdge.edge_type == "FULFILLED_BY",
                        GraphEdge.target_type == "delivery",
                        GraphEdge.target_id == del_id,
                    )
                ).scalars().all()
                related_billing = set()
                for so_id in so_ids:
                    for bill, sos in billing_to_so.items():
                        if str(so_id) in sos:
                            related_billing.add(bill)
                # Keep if it connects to filtered billing universe, else skip.
                if billing_ids and not related_billing:
                    continue
                issues.append({"break_type": break_type, "delivery": del_id})
        elif break_type == "billing_without_journal_entry":
            for bill_id in sorted(billing_ids):
                if not billing_to_acct.get(bill_id):
                    issues.append(
                        {"break_type": break_type, "billing_document": bill_id}
                    )
        elif break_type == "journal_entry_without_clearing":
            # Consider accounting docs that appear as POSTS_TO targets for filtered billings.
            acct_ids = set()
            for acct_set in billing_to_acct.values():
                acct_ids |= acct_set
            for acct_id in sorted(acct_ids):
                if not acct_to_clears.get(acct_id):
                    issues.append(
                        {"break_type": break_type, "accounting_document": acct_id}
                    )
        elif break_type == "cancelled_without_accounting_doc":
            cancelled_ids = {
                str(x)
                for x in session.execute(
                    select(BillingDocumentHeader.billingDocument).where(
                        BillingDocumentHeader.billingDocument.in_(billing_ids),
                        BillingDocumentHeader.isCancelled.is_(True),
                    )
                ).scalars().all()
            }
            for bill_id in sorted(cancelled_ids):
                if not billing_to_acct.get(bill_id):
                    issues.append({"break_type": break_type, "billing_document": bill_id})
        elif break_type == "active_txn_on_blocked_partner":
            blocked_customers = {
                str(x)
                for x in session.execute(
                    select(BusinessPartner.businessPartner).where(BusinessPartner.isBlocked.is_(True))
                ).scalars().all()
            }
            if blocked_customers and billing_ids:
                blocked_bills = session.execute(
                    select(BillingDocumentHeader.billingDocument).where(
                        BillingDocumentHeader.billingDocument.in_(billing_ids),
                        BillingDocumentHeader.soldToParty.in_(blocked_customers),
                    )
                ).scalars().all()
                for bid in blocked_bills:
                    issues.append({"break_type": break_type, "billing_document": str(bid)})
            # Journal side (optional extra context).
            if blocked_customers:
                # Apply journal filters.
                journal_stmt = select(
                    JournalEntryItemsAR.accountingDocument
                ).where(JournalEntryItemsAR.customer.in_(blocked_customers))
                journal_stmt = _apply_journal_filters(journal_stmt, filters=f)
                acct_ids = session.execute(journal_stmt).scalars().all()
                for aid in acct_ids:
                    issues.append({"break_type": break_type, "accounting_document": str(aid)})
        elif break_type == "amount_mismatch_billing_vs_journal":
            # Compare billing header totalNetAmount to sum of journal amounts (company currency).
            # Use journal_entry_items_ar.referenceDocument -> billing_document_headers.billingDocument.
            mismatch_threshold = 0.01
            # Preload billing totals
            billing_headers = session.execute(
                select(BillingDocumentHeader.billingDocument, BillingDocumentHeader.totalNetAmount).where(
                    BillingDocumentHeader.billingDocument.in_(billing_ids),
                    BillingDocumentHeader.totalNetAmount.is_not(None),
                )
            ).all()
            billing_total = {str(bid): float(t or 0.0) for bid, t in billing_headers}

            journal_sums = session.execute(
                select(
                    JournalEntryItemsAR.referenceDocument,
                    func.sum(JournalEntryItemsAR.amountInCompanyCodeCurrency),
                )
                .where(
                    JournalEntryItemsAR.referenceDocument.in_(billing_ids),
                    JournalEntryItemsAR.amountInCompanyCodeCurrency.is_not(None),
                )
                .group_by(JournalEntryItemsAR.referenceDocument)
            ).all()
            journal_total = {str(bid): float(s or 0.0) for bid, s in journal_sums}

            for bill_id in sorted(billing_ids):
                bt = billing_total.get(bill_id)
                if bt is None:
                    continue
                jt = journal_total.get(bill_id, 0.0)
                if abs(bt - jt) > mismatch_threshold:
                    issues.append(
                        {
                            "break_type": break_type,
                            "billing_document": bill_id,
                            "billing_total": bt,
                            "journal_total": jt,
                            "diff": bt - jt,
                        }
                    )

        else:
            # Unknown break type (should not happen due to validation)
            issues.append({"break_type": break_type, "note": "unhandled"})

    return {"intent": "find_broken_flows", "break_types": plan.break_types, "issues": issues}


def handle_lookup_entity(session: Session, plan: LookupEntityPlan) -> dict[str, Any]:
    entity_type = plan.entity_type
    entity_id = plan.entity_id
    include_related = set(plan.include_related)

    related: dict[str, Any] = {}

    if entity_type == "customer":
        entity = session.execute(
            select(BusinessPartner).where(BusinessPartner.businessPartner == entity_id)
        ).scalars().first()
        if not entity:
            return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "error": "not_found"}

        entity_payload = {
            "businessPartner": entity.businessPartner,
            "fullName": entity.fullName,
            "category": entity.category,
            "isBlocked": entity.isBlocked,
            "isMarkedForArchiving": entity.isMarkedForArchiving,
            "region": entity.region,
            "grouping": entity.grouping,
        }

        if "addresses" in include_related:
            rows = session.execute(
                select(BusinessPartnerAddress).where(BusinessPartnerAddress.businessPartner == entity_id)
            ).scalars().all()
            related["addresses"] = [
                {
                    "addressId": r.addressId,
                    "cityName": r.cityName,
                    "region": r.region,
                    "country": r.country,
                    "postalCode": r.postalCode,
                    "validityStartDate": r.validityStartDate.isoformat() if r.validityStartDate else None,
                }
                for r in rows
            ]
        if "sales_area_config" in include_related:
            rows = session.execute(
                select(CustomerSalesAreaAssignment).where(CustomerSalesAreaAssignment.customer == entity_id)
            ).scalars().all()
            related["sales_area_config"] = [
                {
                    "salesOrg": r.salesOrg,
                    "distCh": r.distCh,
                    "division": r.division,
                    "currency": r.currency,
                    "incoterms": r.incoterms,
                    "shippingCondition": r.shippingCondition,
                    "paymentTerms": r.paymentTerms,
                }
                for r in rows
            ]
        if "company_config" in include_related:
            rows = session.execute(
                select(CustomerCompanyAssignment).where(CustomerCompanyAssignment.customer == entity_id)
            ).scalars().all()
            related["company_config"] = [
                {
                    "companyCode": r.companyCode,
                    "reconciliationAccount": r.reconciliationAccount,
                    "paymentTerms": r.paymentTerms,
                    "deletionIndicator": r.deletionIndicator,
                }
                for r in rows
            ]

        return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "entity": entity_payload, "related": related}

    if entity_type == "product":
        entity = session.execute(select(Product).where(Product.product == entity_id)).scalars().first()
        if not entity:
            return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "error": "not_found"}
        entity_payload = {
            "product": entity.product,
            "productType": entity.productType,
            "productGroup": entity.productGroup,
            "division": entity.division,
            "isMarkedForDeletion": entity.isMarkedForDeletion,
        }
        if "product_descriptions" in include_related:
            rows = session.execute(
                select(ProductDescription).where(ProductDescription.product == entity_id)
            ).scalars().all()
            related["product_descriptions"] = [
                {"language": r.language, "productDescription": r.productDescription}
                for r in rows
            ]
        if "storage_locations" in include_related:
            rows = session.execute(
                select(ProductStorageLocation).where(ProductStorageLocation.product == entity_id)
            ).scalars().all()
            related["storage_locations"] = [
                {
                    "plant": r.plant,
                    "storageLocation": r.storageLocation,
                    "physicalInventoryBlockInd": r.physicalInventoryBlockInd,
                    "dateOfLastPostedCnt": r.dateOfLastPostedCnt.isoformat() if r.dateOfLastPostedCnt else None,
                }
                for r in rows
            ]
        return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "entity": entity_payload, "related": related}

    if entity_type == "plant":
        entity = session.execute(select(Plant).where(Plant.plant == entity_id)).scalars().first()
        if not entity:
            return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "error": "not_found"}
        entity_payload = {
            "plant": entity.plant,
            "plantName": entity.plantName,
            "salesOrganization": entity.salesOrganization,
            "valuationArea": entity.valuationArea,
        }
        if "storage_locations" in include_related:
            rows = session.execute(
                select(ProductStorageLocation).where(ProductStorageLocation.plant == entity_id)
            ).scalars().all()
            related["storage_locations"] = [
                {
                    "product": r.product,
                    "storageLocation": r.storageLocation,
                    "physicalInventoryBlockInd": r.physicalInventoryBlockInd,
                    "dateOfLastPostedCnt": r.dateOfLastPostedCnt.isoformat() if r.dateOfLastPostedCnt else None,
                }
                for r in rows
            ]
        return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "entity": entity_payload, "related": related}

    if entity_type == "sales_order":
        entity = session.execute(select(SalesOrderHeader).where(SalesOrderHeader.salesOrder == entity_id)).scalars().first()
        if not entity:
            return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "error": "not_found"}
        entity_payload = {
            "salesOrder": entity.salesOrder,
            "soldToParty": entity.soldToParty,
            "totalNetAmount": entity.totalNetAmount,
            "status": entity.status,
            "creationDate": entity.creationDate.isoformat() if entity.creationDate else None,
        }
        if "items" in include_related:
            rows = session.execute(select(SalesOrderItem).where(SalesOrderItem.salesOrder == entity_id)).scalars().all()
            related["items"] = [
                {
                    "salesOrderItem": r.item,
                    "material": r.material,
                    "netAmount": r.netAmount,
                    "quantity": r.quantity,
                    "productionPlant": r.productionPlant,
                }
                for r in rows
            ]
        if "schedule_lines" in include_related:
            rows = session.execute(select(SalesOrderScheduleLine).where(SalesOrderScheduleLine.salesOrder == entity_id)).scalars().all()
            related["schedule_lines"] = [
                {
                    "item": r.item,
                    "scheduleLine": r.scheduleLine,
                    "confirmedDeliveryDate": r.confirmedDeliveryDate.isoformat() if r.confirmedDeliveryDate else None,
                    "confdOrderQty": r.confdOrderQty,
                }
                for r in rows
            ]
        if "billing_documents" in include_related:
            billing_ids = session.execute(
                select(GraphEdge.target_id).where(
                    GraphEdge.source_type == "sales_order",
                    GraphEdge.source_id == entity_id,
                    GraphEdge.edge_type == "BILLED_AS",
                )
            ).scalars().all()
            billing_rows = session.execute(
                select(BillingDocumentHeader).where(BillingDocumentHeader.billingDocument.in_([str(x) for x in billing_ids]))
            ).scalars().all()
            related["billing_documents"] = [
                {
                    "billingDocument": b.billingDocument,
                    "accountingDocument": b.accountingDocument,
                    "isCancelled": b.isCancelled,
                    "fiscalYear": b.fiscalYear,
                }
                for b in billing_rows
            ]

        return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "entity": entity_payload, "related": related}

    if entity_type == "delivery":
        entity = session.execute(select(OutboundDeliveryHeader).where(OutboundDeliveryHeader.deliveryDocument == entity_id)).scalars().first()
        if not entity:
            return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "error": "not_found"}
        entity_payload = {
            "deliveryDocument": entity.deliveryDocument,
            "pickingStatus": entity.pickingStatus,
            "goodsMovementStatus": entity.goodsMovementStatus,
            "shippingPoint": entity.shippingPoint,
        }
        if "billing_documents" in include_related:
            # delivery -> sales orders via reverse FULFILLED_BY; sales orders -> billings via BILLED_AS
            so_ids = session.execute(
                select(GraphEdge.source_id).where(
                    GraphEdge.edge_type == "FULFILLED_BY",
                    GraphEdge.target_type == "delivery",
                    GraphEdge.target_id == entity_id,
                )
            ).scalars().all()
            bill_ids = session.execute(
                select(GraphEdge.target_id).where(
                    GraphEdge.edge_type == "BILLED_AS",
                    GraphEdge.source_type == "sales_order",
                    GraphEdge.source_id.in_([str(x) for x in so_ids]) if so_ids else False,
                )
            ).scalars().all()
            bill_rows = session.execute(
                select(BillingDocumentHeader).where(BillingDocumentHeader.billingDocument.in_([str(x) for x in bill_ids]))
            ).scalars().all()
            related["billing_documents"] = [
                {"billingDocument": b.billingDocument, "accountingDocument": b.accountingDocument, "isCancelled": b.isCancelled}
                for b in bill_rows
            ]
        return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "entity": entity_payload, "related": related}

    if entity_type == "billing_document":
        entity = session.execute(select(BillingDocumentHeader).where(BillingDocumentHeader.billingDocument == entity_id)).scalars().first()
        if not entity:
            return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "error": "not_found"}
        entity_payload = {
            "billingDocument": entity.billingDocument,
            "soldToParty": entity.soldToParty,
            "accountingDocument": entity.accountingDocument,
            "isCancelled": entity.isCancelled,
            "companyCode": entity.companyCode,
            "fiscalYear": entity.fiscalYear,
            "billingDocumentDate": entity.billingDocumentDate.isoformat() if entity.billingDocumentDate else None,
            "totalNetAmount": entity.totalNetAmount,
        }

        if "cancellations" in include_related:
            rows = session.execute(
                select(BillingDocumentCancellation).where(BillingDocumentCancellation.billingDocument == entity_id)
            ).scalars().all()
            related["cancellations"] = [{"billingDocument": r.billingDocument} for r in rows]

        if "journal_entries" in include_related:
            rows = session.execute(
                select(JournalEntryItemsAR).where(JournalEntryItemsAR.referenceDocument == entity_id)
            ).scalars().all()
            related["journal_entries"] = [
                {
                    "accountingDocument": r.accountingDocument,
                    "item": r.item,
                    "customer": r.customer,
                    "amountInCompanyCodeCurrency": r.amountInCompanyCodeCurrency,
                    "glAccount": r.glAccount,
                    "clearingAccountingDocument": r.clearingAccountingDocument,
                    "postingDate": r.postingDate.isoformat() if r.postingDate else None,
                }
                for r in rows
            ]

        if "payments" in include_related:
            # Payments PK is (accountingDocument, item); include where accountingDocument matches journal entries for this billing.
            journal_accounting_docs = session.execute(
                select(func.distinct(JournalEntryItemsAR.accountingDocument)).where(JournalEntryItemsAR.referenceDocument == entity_id)
            ).scalars().all()
            payment_rows = session.execute(
                select(PaymentsAccountsReceivable).where(
                    PaymentsAccountsReceivable.accountingDocument.in_([str(x) for x in journal_accounting_docs])
                )
            ).scalars().all()
            related["payments"] = [
                {
                    "accountingDocument": r.accountingDocument,
                    "item": r.item,
                    "customer": r.customer,
                    "clearingAccountingDocument": r.clearingAccountingDocument,
                    "postingDate": r.postingDate.isoformat() if r.postingDate else None,
                }
                for r in payment_rows
            ]

        return {"intent": "lookup_entity", "entity_type": entity_type, "entity_id": entity_id, "entity": entity_payload, "related": related}

    # Should be unreachable due to validation.
    return {"intent": "reject", "reason": "unsupported_operation", "clarification_needed": "Unsupported entity_type."}

