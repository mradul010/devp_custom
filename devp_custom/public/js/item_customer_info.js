frappe.ui.form.on('Item Customer Info', {
    customer: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.customer && !row.customer_group && !row.is_default) {
            frappe.msgprint(__('Either Customer or Customer Group must be set unless "Is Default" is checked.'));
        }
    },
    is_default: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.is_default) {
            frappe.model.set_value(cdt, cdn, 'customer', '');
            frappe.model.set_value(cdt, cdn, 'customer_group', '');
        }
    }
});
