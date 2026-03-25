from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    BillingDocumentCancellation,
    BillingDocumentHeader,
    BillingDocumentItem,
    GraphEdge,
    JournalEntryItemsAR,
    OutboundDeliveryItem,
    ProductPlant,
    SalesOrderHeader,
    SalesOrderItem,
)


def _mode(values: Iterable[str]) -> str | None:
    counts = Counter(v for v in values if v is not None)
    if not counts:
        return None
    # Deterministic tie-breaker for rerun stability.
    best_count = max(counts.values())
    best = sorted([v for v, c in counts.items() if c == best_count])[0]
    return best


def build_graph_edges(session: Session) -> None:
    """
    Rebuild graph_edges from relational tables.

    Idempotent: clears existing edges then re-inserts.
    """
    session.execute(delete(GraphEdge))
    session.flush()

    edges: list[GraphEdge] = []

    # 1) SOLD_TO: SalesOrder -> Customer
    sold_to_rows = session.execute(
        select(SalesOrderHeader.salesOrder, SalesOrderHeader.soldToParty).where(
            SalesOrderHeader.soldToParty.is_not(None)
        )
    ).all()
    for so_id, cust_id in sold_to_rows:
        edges.append(
            GraphEdge(
                source_type="sales_order",
                source_id=str(so_id),
                target_type="customer",
                target_id=str(cust_id),
                edge_type="SOLD_TO",
            )
        )

    # 2) CONTAINS_MATERIAL: SalesOrder -> Product (dedupe (salesOrder, product))
    so_material_pairs = session.execute(
        select(SalesOrderItem.salesOrder, SalesOrderItem.material).where(
            SalesOrderItem.material.is_not(None)
        )
    ).all()
    seen = set()
    for so_id, prod_id in so_material_pairs:
        key = (str(so_id), str(prod_id))
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            GraphEdge(
                source_type="sales_order",
                source_id=str(so_id),
                target_type="product",
                target_id=str(prod_id),
                edge_type="CONTAINS_MATERIAL",
            )
        )

    # 3) FULFILLED_BY: SalesOrder -> Delivery via delivery_items.referenceSdDocument
    # Spec: deliveryDocument -> mode(referenceSdDocument)
    delivery_to_so = defaultdict(list)
    del_items = session.execute(
        select(OutboundDeliveryItem.deliveryDocument, OutboundDeliveryItem.referenceSdDocument).select_from(
            OutboundDeliveryItem
        ).join(
            SalesOrderHeader,
            SalesOrderHeader.salesOrder == OutboundDeliveryItem.referenceSdDocument,
        ).where(OutboundDeliveryItem.referenceSdDocument.is_not(None))
    ).all()
    for delivery_id, so_ref in del_items:
        delivery_to_so[str(delivery_id)].append(str(so_ref))
    for delivery_id, so_refs in delivery_to_so.items():
        src_so = _mode(so_refs)
        if not src_so:
            continue
        edges.append(
            GraphEdge(
                source_type="sales_order",
                source_id=src_so,
                target_type="delivery",
                target_id=delivery_id,
                edge_type="FULFILLED_BY",
            )
        )

    # 4) SHIPS_FROM: Delivery -> Plant
    delivery_to_plants = defaultdict(list)
    del_plants = session.execute(
        select(OutboundDeliveryItem.deliveryDocument, OutboundDeliveryItem.plant).where(
            OutboundDeliveryItem.plant.is_not(None)
        )
    ).all()
    for delivery_id, plant_id in del_plants:
        delivery_to_plants[str(delivery_id)].append(str(plant_id))
    for delivery_id, plant_refs in delivery_to_plants.items():
        tgt_plant = _mode(plant_refs)
        if not tgt_plant:
            continue
        edges.append(
            GraphEdge(
                source_type="delivery",
                source_id=delivery_id,
                target_type="plant",
                target_id=tgt_plant,
                edge_type="SHIPS_FROM",
            )
        )

    # 5) BILLED_AS: SalesOrder -> BillingDocument (via billing_document_items.referenceSdDocument)
    billed_as_rows = session.execute(
        select(BillingDocumentItem.referenceSdDocument, BillingDocumentItem.billingDocument).select_from(
            BillingDocumentItem
        ).join(
            SalesOrderItem,
            and_(
                SalesOrderItem.salesOrder == BillingDocumentItem.referenceSdDocument,
                SalesOrderItem.item == BillingDocumentItem.referenceSdDocumentItem,
            ),
        ).where(
            BillingDocumentItem.referenceSdDocument.is_not(None),
            BillingDocumentItem.referenceSdDocumentItem.is_not(None),
        )
    ).all()
    seen.clear()
    for so_id, billing_id in billed_as_rows:
        key = (str(so_id), str(billing_id))
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            GraphEdge(
                source_type="sales_order",
                source_id=str(so_id),
                target_type="billing_document",
                target_id=str(billing_id),
                edge_type="BILLED_AS",
            )
        )

    # 6) BILLED_TO: BillingDocument -> Customer (billing_document_headers.soldToParty)
    billed_to_rows = session.execute(
        select(BillingDocumentHeader.billingDocument, BillingDocumentHeader.soldToParty).where(
            BillingDocumentHeader.soldToParty.is_not(None)
        )
    ).all()
    for billing_id, cust_id in billed_to_rows:
        edges.append(
            GraphEdge(
                source_type="billing_document",
                source_id=str(billing_id),
                target_type="customer",
                target_id=str(cust_id),
                edge_type="BILLED_TO",
            )
        )

    # 7) POSTS_TO: BillingDocument -> AccountingDocument
    posts_to_rows = session.execute(
        select(BillingDocumentHeader.billingDocument, BillingDocumentHeader.accountingDocument).where(
            BillingDocumentHeader.accountingDocument.is_not(None)
        )
    ).all()
    for billing_id, acct_id in posts_to_rows:
        edges.append(
            GraphEdge(
                source_type="billing_document",
                source_id=str(billing_id),
                target_type="accounting_document",
                target_id=str(acct_id),
                edge_type="POSTS_TO",
            )
        )

    # 8) CLEARED_BY: AccountingDocument -> AccountingDocument
    cleared_rows = session.execute(
        select(JournalEntryItemsAR.accountingDocument, JournalEntryItemsAR.clearingAccountingDocument).where(
            JournalEntryItemsAR.clearingAccountingDocument.is_not(None)
        )
    ).all()
    seen.clear()
    for src_acct, tgt_acct in cleared_rows:
        key = (str(src_acct), str(tgt_acct))
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            GraphEdge(
                source_type="accounting_document",
                source_id=str(src_acct),
                target_type="accounting_document",
                target_id=str(tgt_acct),
                edge_type="CLEARED_BY",
            )
        )

    # 9) CANCELLED_BY: BillingDocument -> BillingDocument (self-edge for cancelled documents)
    cancelled_ids = session.execute(
        select(BillingDocumentHeader.billingDocument).where(BillingDocumentHeader.isCancelled.is_(True))
    ).scalars().all()
    cancelled_set = {str(x) for x in cancelled_ids}
    # If the dedicated cancellations table exists, intersect for safety.
    cancels = session.execute(select(BillingDocumentCancellation.billingDocument)).scalars().all()
    cancels_set = {str(x) for x in cancels}
    final_cancelled = cancelled_set if not cancels_set else (cancelled_set & cancels_set)
    for billing_id in sorted(final_cancelled):
        edges.append(
            GraphEdge(
                source_type="billing_document",
                source_id=billing_id,
                target_type="billing_document",
                target_id=billing_id,
                edge_type="CANCELLED_BY",
            )
        )

    # 10) STORED_AT: Product -> Plant (from product_plants)
    stored_at_rows = session.execute(
        select(ProductPlant.product, ProductPlant.plant).where(
            ProductPlant.plant.is_not(None), ProductPlant.product.is_not(None)
        )
    ).all()
    seen.clear()
    for prod_id, plant_id in stored_at_rows:
        key = (str(prod_id), str(plant_id))
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            GraphEdge(
                source_type="product",
                source_id=str(prod_id),
                target_type="plant",
                target_id=str(plant_id),
                edge_type="STORED_AT",
            )
        )

    session.add_all(edges)
    session.commit()

