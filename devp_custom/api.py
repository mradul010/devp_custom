import frappe
import re
from frappe import _
from frappe.utils import now_datetime

# ---------------------------------------------------------------------
# Item code generation & reservation helpers (unchanged helpers kept)
# ---------------------------------------------------------------------
def _abbr_from_name(name, max_len=4):
    if not name:
        return "ITEM"
    s = re.sub(r'[^A-Za-z0-9\s]', '', name).strip().upper()
    parts = s.split()
    if len(parts) == 0:
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
    p = re.sub(r'\s+', '-', p)
    p = re.sub(r'[^A-Z0-9\-]', '', p)
    p = re.sub(r'-{2,}', '-', p).strip('-')
    return p

def _collect_prefix_parts_from_item_group(item_group_name, max_levels=3):
    parts = []
    seen = set()
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
            part = _abbr_from_name(ig.get("name") or ig.get("item_group_name") or current, max_len=4)
            part = _sanitize_part(part)

        if part and part not in seen:
            parts.append(part)
            seen.add(part)

        parent_name = ig.get("parent_item_group") or ig.get("parent_item_group")
        if not parent_name or parent_name == "All Item Groups":
            break
        current = parent_name

    parts = list(reversed(parts))
    return parts

def _compose_prefix_from_item_group(item_group_name, max_levels=3):
    parts = _collect_prefix_parts_from_item_group(item_group_name, max_levels=max_levels)
    if not parts:
        return "ITEM"
    comp = "-".join([_sanitize_part(p) for p in parts if p])
    comp = re.sub(r'-{2,}', '-', comp).strip('-')
    return comp or "ITEM"

# ---------------------------------------------------------------------
# Series reservation using tabSeries table (atomic)
# ---------------------------------------------------------------------
def _reserve_series_number(prefix):
    """
    Atomically create/lock and increment a tabSeries row for this prefix.
    Returns the integer reserved value (1-based).
    """
    # Attempt to select the row FOR UPDATE to lock it
    row = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE name=%s FOR UPDATE", (prefix,))
    if not row:
        # Insert initial row with current = 1 and return 1
        frappe.db.sql("INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)", (prefix, 1))
        frappe.db.commit()
        return 1
    else:
        current = row[0][0] or 0
        next_no = int(current) + 1
        frappe.db.sql("UPDATE `tabSeries` SET `current`=%s WHERE name=%s", (next_no, prefix))
        frappe.db.commit()
        return next_no

# ---------------------------------------------------------------------
# Public APIs (whitelisted where appropriate)
# ---------------------------------------------------------------------
@frappe.whitelist()
def reserve_item_code(item_group=None, digits=3, max_prefix_levels=3):
    """
    Explicitly reserve and return a code (increments tabSeries).
    Useful when you *do* want to consume a number immediately.
    """
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
    """
    Non-reserving preview: find the highest existing Item name that matches the prefix and suggest next.
    This does NOT change DB state and is safe for frontend preview.
    """
    prefix = _compose_prefix_from_item_group(item_group, max_levels=int(max_prefix_levels))
    like_expr = prefix + '-%'

    # Look at existing Item.item_code or Item.name as appropriate.
    # We query Item.item_code first (if populated), then fallback to name.
    rows = frappe.db.sql("SELECT item_code, name FROM `tabItem` WHERE item_group=%s AND (item_code LIKE %s OR name LIKE %s)",
                         (item_group, like_expr, like_expr)) or []

    max_no = 0
    for item_code, name in rows:
        candidate = item_code or name
        if not candidate:
            continue
        last_seg = candidate.rsplit('-', 1)[-1]
        if last_seg.isdigit():
            try:
                n = int(last_seg)
                if n > max_no:
                    max_no = n
            except Exception:
                pass
    next_no = max_no + 1
    fmt = "{:0" + str(int(digits)) + "d}"
    suffix = fmt.format(next_no)
    return f"{prefix}-{suffix}"

# ---------------------------------------------------------------------
# New: API used at submit-time to atomically reserve and write item_code
# ---------------------------------------------------------------------
def _format_code_from_prefix_and_no(prefix, digits):
    fmt = "{:0" + str(int(digits)) + "d}"
    return f"{prefix}-{fmt.format(int(digits) and 0)}"  # unused, helper placeholder

@frappe.whitelist()
def reserve_and_set_item_code_for_item(docname, item_group=None, digits=3, max_prefix_levels=3):
    """
    Atomically reserve the next series number for the prefix and set the item_code column
    for the already-inserted Item identified by docname.
    - This increments tabSeries (atomic) and writes to Item.item_code using db update.
    - Idempotent: if Item already has item_code, returns existing code (no reserve).
    - Meant to be called at submit time (server-side hook) or as a server RPC at submit.
    """
    if not docname:
        frappe.throw(_("docname required"))

    # Reload current Item value to ensure latest state
    item = frappe.get_doc("Item", docname)

    # If already set, do nothing (idempotent)
    existing = item.get("item_code")
    if existing:
        return existing

    # Need item_group to compute prefix
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

    # Write the item_code field into the database for this item (atomic update)
    frappe.db.sql("UPDATE `tabItem` SET item_code=%s WHERE name=%s", (new_code, docname))
    frappe.db.commit()

    return new_code

# ---------------------------------------------------------------------
# Backwards-compatible wrapper
# ---------------------------------------------------------------------
@frappe.whitelist()
def reserve_item_code_for_item(item_group=None, digits=3, max_prefix_levels=3):
    return reserve_item_code(item_group=item_group, digits=digits, max_prefix_levels=max_prefix_levels)

# ---------------------------------------------------------------------
# Hook: attach to on_submit to reserve the number only when item is submitted.
# Register this in hooks.py:
#   "Item": { "on_submit": "devp_custom.api.auto_set_item_code_on_submit" }
# ---------------------------------------------------------------------
def auto_set_item_code_on_submit(doc, method):
    """
    Hook executed on submit. If item_code not present, atomically reserve and set it.
    This will not change the document name (name remains whatever it was at insert).
    If you require doc.name to equal item_code, you must reserve earlier (before_insert).
    """
    # Defensive checks
    if not doc or (getattr(doc, "doctype", None) or doc.get("doctype") if isinstance(doc, dict) else None) != "Item":
        return

    # If item_code already set, nothing to do
    if getattr(doc, "item_code", None):
        return

    # Only proceed when item_group is present
    item_group = getattr(doc, "item_group", None)
    if not item_group:
        frappe.throw(_("Cannot auto-generate item code on submit: Item Group is missing."))

    # Use the atomic reserve-and-write function
    reserve_and_set_item_code_for_item(doc.name, item_group=item_group, digits=3, max_prefix_levels=3)


def assign_item_code_before_insert(doc, method=None):
    """
    Ensure item_code exists at insert time (Save).
    Uses existing reserve_item_code() to get a unique, atomic series value.
    """
    # if user/client already set one (preview or manual), keep it
    if (doc.item_code or "").strip():
        return

    if not getattr(doc, "item_group", None):
        frappe.throw(_("Item Group is required to generate Item Code"))

    # Reserve a unique code (atomic via tabSeries)
    code = reserve_item_code(
        item_group=doc.item_group,
        digits=3,
        max_prefix_levels=3
    )
    doc.item_code = code
    # If your site uses autoname = field:item_code (recommended), name will follow automatically.
    # If not, uncomment to force:
    # doc.name = code

@frappe.whitelist()
def get_last_item_prices(item_code, customer=None, limit=5, include_other_customers=False):
    """
    Return last `limit` selling prices for given item_code.
    - If `customer` provided and include_other_customers = False: fetch only for that customer.
    - If include_other_customers = True: fetch for other customers (exclude given customer).
    - If no customer: fetch across all customers.
    """
    if not item_code:
        return []

    # normalize params
    limit = int(limit or 5)
    if not customer:
        customer = None
    if isinstance(customer, str) and customer.lower() in ("null", "none", ""):
        customer = None

    include_other = True if str(include_other_customers).lower() in ("1", "true", "yes") else False

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

    query = f"""
        SELECT
            si.name AS invoice,
            si.posting_date AS posting_date,
            sii.rate AS rate,
            si.customer AS customer
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {where}
        ORDER BY si.posting_date DESC, si.modified DESC
        LIMIT %s
    """
    params.append(limit)

    rows = frappe.db.sql(query, tuple(params), as_dict=1)

    # format response
    result = []
    for r in rows:
        result.append({
            "invoice": r.get("invoice"),
            "posting_date": r.get("posting_date").strftime("%Y-%m-%d") if r.get("posting_date") else None,
            "rate": float(r.get("rate")) if r.get("rate") is not None else None,
            "customer": r.get("customer") or ""
        })
    return result


def _get_batch_size(batch_name):
    """Return float or None"""
    if not batch_name:
        return None
    res = frappe.db.get_value("Batch", batch_name, "batch_size")
    try:
        return float(res) if res is not None else None
    except:
        return None

# python (example)
def validate_work_order_batch_size(doc, method=None):
    for row in (doc.get("items") or []):
        # or use parent qty fields depending on your logic
        pass

    qty = doc.get("production_qty") or doc.get("qty") or 0
    batch = doc.get("production_batch") or doc.get("batch_no") or doc.get("batch")
    if batch:
        batch_size = frappe.db.get_value("Batch", batch, "batch_size")
        if batch_size and float(qty) > float(batch_size):
            if not doc.get("allow_batch_exceed"):
                frappe.throw(f"Qty ({qty}) exceeds Batch '{batch}' size ({batch_size}).")
            else:
                frappe.msgprint(f"Override used: qty ({qty}) > batch_size ({batch_size})", indicator="orange")

def _get_batch_size(batch_no):
    return frappe.db.get_value("Batch", batch_no, "batch_size")

def validate_sales_invoice_batch_size(doc, method=None):
    """
    Non-blocking: warn if any child row qty exceeds batch_size.
    This will NOT stop save.
    """
    for row in doc.get("items") or []:
        batch_no = row.get("batch_no") or row.get("batch")
        qty = row.get("qty") or 0
        if batch_no:
            batch_size = _get_batch_size(batch_no)
            if batch_size is not None and float(qty) > float(batch_size):
                frappe.msgprint(
                    f"⚠️ Sales Invoice line for item {row.get('item_code') or ''}: "
                    f"qty ({qty}) exceeds Batch '{batch_no}' size ({batch_size}).",
                    indicator="orange"
                )


@frappe.whitelist()
def get_item_name_description_for_customer(item_code, customer=None):
    """
    Return best override for a single item.
    Priority: exact customer -> customer group -> is_default
    Returns dict: {customer_item_name, customer_description, source}
    """
    if not item_code:
        return {}

    item_code = frappe.as_unicode(item_code)
    customer = frappe.as_unicode(customer) if customer else None

    rows = frappe.get_all(
        "Item Customer Info",
        filters={"parent": item_code},
        fields=["name", "customer", "customer_group", "customer_item_name",
                "customer_description", "is_default", "priority"]
    )

    customer_rows = []
    group_rows = []
    default_rows = []

    cust_group = None
    if customer:
        cust_group = frappe.db.get_value("Customer", customer, "customer_group")

    for r in rows:
        if r.get("customer") and customer and r.get("customer") == customer:
            customer_rows.append(r)
        elif r.get("customer_group") and cust_group and r.get("customer_group") == cust_group:
            group_rows.append(r)
        elif r.get("is_default"):
            default_rows.append(r)

    def choose(rows_list):
        if not rows_list:
            return None
        rows_sorted = sorted(rows_list, key=lambda x: (x.get("priority") or 999, x.get("name") or ""))
        return rows_sorted[0]

    chosen = choose(customer_rows) or choose(group_rows) or choose(default_rows)
    if not chosen:
        return {}

    return {
        "customer_item_name": chosen.get("customer_item_name") or "",
        "customer_description": chosen.get("customer_description") or "",
        "source": "customer" if chosen.get("customer") else ("group" if chosen.get("customer_group") else "default")
    }

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
