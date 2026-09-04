"""SQLAlchemy models — import all to ensure they are registered in Base.metadata."""

from cocina_control.models.customer import Customer, CustomerAddress
from cocina_control.models.delivery import Delivery, DeliveryItem
from cocina_control.models.delivery_order import DeliveryOrder, DeliveryOrderItem
from cocina_control.models.delivery_trip import DeliveryTrip
from cocina_control.models.delivery_zone import DeliveryZone
from cocina_control.models.inventory import InventoryCount, InventoryCountItem
from cocina_control.models.option_group import OptionGroup, OptionItem, ProductOptionGroup
from cocina_control.models.payment import Payment
from cocina_control.models.product import Product
from cocina_control.models.promotion import Promotion
from cocina_control.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderItemCost,
    PurchaseOrderStatusEvent,
)
from cocina_control.models.recipe import DeliveryOrderItemIngredient, ProductRecipe
from cocina_control.models.sales_order import (
    SalesOrder,
    SalesOrderItem,
    SalesOrderItemOption,
)
from cocina_control.models.service_principal import ServicePrincipal
from cocina_control.models.supplier import Supplier
from cocina_control.models.user import User

__all__ = [
    "Customer",
    "CustomerAddress",
    "Delivery",
    "DeliveryItem",
    "DeliveryOrder",
    "DeliveryOrderItem",
    "DeliveryOrderItemIngredient",
    "DeliveryTrip",
    "DeliveryZone",
    "InventoryCount",
    "InventoryCountItem",
    "OptionGroup",
    "OptionItem",
    "Payment",
    "Product",
    "ProductOptionGroup",
    "Promotion",
    "ProductRecipe",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "PurchaseOrderItemCost",
    "PurchaseOrderStatusEvent",
    "SalesOrder",
    "SalesOrderItem",
    "SalesOrderItemOption",
    "ServicePrincipal",
    "Supplier",
    "User",
]
