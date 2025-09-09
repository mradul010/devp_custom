# apps/devp_custom/devp_custom/patches/v1_0/make_item_code_not_required.py
import frappe

def execute():
    # If a Property Setter already exists for Item.item_code reqd, update it.
    ps = frappe.db.get_value(
        "Property Setter",
        {"doctype_or_field": "DocField", "doc_type": "Item", "field_name": "item_code", "property": "reqd"},
        ["name"], as_dict=True
    )

    if ps:
        # update existing setter
        try:
            frappe.db.set_value("Property Setter", ps["name"], "value", "0")
            frappe.db.commit()
            frappe.log("Updated Property Setter: item_code reqd -> 0")
        except Exception:
            frappe.db.rollback()
    else:
        # create a new property setter
        try:
            doc = frappe.get_doc({
                "doctype": "Property Setter",
                "doctype_or_field": "DocField",
                "doc_type": "Item",
                "field_name": "item_code",
                "property": "reqd",
                "value": "0",
                "description": "Make item_code not required at save (generated on submit)"
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.throw(f"Could not create Property Setter for Item.item_code: {e}")
