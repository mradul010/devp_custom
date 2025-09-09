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

