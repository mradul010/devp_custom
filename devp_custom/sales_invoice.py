# apps/devp_custom/devp_custom/sales_invoice.py
import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import nowdate

def autoname(doc, method=None):
    """
    Custom autoname for Sales Invoice:
    - If user provided `custom_requested_name`, use it (after validation).
    - Else fall back to naming-series style autoname.
    """

    requested = (doc.get("custom_requested_name") or "").strip()

    # If user supplied a requested name, try to use it.
    if requested:
        # Basic sanitization: you can adjust rules to your naming convention
        if any(ch in requested for ch in ["\n", "\t"]):
            frappe.throw(_("Requested invoice name contains invalid whitespace characters."))

        # Check DB: if any Sales Invoice row exists with this name (including cancelled ones),
        # block reuse and instruct the user to delete the old row first.
        if frappe.db.exists("Sales Invoice", requested):
            frappe.throw(_("Invoice number {0} already exists. Please delete the old Sales Invoice row first to reuse this number.").format(requested))

        # Name is free — set it
        doc.name = requested
        return

    # Otherwise, create an autoname using a series. Adjust pattern as needed.
    # Example: SINV-YY.-.####  (you can use your existing naming_series logic)
    # If you want to use the existing naming_series set on the doc, use make_autoname(doc.naming_series + ".####")
    naming = doc.get("naming_series") or "SINV-.YY.-"
    # If naming_series already contains wildcard (.#### etc), you can pass it directly to make_autoname
    try:
        # If naming contains pattern markers used by make_autoname, pass directly
        doc.name = make_autoname(naming)
    except Exception:
        # fallback — simple date-based pattern if make_autoname fails
        y = nowdate().replace("-", "")[:6]
        doc.name = make_autoname(f"SINV-{y}-.####")
