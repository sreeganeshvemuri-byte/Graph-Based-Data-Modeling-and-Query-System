from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from sqlalchemy.orm import Session

from app.db import models as m
from sqlalchemy import select


def _to_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    # Numbers and other scalars become strings.
    return str(v)


def _normalize_numeric_id(v: Any) -> str | None:
    """
    Normalize padded numeric IDs coming from JSONL (e.g. "000010" -> "10").
    Non-numeric values are returned unchanged (aside from stripping).
    """
    s = _to_str(v)
    if s is None:
        return None
    if s.isdigit():
        s2 = s.lstrip("0")
        return s2 if s2 else "0"
    return s


def _parse_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if v in (0, 1):
            return bool(v)
        return None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"true", "t", "1", "yes", "y"}:
            return True
        if s in {"false", "f", "0", "no", "n"}:
            return False
    return None


def _parse_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _parse_datetime(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    # Dataset uses ISO with 'Z' suffix; convert to RFC3339 offset form.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _get_any(record: dict[str, Any], keys: Iterable[str]) -> Any:
    for k in keys:
        if k in record:
            return record.get(k)
    return None


SOURCE_TABLE_REQUIRED_PKS_RAW: dict[str, list[str]] = {
    "business_partners": ["businessPartner"],
    "business_partner_addresses": ["businessPartner", "addressId"],
    "customer_company_assignments": ["customer", "companyCode"],
    "customer_sales_area_assignments": ["customer", "salesOrganization", "distributionChannel", "division"],
    "products": ["product"],
    "product_descriptions": ["product", "language"],
    "plants": ["plant"],
    "product_plants": ["product", "plant"],
    "product_storage_locations": ["product", "plant", "storageLocation"],
    "sales_order_headers": ["salesOrder", "soldToParty"],
    "sales_order_items": ["salesOrder", "salesOrderItem"],
    "sales_order_schedule_lines": ["salesOrder", "salesOrderItem", "scheduleLine"],
    "outbound_delivery_headers": ["deliveryDocument"],
    "outbound_delivery_items": ["deliveryDocument", "deliveryDocumentItem"],
    "billing_document_headers": ["billingDocument", "soldToParty"],
    "billing_document_items": ["billingDocument", "billingDocumentItem"],
    "billing_document_cancellations": ["billingDocument"],
    "journal_entry_items_accounts_receivable": ["accountingDocument", "accountingDocumentItem"],
    "payments_accounts_receivable": ["accountingDocument", "accountingDocumentItem"],
}


def _upsert_row(session: Session, obj: Any) -> None:
    """
    Upsert by primary key using SQLAlchemy merge.
    """
    session.merge(obj)


def _discover_jsonl_table_dirs(dataset_root: Path) -> list[Path]:
    """
    Each directory directly containing at least one *.jsonl file becomes one input "table".
    """
    root = dataset_root.resolve()
    found: list[Path] = []
    for dirpath, _, filenames in __import__("os").walk(root, topdown=True):
        if any(name.endswith(".jsonl") for name in filenames):
            found.append(Path(dirpath))
    return sorted(found, key=lambda p: str(p).lower())


# ---- Mapping configuration ----


def _bool_or_none(record: dict[str, Any], keys: Iterable[str]) -> bool | None:
    return _parse_bool(_get_any(record, keys))


def _ingest_business_partners(session: Session, record: dict[str, Any]) -> m.BusinessPartner | None:
    businessPartner = _to_str(record.get("businessPartner"))
    if not businessPartner:
        return None
    return m.BusinessPartner(
        businessPartner=businessPartner,
        fullName=_to_str(_get_any(record, ["businessPartnerFullName", "businessPartnerName"])),
        category=_to_str(_get_any(record, ["businessPartnerCategory", "businessPartnerCategory"])),
        isBlocked=_bool_or_none(record, ["businessPartnerIsBlocked"]),
        isMarkedForArchiving=_bool_or_none(record, ["isMarkedForArchiving"]),
        grouping=_to_str(record.get("businessPartnerGrouping")),
    )


def _ingest_business_partner_addresses(session: Session, record: dict[str, Any]) -> m.BusinessPartnerAddress | None:
    businessPartner = _to_str(record.get("businessPartner"))
    addressId = _to_str(record.get("addressId"))
    if not businessPartner or not addressId:
        return None
    return m.BusinessPartnerAddress(
        businessPartner=businessPartner,
        addressId=addressId,
        cityName=_to_str(record.get("cityName")),
        region=_to_str(record.get("region")),
        country=_to_str(record.get("country")),
        postalCode=_to_str(record.get("postalCode") or record.get("postal_code")),
        validityStartDate=_parse_datetime(record.get("validityStartDate")),
    )


def _ingest_customer_company_assignments(
    session: Session, record: dict[str, Any]
) -> m.CustomerCompanyAssignment | None:
    customer = _to_str(record.get("customer"))
    companyCode = _to_str(record.get("companyCode"))
    if not customer or not companyCode:
        return None
    return m.CustomerCompanyAssignment(
        customer=customer,
        companyCode=companyCode,
        reconciliationAccount=_to_str(record.get("reconciliationAccount")),
        paymentTerms=_to_str(record.get("paymentTerms")),
        deletionIndicator=_bool_or_none(record, ["deletionIndicator"]),
    )


def _ingest_customer_sales_area_assignments(
    session: Session, record: dict[str, Any]
) -> m.CustomerSalesAreaAssignment | None:
    customer = _to_str(record.get("customer"))
    salesOrg = _to_str(record.get("salesOrg")) or _to_str(record.get("salesOrganization"))
    distCh = _to_str(record.get("distCh")) or _to_str(record.get("distributionChannel"))
    division = _to_str(record.get("division"))
    if not customer or not salesOrg or not distCh or not division:
        return None
    return m.CustomerSalesAreaAssignment(
        customer=customer,
        salesOrg=salesOrg,
        distCh=distCh,
        division=division,
        currency=_to_str(record.get("currency")),
        incoterms=_to_str(record.get("incoterms")),
        shippingCondition=_to_str(record.get("shippingCondition")),
        paymentTerms=_to_str(record.get("paymentTerms")),
    )


def _ingest_products(session: Session, record: dict[str, Any]) -> m.Product | None:
    product = _to_str(record.get("product"))
    if not product:
        return None
    return m.Product(
        product=product,
        productType=_to_str(record.get("productType")),
        productGroup=_to_str(record.get("productGroup")),
        division=_to_str(record.get("division")),
        isMarkedForDeletion=_bool_or_none(record, ["isMarkedForDeletion"]),
    )


def _ingest_product_descriptions(session: Session, record: dict[str, Any]) -> m.ProductDescription | None:
    product = _to_str(record.get("product"))
    language = _to_str(record.get("language"))
    if not product or not language:
        return None
    return m.ProductDescription(
        product=product,
        language=language,
        productDescription=_to_str(record.get("productDescription")),
    )


def _ingest_plants(session: Session, record: dict[str, Any]) -> m.Plant | None:
    plant = _to_str(record.get("plant"))
    if not plant:
        return None
    return m.Plant(
        plant=plant,
        plantName=_to_str(record.get("plantName")),
        salesOrganization=_to_str(record.get("salesOrganization")),
        valuationArea=_to_str(record.get("valuationArea")),
    )


def _ingest_product_plants(session: Session, record: dict[str, Any]) -> m.ProductPlant | None:
    product = _to_str(record.get("product"))
    plant = _to_str(record.get("plant"))
    if not product or not plant:
        return None
    return m.ProductPlant(
        product=product,
        plant=plant,
        mrpType=_to_str(record.get("mrpType")),
        profitCenter=_to_str(record.get("profitCenter")),
        countryOfOrigin=_to_str(record.get("countryOfOrigin")),
    )


def _ingest_product_storage_locations(
    session: Session, record: dict[str, Any]
) -> m.ProductStorageLocation | None:
    product = _to_str(record.get("product"))
    plant = _to_str(record.get("plant"))
    storageLocation = _to_str(record.get("storageLocation"))
    if not product or not plant or not storageLocation:
        return None
    return m.ProductStorageLocation(
        product=product,
        plant=plant,
        storageLocation=storageLocation,
        physicalInventoryBlockInd=_to_str(record.get("physicalInventoryBlockInd")),
        dateOfLastPostedCnt=_parse_datetime(record.get("dateOfLastPostedCnt")),
    )


def _ingest_sales_order_headers(session: Session, record: dict[str, Any]) -> m.SalesOrderHeader | None:
    salesOrder = _to_str(record.get("salesOrder"))
    soldToParty = _to_str(record.get("soldToParty"))
    if not salesOrder or not soldToParty:
        return None
    status = _to_str(record.get("overallDeliveryStatus")) or _to_str(record.get("salesOrderType"))
    return m.SalesOrderHeader(
        salesOrder=salesOrder,
        soldToParty=soldToParty,
        totalNetAmount=_parse_float(record.get("totalNetAmount")),
        status=status,
        creationDate=_parse_datetime(record.get("creationDate")),
    )


def _ingest_sales_order_items(session: Session, record: dict[str, Any]) -> m.SalesOrderItem | None:
    salesOrder = _to_str(record.get("salesOrder"))
    item = _normalize_numeric_id(record.get("salesOrderItem"))
    if not salesOrder or not item:
        return None
    return m.SalesOrderItem(
        salesOrder=salesOrder,
        item=item,
        material=_to_str(record.get("material")),
        netAmount=_parse_float(record.get("netAmount")),
        quantity=_parse_float(record.get("requestedQuantity")),
        productionPlant=_to_str(record.get("productionPlant")),
    )


def _ingest_sales_order_schedule_lines(
    session: Session, record: dict[str, Any]
) -> m.SalesOrderScheduleLine | None:
    salesOrder = _to_str(record.get("salesOrder"))
    item = _normalize_numeric_id(record.get("salesOrderItem"))
    scheduleLine = _to_str(record.get("scheduleLine"))
    if not salesOrder or not item or not scheduleLine:
        return None
    return m.SalesOrderScheduleLine(
        salesOrder=salesOrder,
        item=item,
        scheduleLine=scheduleLine,
        confirmedDeliveryDate=_parse_datetime(record.get("confirmedDeliveryDate")),
        confdOrderQty=_parse_float(record.get("confdOrderQtyByMatlAvailCheck")),
    )


def _ingest_outbound_delivery_headers(
    session: Session, record: dict[str, Any]
) -> m.OutboundDeliveryHeader | None:
    deliveryDocument = _to_str(record.get("deliveryDocument"))
    if not deliveryDocument:
        return None
    return m.OutboundDeliveryHeader(
        deliveryDocument=deliveryDocument,
        pickingStatus=_to_str(record.get("overallPickingStatus")),
        goodsMovementStatus=_to_str(record.get("overallGoodsMovementStatus")),
        shippingPoint=_to_str(record.get("shippingPoint")),
    )


def _ingest_outbound_delivery_items(
    session: Session, record: dict[str, Any]
) -> m.OutboundDeliveryItem | None:
    deliveryDocument = _to_str(record.get("deliveryDocument"))
    item = _to_str(record.get("deliveryDocumentItem"))
    if not deliveryDocument or not item:
        return None
    return m.OutboundDeliveryItem(
        deliveryDocument=deliveryDocument,
        item=item,
        referenceSdDocument=_to_str(record.get("referenceSdDocument")),
        referenceSdDocumentItem=_normalize_numeric_id(record.get("referenceSdDocumentItem")),
        plant=_to_str(record.get("plant")),
        batch=_to_str(record.get("batch")),
    )


def _ingest_billing_document_headers(
    session: Session, record: dict[str, Any]
) -> m.BillingDocumentHeader | None:
    billingDocument = _to_str(record.get("billingDocument"))
    soldToParty = _to_str(record.get("soldToParty"))
    accountingDocument = _to_str(record.get("accountingDocument"))
    if not billingDocument or not soldToParty:
        return None
    return m.BillingDocumentHeader(
        billingDocument=billingDocument,
        soldToParty=soldToParty,
        companyCode=_to_str(record.get("companyCode")),
        billingDocumentDate=_parse_datetime(record.get("billingDocumentDate")),
        accountingDocument=accountingDocument,
        fiscalYear=_to_str(record.get("fiscalYear")),
        totalNetAmount=_parse_float(record.get("totalNetAmount")),
        isCancelled=_parse_bool(record.get("billingDocumentIsCancelled")),
    )


def _ingest_billing_document_items(
    session: Session, record: dict[str, Any]
) -> m.BillingDocumentItem | None:
    billingDocument = _to_str(record.get("billingDocument"))
    item = _to_str(record.get("billingDocumentItem"))
    if not billingDocument or not item:
        return None
    return m.BillingDocumentItem(
        billingDocument=billingDocument,
        item=item,
        referenceSdDocument=_to_str(record.get("referenceSdDocument")),
        referenceSdDocumentItem=_normalize_numeric_id(record.get("referenceSdDocumentItem")),
        material=_to_str(record.get("material")),
        netAmount=_parse_float(record.get("netAmount")),
    )


def _ingest_billing_document_cancellations(
    session: Session, record: dict[str, Any]
) -> m.BillingDocumentCancellation | None:
    billingDocument = _to_str(record.get("billingDocument"))
    if not billingDocument:
        return None
    return m.BillingDocumentCancellation(billingDocument=billingDocument)


def _ingest_journal_entry_items_accounts_receivable(
    session: Session, record: dict[str, Any]
) -> m.JournalEntryItemsAR | None:
    accountingDocument = _to_str(record.get("accountingDocument"))
    item = _to_str(record.get("accountingDocumentItem"))
    if not accountingDocument or not item:
        return None
    return m.JournalEntryItemsAR(
        accountingDocument=accountingDocument,
        item=item,
        customer=_to_str(record.get("customer")),
        referenceDocument=_to_str(record.get("referenceDocument")),
        companyCode=_to_str(record.get("companyCode")),
        fiscalYear=_to_str(record.get("fiscalYear")),
        postingDate=_parse_datetime(record.get("postingDate")),
        amountInCompanyCodeCurrency=_parse_float(record.get("amountInCompanyCodeCurrency")),
        glAccount=_to_str(record.get("glAccount")),
        clearingAccountingDocument=_to_str(record.get("clearingAccountingDocument")),
    )


def _ingest_payments_accounts_receivable(
    session: Session, record: dict[str, Any]
) -> m.PaymentsAccountsReceivable | None:
    accountingDocument = _to_str(record.get("accountingDocument"))
    item = _to_str(record.get("accountingDocumentItem"))
    if not accountingDocument or not item:
        return None
    return m.PaymentsAccountsReceivable(
        accountingDocument=accountingDocument,
        item=item,
        customer=_to_str(record.get("customer")),
        clearingAccountingDocument=_to_str(record.get("clearingAccountingDocument")),
        postingDate=_parse_datetime(record.get("postingDate")),
    )


# Canonical destination model m.<Entity> + mapper per input source table name.
SOURCE_TABLE_TO_MAPPER: dict[str, Callable[[Session, dict[str, Any]], Any | None]] = {
    "business_partners": _ingest_business_partners,
    "business_partner_addresses": _ingest_business_partner_addresses,
    "customer_company_assignments": _ingest_customer_company_assignments,
    "customer_sales_area_assignments": _ingest_customer_sales_area_assignments,
    "products": _ingest_products,
    "product_descriptions": _ingest_product_descriptions,
    "plants": _ingest_plants,
    "product_plants": _ingest_product_plants,
    "product_storage_locations": _ingest_product_storage_locations,
    "sales_order_headers": _ingest_sales_order_headers,
    "sales_order_items": _ingest_sales_order_items,
    "sales_order_schedule_lines": _ingest_sales_order_schedule_lines,
    "outbound_delivery_headers": _ingest_outbound_delivery_headers,
    "outbound_delivery_items": _ingest_outbound_delivery_items,
    "billing_document_headers": _ingest_billing_document_headers,
    "billing_document_items": _ingest_billing_document_items,
    "billing_document_cancellations": _ingest_billing_document_cancellations,
    # Raw folder name in the dataset uses the long form.
    "journal_entry_items_accounts_receivable": _ingest_journal_entry_items_accounts_receivable,
    "payments_accounts_receivable": _ingest_payments_accounts_receivable,
}


def ingest_jsonl_dataset(
    session: Session,
    dataset_root: Path,
    *,
    truncate_graph_edges: bool = True,
    logger: logging.Logger | None = None,
) -> None:
    """
    Ingest JSONL files under `dataset_root` folder-wise and upsert into the relational schema.

    Rerunnable:
    - entity tables use PK-based SQLAlchemy merge (no duplicates)
    - graph_edges are rebuilt separately (optional).
    """
    log = logger or logging.getLogger(__name__)

    if not dataset_root.exists() or not dataset_root.is_dir():
        raise FileNotFoundError(f"dataset_root not found or not a directory: {dataset_root}")

    table_dirs = _discover_jsonl_table_dirs(dataset_root)
    if not table_dirs:
        log.warning("No jsonl-containing directories found under %s", dataset_root)
        return

    total_rows = 0
    total_skipped = 0
    total_errors = 0

    for folder in table_dirs:
        source_table = folder.name
        mapper = SOURCE_TABLE_TO_MAPPER.get(source_table)
        if mapper is None:
            log.info("Skipping unknown table dir: %s", folder)
            continue

        jsonl_files = sorted(folder.glob("*.jsonl"))
        if not jsonl_files:
            continue

        log.info("Ingesting table '%s' from %d file(s)", source_table, len(jsonl_files))

        # Each file is an independent transaction boundary for clearer failure isolation.
        for jf in jsonl_files:
            file_rows = 0
            file_errors = 0
            file_skipped = 0

            with session.begin():
                with jf.open("r", encoding="utf-8", errors="replace") as f:
                    for line_no, line in enumerate(f, 1):
                        raw = line.strip()
                        if not raw:
                            continue

                        try:
                            record = json.loads(raw)
                        except json.JSONDecodeError as e:
                            file_errors += 1
                            log.error(
                                "Invalid JSON table=%s file=%s line=%d: %s",
                                source_table,
                                jf.name,
                                line_no,
                                e,
                            )
                            continue

                        if not isinstance(record, dict):
                            file_errors += 1
                            log.error(
                                "Non-object JSON table=%s file=%s line=%d: got %s",
                                source_table,
                                jf.name,
                                line_no,
                                type(record).__name__,
                            )
                            continue

                        obj = mapper(session, record)
                        if obj is None:
                            file_skipped += 1
                            required = SOURCE_TABLE_REQUIRED_PKS_RAW.get(source_table, [])
                            missing = [
                                k
                                for k in required
                                if _to_str(record.get(k)) is None
                            ]
                            if missing:
                                log.warning(
                                    "Skip missing PK table=%s file=%s line=%d missing=%s",
                                    source_table,
                                    jf.name,
                                    line_no,
                                    ",".join(missing),
                                )
                            continue

                        try:
                            _upsert_row(session, obj)
                        except Exception as e:
                            file_errors += 1
                            log.error(
                                "DB upsert failed table=%s file=%s line=%d: %s",
                                source_table,
                                jf.name,
                                line_no,
                                e,
                                exc_info=True,
                            )
                            # Continue other rows within the transaction.
                            continue
                        file_rows += 1

            total_rows += file_rows
            total_skipped += file_skipped
            total_errors += file_errors

            if file_errors:
                log.warning(
                    "Finished file with errors: table=%s file=%s ok_rows=%d skipped=%d errors=%d",
                    source_table,
                    jf.name,
                    file_rows,
                    file_skipped,
                    file_errors,
                )

    log.info(
        "Ingestion complete: total_rows_upserted=%d skipped_due_to_missing_pk=%d total_errors=%d",
        total_rows,
        total_skipped,
        total_errors,
    )

    # Canonicalize billing_document_items reference mapping.
    # Spec hazard: billing_document_items.referenceSdDocument may point to deliveryDocument (8xxxxxxx)
    # instead of sales order. If so, resolve it via outbound_delivery_items reference fields.
    _canonicalize_billing_reference_to_sales_order(session, log=log)

    if truncate_graph_edges:
        log.info("Note: graph_edges rebuild should be triggered by build_graph_edges().")


def _canonicalize_billing_reference_to_sales_order(session: Session, *, log: logging.Logger) -> None:
    billing_items = session.execute(
        select(m.BillingDocumentItem).where(
            m.BillingDocumentItem.referenceSdDocument.is_not(None),
            m.BillingDocumentItem.referenceSdDocumentItem.is_not(None),
        )
    ).scalars().all()

    updated = 0
    for bi in billing_items:
        ref_sd = bi.referenceSdDocument
        ref_item = bi.referenceSdDocumentItem
        if ref_sd is None or ref_item is None:
            continue
        sd_int = None
        if isinstance(ref_sd, str) and ref_sd.isdigit():
            sd_int = int(ref_sd)
        if sd_int is None:
            continue

        # If this looks like a deliveryDocument (>= 80000000), resolve via outbound_delivery_items.
        if sd_int >= 80000000:
            # outbound_delivery_items.primary keys: (deliveryDocument, deliveryDocumentItem) -> model (deliveryDocument, item)
            delivery_item_candidates: set[str] = {ref_item}
            # Dataset appears to use zero-padded 6-digit delivery document items (e.g. "000010").
            if isinstance(ref_item, str) and ref_item.isdigit():
                delivery_item_candidates.add(ref_item.zfill(6))

            out_items = session.execute(
                select(m.OutboundDeliveryItem).where(
                    m.OutboundDeliveryItem.deliveryDocument == ref_sd,
                    m.OutboundDeliveryItem.item.in_(sorted(delivery_item_candidates)),
                )
            ).scalars().all()
            if not out_items:
                continue

            # If multiple, take the mode for stability.
            so_ids = [oi.referenceSdDocument for oi in out_items if oi.referenceSdDocument is not None]
            so_item_ids = [oi.referenceSdDocumentItem for oi in out_items if oi.referenceSdDocumentItem is not None]
            if not so_ids or not so_item_ids:
                continue

            # Choose deterministic mode.
            def mode_str(vals: list[str | None]) -> str | None:
                counts: dict[str, int] = {}
                for v in vals:
                    if v is None:
                        continue
                    counts[v] = counts.get(v, 0) + 1
                if not counts:
                    return None
                maxc = max(counts.values())
                return sorted([k for k, c in counts.items() if c == maxc])[0]

            resolved_sd = mode_str(so_ids)
            resolved_item = mode_str(so_item_ids)
            if resolved_sd is None or resolved_item is None:
                continue

            if bi.referenceSdDocument != resolved_sd or bi.referenceSdDocumentItem != resolved_item:
                bi.referenceSdDocument = resolved_sd
                bi.referenceSdDocumentItem = resolved_item
                updated += 1

    if updated:
        session.commit()
    log.info("Canonicalized billing references: updated_rows=%d", updated)

