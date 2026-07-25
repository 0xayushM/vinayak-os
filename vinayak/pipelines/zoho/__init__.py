"""Zoho Books pipelines — the second source family, writing zb_* raw tables."""
from vinayak.pipelines.zoho.contacts import ZohoContactsPipeline
from vinayak.pipelines.zoho.invoices import ZohoInvoicesPipeline
from vinayak.pipelines.zoho.bills import ZohoBillsPipeline
from vinayak.pipelines.zoho.items import ZohoItemsPipeline

ALL_ZOHO_PIPELINES = [
    ZohoContactsPipeline, ZohoInvoicesPipeline, ZohoBillsPipeline, ZohoItemsPipeline,
]
