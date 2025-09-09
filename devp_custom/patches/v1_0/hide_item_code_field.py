# apps/devp_custom/devp_custom/patches/v1_0/hide_item_code_field.py
import frappe

def execute():
    """
    Create or update a Property Setter to set DocField Item.item_code hidden = 1
    Idempotent: safe to run multiple times.
    """
    try:
        ps = frappe.db.get_value(
            "Property Setter",
            {
                "doctype_or_field": "DocField",
                "doc_type": "Item",
                "field_name": "item_code",
                "property": "hidden"
            },
            ["name"], as_dict=True
        )

        if ps:
            # update existing property setter
            frappe.db.set_value("Property Setter", ps["name"], "value", "1")
            frappe.db.commit()
            frappe.log("Updated Property Setter: Item.item_code hidden -> 1")
        else:
            # create a new property setter
            doc = frappe.get_doc({
                "doctype": "Property Setter",
                "doctype_or_field": "DocField",
                "doc_type": "Item",
                "field_name": "item_code",
                "property": "hidden",
                "value": "1",
                "description": "Hide item_code field on Item form (generated on submit)"
            })
            doc.insert(ignore_permissions=True)
            frappe.db.commit()
            frappe.log("Created Property Setter: Item.item_code hidden -> 1")
    except Exception as e:
        frappe.db.rollback()
        frappe.throw(f"Failed to create/update Property Setter to hide Item.item_code: {e}")
