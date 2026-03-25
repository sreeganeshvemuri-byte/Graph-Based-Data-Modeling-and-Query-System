from __future__ import annotations

import argparse
from dataclasses import dataclass

from sqlalchemy import and_, cast, func, Integer, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    BillingDocumentHeader,
    BillingDocumentItem,
    BillingDocumentCancellation,
    GraphEdge,
    JournalEntryItemsAR,
    OutboundDeliveryHeader,
    OutboundDeliveryItem,
    PaymentsAccountsReceivable,
    SalesOrderHeader,
    SalesOrderItem,
)
from app.db.session import SessionLocal, init_db


@dataclass(frozen=True)
class NodeRef:
    node_type: str
    node_id: str

    def label(self) -> str:
        return f"{self.node_type}:{self.node_id}"


def _first_sales_order(session: Session) -> str | None:
    # Prefer a sales order that actually participates in the graph via BILLED_AS.
    row = session.execute(
        select(GraphEdge.source_id)
        .where(
            GraphEdge.source_type == "sales_order",
            GraphEdge.edge_type == "BILLED_AS",
        )
        .order_by(GraphEdge.source_id)
        .limit(1)
    ).scalar_one_or_none()
    if row is not None:
        return str(row)

    # Fallback: any sales order.
    row2 = session.execute(
        select(SalesOrderHeader.salesOrder).order_by(SalesOrderHeader.salesOrder).limit(1)
    ).scalar_one_or_none()
    return str(row2) if row2 is not None else None


def _first_billing_document(session: Session) -> str | None:
    row = session.execute(
        select(BillingDocumentHeader.billingDocument)
        .order_by(BillingDocumentHeader.billingDocument)
        .limit(1)
    ).scalar_one_or_none()
    return row


def _count(session: Session, model) -> int:
    return int(session.execute(select(func.count()).select_from(model)).scalar_one())


def fetch_sales_order_bundle(session: Session, sales_order_id: str) -> dict[str, object]:
    items = session.execute(
        select(SalesOrderItem).where(SalesOrderItem.salesOrder == sales_order_id)
    ).scalars().all()

    deliveries = session.execute(
        select(OutboundDeliveryHeader).where(
            OutboundDeliveryHeader.deliveryDocument.in_(
                select(OutboundDeliveryItem.deliveryDocument).where(
                    OutboundDeliveryItem.referenceSdDocument == sales_order_id
                )
            )
        )
    ).scalars().all()

    billing_doc_ids = session.execute(
        select(func.distinct(GraphEdge.target_id)).where(
            GraphEdge.source_type == "sales_order",
            GraphEdge.source_id == sales_order_id,
            GraphEdge.edge_type == "BILLED_AS",
        )
    ).scalars().all()
    billing_doc_ids = [str(x) for x in billing_doc_ids]

    billing_headers = session.execute(
        select(BillingDocumentHeader).where(BillingDocumentHeader.billingDocument.in_(billing_doc_ids))
    ).scalars().all()

    accounting_ids = session.execute(
        select(func.distinct(BillingDocumentHeader.accountingDocument)).where(
            BillingDocumentHeader.billingDocument.in_(billing_doc_ids),
            BillingDocumentHeader.accountingDocument.is_not(None),
        )
    ).scalars().all()
    accounting_ids = [str(x) for x in accounting_ids]

    accounting_entries = session.execute(
        select(JournalEntryItemsAR).where(JournalEntryItemsAR.accountingDocument.in_(accounting_ids))
    ).scalars().all()

    delivery_items = session.execute(
        select(OutboundDeliveryItem).where(
            OutboundDeliveryItem.deliveryDocument.in_([d.deliveryDocument for d in deliveries])
        )
    ).scalars().all() if deliveries else []

    billing_items = session.execute(
        select(BillingDocumentItem).where(
            BillingDocumentItem.billingDocument.in_(billing_doc_ids)
        )
    ).scalars().all() if billing_doc_ids else []

    return {
        "sales_order_id": sales_order_id,
        "items": items,
        "deliveries": deliveries,
        "delivery_items": delivery_items,
        "billing_document_headers": billing_headers,
        "billing_items": billing_items,
        "accounting_entries": accounting_entries,
    }


def trace_billing_document(session: Session, billing_document_id: str) -> dict[str, object]:
    # Trace back: graph edge BILLED_AS provides authoritative linkage.
    sales_order_ids_from_graph = session.execute(
        select(func.distinct(GraphEdge.source_id)).where(
            GraphEdge.target_type == "billing_document",
            GraphEdge.target_id == billing_document_id,
            GraphEdge.edge_type == "BILLED_AS",
        )
    ).scalars().all()
    sales_order_ids_from_graph = [str(x) for x in sales_order_ids_from_graph]

    billing_header = session.execute(
        select(BillingDocumentHeader).where(BillingDocumentHeader.billingDocument == billing_document_id)
    ).scalars().first()

    # Forward to accounting doc: both relational and graph should agree.
    accounting_id_from_rel = (
        str(billing_header.accountingDocument) if billing_header and billing_header.accountingDocument is not None else None
    )

    accounting_id_from_graph = session.execute(
        select(func.distinct(GraphEdge.target_id)).where(
            GraphEdge.source_type == "billing_document",
            GraphEdge.source_id == billing_document_id,
            GraphEdge.edge_type == "POSTS_TO",
        )
    ).scalars().all()
    accounting_id_from_graph = [str(x) for x in accounting_id_from_graph]

    return {
        "billing_document_id": billing_document_id,
        "sales_order_ids_from_graph": sales_order_ids_from_graph,
        "accounting_id_from_rel": accounting_id_from_rel,
        "accounting_ids_from_graph": accounting_id_from_graph,
    }


def connected_nodes_via_graph(
    session: Session,
    start: NodeRef,
    *,
    depth: int = 2,
    max_nodes: int = 200,
) -> set[NodeRef]:
    """
    Undirected-ish neighborhood traversal (considers both outgoing and incoming edges).
    """
    visited: set[NodeRef] = {start}
    frontier: set[NodeRef] = {start}

    for _ in range(depth):
        if not frontier:
            break
        next_frontier: set[NodeRef] = set()

        for node in list(frontier):
            outgoing = session.execute(
                select(GraphEdge).where(
                    GraphEdge.source_type == node.node_type,
                    GraphEdge.source_id == node.node_id,
                )
            ).scalars().all()
            incoming = session.execute(
                select(GraphEdge).where(
                    GraphEdge.target_type == node.node_type,
                    GraphEdge.target_id == node.node_id,
                )
            ).scalars().all()

            for e in outgoing:
                nbr = NodeRef(e.target_type, e.target_id)
                if nbr not in visited:
                    next_frontier.add(nbr)
            for e in incoming:
                nbr = NodeRef(e.source_type, e.source_id)
                if nbr not in visited:
                    next_frontier.add(nbr)

        # Cap to avoid runaway neighborhoods.
        next_frontier = {n for n in next_frontier if n not in visited}
        if len(visited) + len(next_frontier) > max_nodes:
            break
        visited |= next_frontier
        frontier = next_frontier

    return visited


def print_graph_edges_for_sales_order(session: Session, sales_order_id: str, depth: int = 2) -> None:
    start = NodeRef("sales_order", sales_order_id)
    nodes = connected_nodes_via_graph(session, start, depth=depth)
    print(f"Connected graph nodes (depth={depth}): {len(nodes)}")
    for n in sorted(nodes, key=lambda x: (x.node_type, x.node_id)):
        print(f"  - {n.label()}")

    edges = session.execute(
        select(GraphEdge).where(
            or_(
                and_(GraphEdge.source_type == "sales_order", GraphEdge.source_id == sales_order_id),
                and_(GraphEdge.target_type == "sales_order", GraphEdge.target_id == sales_order_id),
            )
        )
    ).scalars().all()
    print(f"Direct edges touching {start.label()}: {len(edges)}")
    for e in edges[:50]:
        print(
            f"  {e.edge_type}: {e.source_type}:{e.source_id} -> {e.target_type}:{e.target_id}"
        )
    if len(edges) > 50:
        print(f"  ... ({len(edges) - 50} more)")


def print_counts(session: Session) -> None:
    from app.db import models as m

    table_models = [
        m.BusinessPartner,
        m.BusinessPartnerAddress,
        m.CustomerCompanyAssignment,
        m.CustomerSalesAreaAssignment,
        m.Product,
        m.ProductDescription,
        m.Plant,
        m.ProductPlant,
        m.ProductStorageLocation,
        m.SalesOrderHeader,
        m.SalesOrderItem,
        m.SalesOrderScheduleLine,
        m.OutboundDeliveryHeader,
        m.OutboundDeliveryItem,
        m.BillingDocumentHeader,
        m.BillingDocumentItem,
        m.BillingDocumentCancellation,
        m.JournalEntryItemsAR,
        m.PaymentsAccountsReceivable,
        m.GraphEdge,
    ]

    print("Row counts:")
    for model in table_models:
        print(f"  {model.__tablename__}: {_count(session, model)}")

    print("\nGraph edge counts by edge_type:")
    edge_rows = session.execute(
        select(GraphEdge.edge_type, func.count()).group_by(GraphEdge.edge_type).order_by(func.count().desc())
    ).all()
    for edge_type, cnt in edge_rows:
        print(f"  {edge_type}: {cnt}")


def check_billing_reference_mapping(session: Session) -> None:
    """
    Validate:
    - billing_document_items.referenceSdDocument/referenceSdDocumentItem joins to sales_order_items
    - delivery-references (8xxxxxx) are resolved (after canonicalization)
    """
    # Rows where we have a usable reference mapping.
    total = session.execute(
        select(func.count()).select_from(BillingDocumentItem).where(
            BillingDocumentItem.referenceSdDocument.is_not(None),
            BillingDocumentItem.referenceSdDocumentItem.is_not(None),
        )
    ).scalar_one()

    join_ok = session.execute(
        select(func.count()).select_from(BillingDocumentItem).join(
            SalesOrderItem,
            and_(
                SalesOrderItem.salesOrder == BillingDocumentItem.referenceSdDocument,
                SalesOrderItem.item == BillingDocumentItem.referenceSdDocumentItem,
            ),
        ).where(
            BillingDocumentItem.referenceSdDocument.is_not(None),
            BillingDocumentItem.referenceSdDocumentItem.is_not(None),
        )
    ).scalar_one()

    delivery_like = session.execute(
        select(func.count()).select_from(BillingDocumentItem).where(
            BillingDocumentItem.referenceSdDocument.is_not(None),
            BillingDocumentItem.referenceSdDocumentItem.is_not(None),
            cast(BillingDocumentItem.referenceSdDocument, Integer) >= 80000000,
        )
    ).scalar_one()

    join_ok_delivery_like = session.execute(
        select(func.count()).select_from(BillingDocumentItem).join(
            SalesOrderItem,
            and_(
                SalesOrderItem.salesOrder == BillingDocumentItem.referenceSdDocument,
                SalesOrderItem.item == BillingDocumentItem.referenceSdDocumentItem,
            ),
        ).where(
            BillingDocumentItem.referenceSdDocument.is_not(None),
            BillingDocumentItem.referenceSdDocumentItem.is_not(None),
            cast(BillingDocumentItem.referenceSdDocument, Integer) >= 80000000,
        )
    ).scalar_one()

    print("\n=== Deep check 1) billing_document_items reference mapping ===")
    print(f"Billing items with reference mapping: {total}")
    print(f"Join to sales_order_items OK: {join_ok}")
    print(f"Reference values that look like delivery (>=80000000): {delivery_like}")
    print(f"Delivery-like rows that STILL join to SO items: {join_ok_delivery_like}")

    # After canonicalization, we expect the mapping to always resolve to SO keys.
    # (Hard assert to catch any major linkage break.)
    assert join_ok == total, (
        f"Mismatch: {total - join_ok} billing_document_items rows do not join to sales_order_items "
        f"using (referenceSdDocument, referenceSdDocumentItem)."
    )

    # If canonicalization worked, delivery-like should be ~0. We keep it as a soft assertion:
    # if ingestion didn’t canonicalize a few edge cases, we still want visibility.
    assert delivery_like == 0, (
        f"{delivery_like} billing_document_items rows still have delivery-like referenceSdDocument "
        f"(>=80000000) after canonicalization."
    )

    # Show examples for debugging when assertion fails.
    if total != 0 and join_ok != total:
        missing_examples = session.execute(
            select(
                BillingDocumentItem.billingDocument,
                BillingDocumentItem.item,
                BillingDocumentItem.referenceSdDocument,
                BillingDocumentItem.referenceSdDocumentItem,
            )
            .select_from(BillingDocumentItem)
            .outerjoin(
                SalesOrderItem,
                and_(
                    SalesOrderItem.salesOrder == BillingDocumentItem.referenceSdDocument,
                    SalesOrderItem.item == BillingDocumentItem.referenceSdDocumentItem,
                ),
            )
            .where(
                BillingDocumentItem.referenceSdDocument.is_not(None),
                BillingDocumentItem.referenceSdDocumentItem.is_not(None),
                SalesOrderItem.salesOrder.is_(None),
            )
            .limit(10)
        ).all()
        print("Sample unmapped billing items (first 10):")
        for row in missing_examples:
            print(" ", row)


def check_cancellation_handling(session: Session) -> None:
    """
    Validate:
    - billing_document_cancellations subset vs billing_document_headers
    - CANCELLED_BY graph edges have no duplicates and cover all cancelled billing docs
    """
    cancelled_headers = session.execute(
        select(BillingDocumentHeader.billingDocument).where(BillingDocumentHeader.isCancelled.is_(True))
    ).scalars().all()
    cancelled_headers_set = {str(x) for x in cancelled_headers}

    cancellations_table = session.execute(
        select(BillingDocumentCancellation.billingDocument)
    ).scalars().all()
    cancellations_set = {str(x) for x in cancellations_table}

    intersection = cancelled_headers_set & cancellations_set
    ghost_cancellations = cancellations_set - cancelled_headers_set
    missing_cancellations = cancelled_headers_set - cancellations_set

    cancelled_edges = session.execute(
        select(GraphEdge).where(GraphEdge.edge_type == "CANCELLED_BY")
    ).scalars().all()
    cancelled_edge_keys = {(e.source_id, e.target_id) for e in cancelled_edges}

    # Check duplicates by source billingDocument.
    dup_cnt = session.execute(
        select(GraphEdge.source_id, func.count()).where(
            GraphEdge.edge_type == "CANCELLED_BY",
            GraphEdge.source_id == GraphEdge.target_id,
        ).group_by(GraphEdge.source_id)
    ).all()
    max_mult = max((cnt for _, cnt in dup_cnt), default=1)

    print("\n=== Deep check 2) cancellation handling ===")
    print(f"Cancelled in headers: {len(cancelled_headers_set)}")
    print(f"Cancelled in cancellations table: {len(cancellations_set)}")
    print(f"Intersection (expected cancelled billing docs): {len(intersection)}")
    print(f"Ghost cancellations (in table but not headers): {len(ghost_cancellations)}")
    print(f"Missing cancellations (in headers but not table): {len(missing_cancellations)}")
    if ghost_cancellations:
        print("  Sample ghost cancellation billing docs:", sorted(list(ghost_cancellations))[:10])
    if missing_cancellations:
        print("  Sample missing cancellation billing docs:", sorted(list(missing_cancellations))[:10])

    print(f"CANCELLED_BY graph edges: {len(cancelled_edges)}")
    print(f"Max duplicate multiplicity per source billingDocument: {max_mult}")

    # Must have no duplicates: graph_edges PK should enforce it, but assert anyway.
    assert max_mult == 1, f"Found duplicate CANCELLED_BY edges (max multiplicity={max_mult})."

    # Must cover all cancelled billing docs intersection.
    missing_edges = intersection - {s for (s, _) in cancelled_edge_keys}
    extra_edges = {s for (s, _) in cancelled_edge_keys} - intersection
    assert not missing_edges, f"Missing CANCELLED_BY edges for billing docs (count={len(missing_edges)})."
    assert not extra_edges, f"Extra CANCELLED_BY edges for non-cancelled docs (count={len(extra_edges)})."


def check_journal_vs_payments_duplication(session: Session) -> None:
    """
    Validate:
    - journal vs payments duplication does not leak into CLEARED_BY edges
    - overlap and clearingAccountingDocument consistency across both tables
    """
    # Check CLEARED_BY edges match journal clearing pairs (not payments).
    journal_clear_pairs = session.execute(
        select(
            JournalEntryItemsAR.accountingDocument,
            JournalEntryItemsAR.clearingAccountingDocument,
        ).where(JournalEntryItemsAR.clearingAccountingDocument.is_not(None)).distinct()
    ).all()
    journal_pair_set = {(str(a), str(c)) for a, c in journal_clear_pairs}

    cleared_edges = session.execute(
        select(GraphEdge.source_id, GraphEdge.target_id).where(GraphEdge.edge_type == "CLEARED_BY")
    ).all()
    cleared_edge_set = {(str(s), str(t)) for s, t in cleared_edges}

    # Overlap checks between journal and payments PKs.
    overlap_keys = session.execute(
        select(func.count()).select_from(JournalEntryItemsAR).join(
            PaymentsAccountsReceivable,
            and_(
                PaymentsAccountsReceivable.accountingDocument == JournalEntryItemsAR.accountingDocument,
                PaymentsAccountsReceivable.item == JournalEntryItemsAR.item,
            ),
        )
    ).scalar_one()

    journal_cnt = session.execute(select(func.count()).select_from(JournalEntryItemsAR)).scalar_one()
    payments_cnt = session.execute(select(func.count()).select_from(PaymentsAccountsReceivable)).scalar_one()

    print("\n=== Deep check 3) journal vs payments duplication ===")
    print(f"journal rows: {journal_cnt}")
    print(f"payments rows: {payments_cnt}")
    print(f"overlap on (accountingDocument, item): {overlap_keys}")
    print(f"CLEARED_BY edges: {len(cleared_edge_set)}")
    print(f"Distinct journal clearing pairs: {len(journal_pair_set)}")

    # Hard assert: graph edges must be derived from journal pairs.
    assert journal_pair_set == cleared_edge_set, (
        "CLEARED_BY edges do not match distinct journal (accountingDocument, clearingAccountingDocument) pairs."
    )

    # Consistency check for clearingAccountingDocument values on overlapping PKs.
    mismatches = session.execute(
        select(
            JournalEntryItemsAR.accountingDocument,
            JournalEntryItemsAR.item,
            JournalEntryItemsAR.clearingAccountingDocument,
            PaymentsAccountsReceivable.clearingAccountingDocument,
        )
        .select_from(JournalEntryItemsAR)
        .join(
            PaymentsAccountsReceivable,
            and_(
                PaymentsAccountsReceivable.accountingDocument == JournalEntryItemsAR.accountingDocument,
                PaymentsAccountsReceivable.item == JournalEntryItemsAR.item,
            ),
        )
        .where(
            or_(
                JournalEntryItemsAR.clearingAccountingDocument != PaymentsAccountsReceivable.clearingAccountingDocument,
            )
        )
        .limit(10)
    ).all()
    print(f"Journal/Payments clearingAccountingDocument mismatches (first 10 shown): {len(mismatches)}")
    for row in mismatches[:10]:
        print("  ", row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate ingestion relationships via relational tables + graph_edges.")
    parser.add_argument("--sales-order", dest="sales_order_id", default=None)
    parser.add_argument("--billing-document", dest="billing_document_id", default=None)
    parser.add_argument("--graph-depth", dest="graph_depth", type=int, default=2)
    args = parser.parse_args()

    init_db()
    with SessionLocal() as session:
        sales_order_id = args.sales_order_id or _first_sales_order(session)
        if not sales_order_id:
            raise SystemExit("No sales orders found in DB. Run ingestion first.")

        print(f"=== 1) Sales order bundle: {sales_order_id} ===")
        bundle = fetch_sales_order_bundle(session, sales_order_id)
        items = bundle["items"]
        deliveries = bundle["deliveries"]
        delivery_items = bundle["delivery_items"]
        billing_headers = bundle["billing_document_headers"]
        billing_items = bundle["billing_items"]
        accounting_entries = bundle["accounting_entries"]
        print(f"Items: {len(items)}")
        print(f"Deliveries (headers): {len(deliveries)} / (items): {len(delivery_items)}")
        print(f"Billing documents: {len(billing_headers)}")
        print(f"Billing items: {len(billing_items)}")
        print(f"Accounting entries (journal rows): {len(accounting_entries)}")

        # Print a small sample to keep output readable.
        if items:
            first_item = items[0]
            print(
                f"  Sample item: item={first_item.item} material={first_item.material} netAmount={first_item.netAmount}"
            )
        if deliveries:
            first_delivery = deliveries[0]
            print(
                f"  Sample delivery: deliveryDocument={first_delivery.deliveryDocument} pickingStatus={first_delivery.pickingStatus}"
            )
        if billing_headers:
            first_bill = billing_headers[0]
            print(
                f"  Sample billing: billingDocument={first_bill.billingDocument} accountingDocument={first_bill.accountingDocument} isCancelled={first_bill.isCancelled}"
            )

        print(f"\n=== 3) Graph neighborhood from sales order {sales_order_id} ===")
        print_graph_edges_for_sales_order(session, sales_order_id, depth=args.graph_depth)

        print("\n=== 2) Trace from a billing document (back/forward) ===")
        billing_document_id = args.billing_document_id or _first_billing_document(session)
        if not billing_document_id:
            raise SystemExit("No billing documents found in DB. Run ingestion first.")
        trace = trace_billing_document(session, billing_document_id)
        print(f"Billing doc: {trace['billing_document_id']}")
        print(f"Sales orders (from graph BILLED_AS): {trace['sales_order_ids_from_graph']}")
        print(f"Accounting doc (from relational billing header): {trace['accounting_id_from_rel']}")
        print(f"Accounting docs (from graph POSTS_TO): {trace['accounting_ids_from_graph']}")

        print("\n=== 4) Row counts + edge counts ===")
        print_counts(session)

        # Targeted validations for tricky linkage.
        check_billing_reference_mapping(session)
        check_cancellation_handling(session)
        check_journal_vs_payments_duplication(session)


if __name__ == "__main__":
    main()

