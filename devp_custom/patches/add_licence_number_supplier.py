import frappe

def execute():
    # Ensure the field exists
    if frappe.db.exists("Custom Field", {"dt": "Supplier", "fieldname": "drug_license_number"}):
        frappe.db.set_value(
            "Custom Field",
            {"dt": "Supplier", "fieldname": "drug_license_number"},
            "insert_after",
            "country"
        )
        frappe.clear_cache(doctype="Supplier")
