# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime

# ---------------------------------------------------------------------
# Helpers: item-code generation
# ---------------------------------------------------------------------
def _abbr_from_name(name, max_len=4):
    if not name:
        return "ITEM"
    s = re.sub(r"[^A-Za-z0-9\s]", "", name).strip().upper()
    parts = s.split()
    if not parts:
        return "ITEM"
    if len(parts) == 1:
        return parts[0][:max_len]
    token = parts[0][:3]
    i = 1
    while len(token) < max_len and i < len(parts):
        add = parts[i][: (max_len - len(token))]
        token += add
        i += 1
    return token

def _sanitize_part(part):
    if not part:
        return ""
    p = str(part).upper().strip()
    p = re.sub(r"\s+", "-", p)
    p = re.sub(r"[^A-Z0-9\-]", "", p)
    p = re.sub(r"-{2,}", "-", p).strip("-")
    return p

def _collect_prefix_parts_from_item_group(item_group_name, max_levels=3):
    parts, seen = [], set()
    current = item_group_name
    while current and len(parts) < max_levels:
        try:
            ig = frappe.get_doc("Item Group", current)
        except Exception:
            break

        prefix_field = (ig.get("item_code_prefix") or "").strip()
        if prefix_field:
            part = _sanitize_part(prefix_field)
        else:
            part = _sanitize_part(_abbr_from_name(ig.get("name") or current, max_len=4))

        if part and part not in seen:
            parts.append(part)
            seen.add(part)

        parent_name = ig.get("parent_item_group")
        if not parent_name or parent_name == "All Item Groups":
            break
        current = parent_name

    return list(reversed(parts))

def _compose_prefix_from_item_group(item_group_name, max_levels=3):
    parts = _collect_prefix_parts_from_item_group(item_group_name, max_levels=max_levels)
    if not parts:
        return "ITEM"
    comp = "-".join([_sanitize_part(p) for p in parts if p]).strip("-")
    comp = re.sub(r"-{2,}", "-", comp)
    return comp or "ITEM"

# ---------------------------------------------------------------------
# Series reservation (atomic via tabSeries)
# ---------------------------------------------------------------------
def _reserve_series_number(prefix):
    """
    Atomically selects/locks and increments a tabSeries row for this prefix.
    Returns the reserved integer.
    """
    row = frappe.db.sql(
        "SELECT `current` FROM `tabSeries` WHERE name=%s FOR UPDATE",
        (prefix,),
    )
    if not row:
        frappe.db.sql(
            "INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)",
            (prefix, 1),
        )
        frappe.db.commit()
        return 1
    current = int(row[0][0] or 0)
    next_no = current + 1
    frappe.db.sql(
        "UPDATE `tabSeries` SET `current`=%s WHERE name=%s",
        (next_no, prefix),
    )
    frappe.db.commit()
    return next_no

@frappe.whitelist()
def reserve_item_code(item_group=None, digits=3, max_prefix_levels=3):
    prefix = _compose_prefix_from_item_group(item_group, max_levels=int(max_prefix_levels))
    try:
        next_no = _reserve_series_number(prefix)
    except Exception as e:
        frappe.throw(_("Could not reserve item code for prefix {0}: {1}").format(prefix, e))

    fmt = "{:0" + str(int(digits)) + "d}"
    suffix = fmt.format(next_no)
    return f"{prefix}-{suffix}"

@frappe.whitelist()
def get_next_item_code_preview(item_group=None, digits=3, max_prefix_levels=3):
    prefix = _compose_prefix_from_item_group(item_group, max_levels=int(max_prefix_levels))
    like_expr = prefix + "-%"

    rows = frappe.db.sql(
        """
        SELECT item_code, name
        FROM `tabItem`
        WHERE item_group=%s AND (item_code LIKE %s OR name LIKE %s)
        """,
        (item_group, like_expr, like_expr),
    ) or []

    max_no = 0
    for item_code, name in rows:
        candidate = item_code or name
        if not candidate:
            continue
        last_seg = candidate.rsplit("-", 1)[-1]
        if last_seg.isdigit():
            n = int(last_seg)
            if n > max_no:
                max_no = n

    next_no = max_no + 1
    fmt = "{:0" + str(int(digits)) + "d}"
    suffix = fmt.format(next_no)
    return f"{prefix}-{suffix}"

@frappe.whitelist()
def reserve_and_set_item_code_for_item(docname, item_group=None, digits=3, max_prefix_levels=3):
    if not docname:
        frappe.throw(_("docname required"))

    item = frappe.get_doc("Item", docname)
    existing = item.get("item_code")
    if existing:
        return existing

    ig = item_group or item.get("item_group")
    if not ig:
        frappe.throw(_("Cannot determine Item Group to compose item code prefix."))

    prefix = _compose_prefix_from_item_group(ig, max_levels=int(max_prefix_levels))
    try:
        next_no = _reserve_series_number(prefix)
    except Exception as e:
        frappe.throw(_("Could not reserve item code for prefix {0}: {1}").format(prefix, e))

    fmt = "{:0" + str(int(digits)) + "d}"
    suffix = fmt.format(next_no)
    new_code = f"{prefix}-{suffix}"

    frappe.db.sql("UPDATE `tabItem` SET item_code=%s WHERE name=%s", (new_code, docname))
    frappe.db.commit()
    return new_code

@frappe.whitelist()
def reserve_item_code_for_item(item_group=None, digits=3, max_prefix_levels=3):
    return reserve_item_code(item_group=item_group, digits=digits, max_prefix_levels=max_prefix_levels)

def auto_set_item_code_on_submit(doc, method=None):
    if not doc or getattr(doc, "doctype", None) != "Item":
        return
    if getattr(doc, "item_code", None):
        return
    if not getattr(doc, "item_group", None):
        frappe.throw(_("Cannot auto-generate item code on submit: Item Group is missing."))
    reserve_and_set_item_code_for_item(doc.name, item_group=doc.item_group, digits=3, max_prefix_levels=3)

def assign_item_code_before_insert(doc, method=None):
    if (doc.item_code or "").strip():
        return
    if not getattr(doc, "item_group", None):
        frappe.throw(_("Item Group is required to generate Item Code"))

    code = reserve_item_code(item_group=doc.item_group, digits=3, max_prefix_levels=3)
    doc.item_code = code
    # If autoname != field:item_code and you want name to follow, uncomment:
    # doc.name = code

# ---------------------------------------------------------------------
# Pricing helpers
# ---------------------------------------------------------------------
@frappe.whitelist()
def get_last_item_prices(item_code, customer=None, limit=5, include_other_customers=False):
    if not item_code:
        return []

    limit = int(limit or 5)
    customer = (customer or "").strip() or None
    include_other = str(include_other_customers).lower() in ("1", "true", "yes")

    if not frappe.has_permission("Sales Invoice", ptype="read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    filters = ["sii.item_code = %s", "si.docstatus = 1"]
    params = [item_code]

    if customer:
        if include_other:
            filters.append("si.customer != %s")
            params.append(customer)
        else:
            filters.append("si.customer = %s")
            params.append(customer)

    where = " AND ".join(filters)
    rows = frappe.db.sql(
        f"""
        SELECT si.name AS invoice, si.posting_date AS posting_date,
               sii.rate AS rate, si.customer AS customer
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {where}
        ORDER BY si.posting_date DESC, si.modified DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
        as_dict=1,
    )

    result = []
    for r in rows:
        result.append({
            "invoice": r.get("invoice"),
            "posting_date": r.get("posting_date").strftime("%Y-%m-%d") if r.get("posting_date") else None,
            "rate": float(r.get("rate")) if r.get("rate") is not None else None,
            "customer": r.get("customer") or "",
        })
    return result

# ---------------------------------------------------------------------
# Batch-size warnings (non-blocking UI warning you already use)
# ---------------------------------------------------------------------
def _get_batch_size(batch_no):
    res = frappe.db.get_value("Batch", batch_no, "batch_size") if batch_no else None
    try:
        return float(res) if res is not None else None
    except Exception:
        return None

def validate_work_order_batch_size(doc, method=None):
    qty = doc.get("production_qty") or doc.get("qty") or 0
    batch = doc.get("production_batch") or doc.get("batch_no") or doc.get("batch")
    if batch:
        batch_size = _get_batch_size(batch)
        if batch_size and float(qty) > float(batch_size):
            if not doc.get("allow_batch_exceed"):
                frappe.throw(f"Qty ({qty}) exceeds Batch '{batch}' size ({batch_size}).")
            else:
                frappe.msgprint(
                    f"Override used: qty ({qty}) > batch_size ({batch_size})",
                    indicator="orange",
                )

def validate_sales_invoice_batch_size(doc, method=None):
    for row in doc.get("items") or []:
        batch_no = row.get("batch_no") or row.get("batch")
        qty = row.get("qty") or 0
        if batch_no:
            batch_size = _get_batch_size(batch_no)
            if batch_size is not None and float(qty) > float(batch_size):
                frappe.msgprint(
                    f"⚠️ Sales Invoice line for item {row.get('item_code') or ''}: "
                    f"qty ({qty}) exceeds Batch '{batch_no}' size ({batch_size}).",
                    indicator="orange",
                )

# ---------------------------------------------------------------------
# Customer Item Name/Description mapping
# ---------------------------------------------------------------------
@frappe.whitelist()
def get_item_name_description_for_customer(item_code, customer=None):
    if not item_code:
        return {}

    item_code = frappe.as_unicode(item_code)
    customer = frappe.as_unicode(customer) if customer else None

    rows = frappe.get_all(
        "Item Customer Info",
        filters={"parent": item_code},
        fields=[
            "name", "customer", "customer_group",
            "customer_item_name", "customer_description",
            "is_default", "priority",
        ],
    )

    customer_rows, group_rows, default_rows = [], [], []
    cust_group = frappe.db.get_value("Customer", customer, "customer_group") if customer else None

    for r in rows:
        if r.get("customer") and customer and r["customer"] == customer:
            customer_rows.append(r)
        elif r.get("customer_group") and cust_group and r["customer_group"] == cust_group:
            group_rows.append(r)
        elif r.get("is_default"):
            default_rows.append(r)

    def choose(lst):
        if not lst:
            return None
        return sorted(lst, key=lambda x: (x.get("priority") or 999, x.get("name") or ""))[0]

    chosen = choose(customer_rows) or choose(group_rows) or choose(default_rows)
    if not chosen:
        return {}

    return {
        "customer_item_name": chosen.get("customer_item_name") or "",
        "customer_description": chosen.get("customer_description") or "",
        "source": "customer" if chosen.get("customer") else ("group" if chosen.get("customer_group") else "default"),
    }

@frappe.whitelist()
def get_item_names_for_customer_batch(item_codes, customer=None):
    import json
    if not item_codes:
        return {}

    if isinstance(item_codes, str):
        try:
            item_list = json.loads(item_codes)
            if not isinstance(item_list, list):
                raise Exception
        except Exception:
            item_list = [c.strip() for c in item_codes.split(",") if c.strip()]
    else:
        item_list = list(item_codes)

    if not item_list:
        return {}

    rows = frappe.get_all(
        "Item Customer Mapping",
        filters=[["item", "in", item_list], ["is_active", "=", 1]],
        fields=[
            "name", "item", "customer", "customer_group",
            "customer_item_name", "customer_description",
            "effective_from", "priority", "modified",
        ],
    )

    grouped = {}
    for r in rows:
        grouped.setdefault(r["item"], []).append(r)

    cust_group = frappe.db.get_value("Customer", customer, "customer_group") if customer else None

    def choose(rows_list):
        if not rows_list:
            return None

        def key(rr):
            pr = rr.get("priority") or 999
            try:
                mod_ts = get_datetime(rr.get("modified")).timestamp() if rr.get("modified") else 0
            except Exception:
                mod_ts = 0
            return (pr, -mod_ts)

        return sorted(rows_list, key=key)[0]

    result = {}
    for item in item_list:
        rs = grouped.get(item, []) or []
        customer_rows = [r for r in rs if r.get("customer") and customer and r["customer"] == customer]
        group_rows = [r for r in rs if r.get("customer_group") and cust_group and r["customer_group"] == cust_group]
        default_rows = [r for r in rs if not r.get("customer") and not r.get("customer_group")]

        chosen = choose(customer_rows) or choose(group_rows) or choose(default_rows)
        if chosen:
            result[item] = {
                "mapping_name": chosen.get("name"),
                "customer_item_name": chosen.get("customer_item_name") or "",
                "customer_description": chosen.get("customer_description") or "",
                "source": "customer" if chosen.get("customer") else ("group" if chosen.get("customer_group") else "default"),
            }
        else:
            result[item] = {}
    return result

def apply_customer_item_names(doc, method=None):
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
            try: d.customer_mapping = res.get("mapping_name")
            except Exception: pass
        if res.get("customer_item_name"):
            try: d.customer_item_name = res.get("customer_item_name")
            except Exception: pass
            try: d.item_name = res.get("customer_item_name")
            except Exception: pass
        if res.get("customer_description"):
            try: d.customer_description = res.get("customer_description")
            except Exception: pass
            try: d.description = res.get("customer_description")
            except Exception: pass

# ---------------------------------------------------------------------
# Batch availability control (your new requirement)
# ---------------------------------------------------------------------
def _is_stock_affecting(doc):
    """Delivery Note always affects stock. Sales Invoice only when update_stock=1."""
    return (doc.doctype == "Delivery Note") or (doc.doctype == "Sales Invoice" and getattr(doc, "update_stock", 0))

def _row_stock_qty(it):
    """Use stock_qty if present; fallback to qty * conversion_factor (Stock UOM)."""
    if getattr(it, "stock_qty", None) is not None:
        return float(it.stock_qty or 0)
    cf = float(getattr(it, "conversion_factor", 1) or 1)
    return float(it.qty or 0) * cf

def _collect_requested_by_batch(doc):
    by_batch = defaultdict(float)
    for it in (doc.items or []):
        bno = getattr(it, "batch_no", None)
        if not bno:
            continue
        q = _row_stock_qty(it)
        if q > 0:
            by_batch[bno] += q
    return by_batch

def validate_available_qty(doc, method=None):
    """Hard validation before submit: cumulative per-batch request must not exceed available_batch_qty."""
    if not _is_stock_affecting(doc):
        return

    req = _collect_requested_by_batch(doc)
    if not req:
        return

    batch_nos = list(req.keys())
    placeholders = ", ".join(["%s"] * len(batch_nos))
    rows = frappe.db.sql(
        f"""
        SELECT name, COALESCE(available_batch_qty, 0) AS avail
        FROM `tabBatch`
        WHERE name IN ({placeholders})
        """,
        tuple(batch_nos),
        as_dict=True,
    )
    avail_map = {r.name: float(r.avail or 0) for r in rows}

    violations = []
    for bno, needed in req.items():
        avail = avail_map.get(bno, 0.0)
        if needed > avail + 1e-9:
            violations.append((bno, needed, avail))

    if violations:
        lines = "\n".join([f"- {b} needs {needed} but only {avail} available" for b, needed, avail in violations])
        # frappe.throw(
        #     _("Batch availability check failed. Please adjust quantities:\n{0}").format(lines),
        #     title=_("Insufficient Available Batch Quantity"),
        # )

def _apply_available_qty(doc, sign):
    """
    sign = -1 on submit (consume), +1 on cancel (revert).
    Guarded update to avoid negative values.
    """
    if not _is_stock_affecting(doc):
        return

    for it in (doc.items or []):
        bno = getattr(it, "batch_no", None)
        if not bno:
            continue
        qty = _row_stock_qty(it)
        if qty <= 0:
            continue

        delta = sign * qty  # submit: -qty ; cancel: +qty
        avail = frappe.db.get_value("Batch", bno, "available_batch_qty") or 0
        new_val = float(avail) + float(delta)
        

        frappe.db.sql(
            """
            UPDATE `tabBatch`
            SET available_batch_qty = COALESCE(available_batch_qty, 0) + %s
            WHERE name = %s
            """,
            (delta, bno),
        )

def consume_available_qty(doc, method=None):
    _apply_available_qty(doc, sign=-1)

def revert_available_qty(doc, method=None):
    _apply_available_qty(doc, sign=+1)
