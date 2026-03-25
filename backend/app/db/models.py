from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, ForeignKeyConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    source_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(50), primary_key=True)
    target_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    edge_type: Mapped[str] = mapped_column(String(50), primary_key=True)


class BusinessPartner(Base):
    __tablename__ = "business_partners"

    businessPartner: Mapped[str] = mapped_column(String(32), primary_key=True)
    fullName: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    isBlocked: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    isMarkedForArchiving: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Optional fields referenced by the graph spec's node properties.
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    grouping: Mapped[str | None] = mapped_column(String(50), nullable=True)


class BusinessPartnerAddress(Base):
    __tablename__ = "business_partner_addresses"

    businessPartner: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("business_partners.businessPartner"),
        primary_key=True,
    )
    addressId: Mapped[str] = mapped_column(String(32), primary_key=True)

    cityName: Mapped[str | None] = mapped_column(String(100), nullable=True)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str | None] = mapped_column(String(50), nullable=True)
    postalCode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    validityStartDate: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)


class CustomerCompanyAssignment(Base):
    __tablename__ = "customer_company_assignments"

    customer: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("business_partners.businessPartner"),
        primary_key=True,
    )
    companyCode: Mapped[str] = mapped_column(String(20), primary_key=True)

    reconciliationAccount: Mapped[str | None] = mapped_column(String(50), nullable=True)
    paymentTerms: Mapped[str | None] = mapped_column(String(50), nullable=True)
    deletionIndicator: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class CustomerSalesAreaAssignment(Base):
    __tablename__ = "customer_sales_area_assignments"

    customer: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("business_partners.businessPartner"),
        primary_key=True,
    )
    salesOrg: Mapped[str] = mapped_column(String(10), primary_key=True)
    distCh: Mapped[str] = mapped_column(String(10), primary_key=True)
    division: Mapped[str] = mapped_column(String(10), primary_key=True)

    currency: Mapped[str | None] = mapped_column(String(5), nullable=True)
    incoterms: Mapped[str | None] = mapped_column(String(20), nullable=True)
    shippingCondition: Mapped[str | None] = mapped_column(String(50), nullable=True)
    paymentTerms: Mapped[str | None] = mapped_column(String(50), nullable=True)


class Product(Base):
    __tablename__ = "products"

    product: Mapped[str] = mapped_column(String(32), primary_key=True)
    productType: Mapped[str | None] = mapped_column(String(50), nullable=True)
    productGroup: Mapped[str | None] = mapped_column(String(50), nullable=True)
    division: Mapped[str | None] = mapped_column(String(20), nullable=True)
    isMarkedForDeletion: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class ProductDescription(Base):
    __tablename__ = "product_descriptions"

    product: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("products.product"),
        primary_key=True,
    )
    language: Mapped[str] = mapped_column(String(10), primary_key=True)

    productDescription: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Plant(Base):
    __tablename__ = "plants"

    plant: Mapped[str] = mapped_column(String(32), primary_key=True)
    plantName: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salesOrganization: Mapped[str | None] = mapped_column(String(20), nullable=True)
    valuationArea: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ProductPlant(Base):
    __tablename__ = "product_plants"

    product: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("products.product"),
        primary_key=True,
    )
    plant: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("plants.plant"),
        primary_key=True,
    )

    mrpType: Mapped[str | None] = mapped_column(String(20), nullable=True)
    profitCenter: Mapped[str | None] = mapped_column(String(30), nullable=True)
    countryOfOrigin: Mapped[str | None] = mapped_column(String(50), nullable=True)


class ProductStorageLocation(Base):
    __tablename__ = "product_storage_locations"

    product: Mapped[str] = mapped_column(String(32), primary_key=True)
    plant: Mapped[str] = mapped_column(String(32), primary_key=True)
    storageLocation: Mapped[str] = mapped_column(String(32), primary_key=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["product", "plant"],
            ["product_plants.product", "product_plants.plant"],
        ),
    )

    physicalInventoryBlockInd: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dateOfLastPostedCnt: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)


class SalesOrderHeader(Base):
    __tablename__ = "sales_order_headers"

    salesOrder: Mapped[str] = mapped_column(String(32), primary_key=True)
    soldToParty: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("business_partners.businessPartner"),
        index=True,
    )
    totalNetAmount: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    creationDate: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)


class SalesOrderItem(Base):
    __tablename__ = "sales_order_items"

    salesOrder: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("sales_order_headers.salesOrder"),
        primary_key=True,
    )
    item: Mapped[str] = mapped_column(String(20), primary_key=True)

    material: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("products.product"),
        index=True,
    )
    netAmount: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    productionPlant: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("plants.plant"),
        index=True,
    )


class SalesOrderScheduleLine(Base):
    __tablename__ = "sales_order_schedule_lines"

    salesOrder: Mapped[str] = mapped_column(String(32), primary_key=True)
    item: Mapped[str] = mapped_column(String(20), primary_key=True)
    scheduleLine: Mapped[str] = mapped_column(String(20), primary_key=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["salesOrder", "item"],
            ["sales_order_items.salesOrder", "sales_order_items.item"],
        ),
    )

    confirmedDeliveryDate: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    confdOrderQty: Mapped[float | None] = mapped_column(Float, nullable=True)


class OutboundDeliveryHeader(Base):
    __tablename__ = "outbound_delivery_headers"

    deliveryDocument: Mapped[str] = mapped_column(String(32), primary_key=True)
    pickingStatus: Mapped[str | None] = mapped_column(String(50), nullable=True)
    goodsMovementStatus: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shippingPoint: Mapped[str | None] = mapped_column(String(50), nullable=True)


class OutboundDeliveryItem(Base):
    __tablename__ = "outbound_delivery_items"

    deliveryDocument: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("outbound_delivery_headers.deliveryDocument"),
        primary_key=True,
    )
    item: Mapped[str] = mapped_column(String(20), primary_key=True)

    # Ambiguity is handled at ingestion time; this FK is "best-effort" based on the spec.
    referenceSdDocument: Mapped[str | None] = mapped_column(String(32), nullable=True)
    referenceSdDocumentItem: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plant: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("plants.plant"),
        nullable=True,
    )
    batch: Mapped[str | None] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["referenceSdDocument", "referenceSdDocumentItem"],
            ["sales_order_items.salesOrder", "sales_order_items.item"],
        ),
    )


class BillingDocumentHeader(Base):
    __tablename__ = "billing_document_headers"

    billingDocument: Mapped[str] = mapped_column(String(32), primary_key=True)
    soldToParty: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("business_partners.businessPartner"),
        index=True,
    )
    companyCode: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    billingDocumentDate: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    accountingDocument: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fiscalYear: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    totalNetAmount: Mapped[float | None] = mapped_column(Float, nullable=True)
    isCancelled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class BillingDocumentItem(Base):
    __tablename__ = "billing_document_items"

    billingDocument: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("billing_document_headers.billingDocument"),
        primary_key=True,
    )
    item: Mapped[str] = mapped_column(String(20), primary_key=True)

    # Ambiguity is handled at ingestion time; this composite FK models the "assumed" mapping.
    referenceSdDocument: Mapped[str | None] = mapped_column(String(32), nullable=True)
    referenceSdDocumentItem: Mapped[str | None] = mapped_column(String(20), nullable=True)
    material: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("products.product"),
        nullable=True,
        index=True,
    )
    netAmount: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["referenceSdDocument", "referenceSdDocumentItem"],
            ["sales_order_items.salesOrder", "sales_order_items.item"],
        ),
    )


class BillingDocumentCancellation(Base):
    __tablename__ = "billing_document_cancellations"

    billingDocument: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("billing_document_headers.billingDocument"),
        primary_key=True,
    )


class JournalEntryItemsAR(Base):
    __tablename__ = "journal_entry_items_ar"

    accountingDocument: Mapped[str] = mapped_column(String(32), primary_key=True)
    item: Mapped[str] = mapped_column(String(20), primary_key=True)

    customer: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("business_partners.businessPartner"),
        index=True,
    )
    referenceDocument: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("billing_document_headers.billingDocument"),
        nullable=True,
    )
    companyCode: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    fiscalYear: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    postingDate: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True, index=True)
    amountInCompanyCodeCurrency: Mapped[float | None] = mapped_column(Float, nullable=True)
    glAccount: Mapped[str | None] = mapped_column(String(20), nullable=True)
    clearingAccountingDocument: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )


class PaymentsAccountsReceivable(Base):
    __tablename__ = "payments_accounts_receivable"

    accountingDocument: Mapped[str] = mapped_column(String(32), primary_key=True)
    item: Mapped[str] = mapped_column(String(20), primary_key=True)

    customer: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("business_partners.businessPartner"),
        index=True,
    )
    clearingAccountingDocument: Mapped[str | None] = mapped_column(String(32), nullable=True)
    postingDate: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)


