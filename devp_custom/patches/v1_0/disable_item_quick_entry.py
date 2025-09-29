import frappe

def execute():
    df = frappe.get_doc('DocType', 'Item')
    if df.quick_entry:
        frappe.db.set_value('DocType', 'Item', 'quick_entry', 0)
        frappe.clear_cache(doctype='Item')
