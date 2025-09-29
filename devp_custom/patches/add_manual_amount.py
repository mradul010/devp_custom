import frappe

def execute():
    """Create Manual Amount field in Sales Invoice Item if not exists"""
    if not frappe.db.exists("Custom Field", "Sales Invoice Item-manual_amount"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Sales Invoice Item",
            "fieldname": "manual_amount",
            "label": "Manual Amount",
            "fieldtype": "Currency",
            "insert_after": "amount",
            "precision": "9",   # to handle high precision if needed
            "reqd": 0
        }).insert()
