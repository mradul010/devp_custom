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
        
    if not frappe.db.exists("Custom Field", "Sales Order Item-manual_amount"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Sales Order Item",
            "fieldname": "manual_amount",
            "label": "Manual Amount",
            "fieldtype": "Currency",
            "insert_after": "amount",
            "precision": "9",   # to handle high precision if needed
            "reqd": 0
        }).insert()
        
    if not frappe.db.exists("Custom Field", "Delivery Note Item-manual_amount"):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Delivery Note Item",
            "fieldname": "manual_amount",
            "label": "Manual Amount",
            "fieldtype": "Currency",
            "insert_after": "amount",
            "precision": "9",   # to handle high precision if needed
            "reqd": 0
        }).insert()
