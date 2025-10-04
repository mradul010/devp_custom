# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import frappe
from frappe.utils import get_datetime

@frappe.whitelist()
def get_item_names_for_customer_batch(item_codes, customer=None):
    """
    Returns mapping per item_code:
      { mapping_name, customer_item_name, customer_description, source }
    Accepts JSON array string or comma separated.
    """
    import json
    if not item_codes:
        return {}

    # parse input
    if isinstance(item_codes, str):
        try:
            item_list = json.loads(item_codes)
            if not isinstance(item_list, list):
                raise
        except Exception:
            item_list = [c.strip() for c in item_codes.split(",") if c.strip()]
    else:
        item_list = list(item_codes)

    if not item_list:
        return {}

    rows = frappe.get_all(
        "Item Customer Mapping",
        filters=[["item", "in", item_list], ["is_active", "=", 1]],
        fields=["name", "item", "customer", "customer_group", "customer_item_name",
                "customer_description", "effective_from", "priority", "modified"]
    )

    grouped = {}
    for r in rows:
        grouped.setdefault(r["item"], []).append(r)

    cust_group = None
    if customer:
        cust_group = frappe.db.get_value("Customer", customer, "customer_group")

    def choose(rows_list):
        if not rows_list:
            return None
        def key(rr):
            pr = rr.get("priority") or 999
            mod_ts = 0
            try:
                mod_ts = get_datetime(rr.get("modified")).timestamp() if rr.get("modified") else 0
            except Exception:
                mod_ts = 0
            return (pr, -mod_ts)
        return sorted(rows_list, key=key)[0]

    result = {}
    for item in item_list:
        rs = grouped.get(item, []) or []
        customer_rows = [r for r in rs if r.get("customer") and customer and r.get("customer") == customer]
        group_rows = [r for r in rs if r.get("customer_group") and cust_group and r.get("customer_group") == cust_group]
        default_rows = [r for r in rs if not r.get("customer") and not r.get("customer_group")]
        chosen = choose(customer_rows) or choose(group_rows) or choose(default_rows)
        if chosen:
            result[item] = {
                "mapping_name": chosen.get("name"),
                "customer_item_name": chosen.get("customer_item_name") or "",
                "customer_description": chosen.get("customer_description") or "",
                "source": "customer" if chosen.get("customer") else ("group" if chosen.get("customer_group") else "default")
            }
        else:
            result[item] = {}
    return result

@frappe.whitelist()
def get_all_mappings_for_item(item_code):
    """
    Return all active mappings (serializes datetimes to ISO).
    """
    import datetime
    rows = frappe.get_all(
        "Item Customer Mapping",
        filters={"item": item_code, "is_active": 1},
        fields=["name", "item", "customer", "customer_group", "customer_item_name", "customer_description", "effective_from", "priority", "modified"],
        order_by="priority asc, modified desc"
    )

    def js(v):
        if isinstance(v, (datetime.date, datetime.datetime)):
            return v.isoformat()
        return v

    return [{k: js(v) for k, v in r.items()} for r in rows]

def apply_customer_item_names(doc, method=None):
    """
    Hook: before_save on Sales Order / Quotation / Sales Invoice.
    Applies mapping_name -> set customer_mapping link, and populates fields.
    """
    customer = getattr(doc, "customer", None)
    if not getattr(doc, "items", None):
        return

    item_codes = [d.item_code for d in doc.items if getattr(d, "item_code", None)]
    if not item_codes:
        return

    mapping = get_item_names_for_customer_batch(item_codes, customer=customer)

    for d in doc.items:
        if not getattr(d, "item_code", None):
            continue
        res = mapping.get(d.item_code) or {}
        if res.get("mapping_name"):
            try:
                d.customer_mapping = res.get("mapping_name")
            except Exception:
                pass
        if res.get("customer_item_name"):
            try:
                d.customer_item_name = res.get("customer_item_name")
            except Exception:
                pass
            try:
                d.item_name = res.get("customer_item_name")
            except Exception:
                pass
        if res.get("customer_description"):
            try:
                d.customer_description = res.get("customer_description")
            except Exception:
                pass
            try:
                d.description = res.get("customer_description")
            except Exception:
                pass
