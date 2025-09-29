frappe.ui.form.on('Sales Invoice Item', {
    qty: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        const qty = row.qty || 0;
        const batch = row.batch_no || null;

        if (!batch || !qty) return;

        frappe.db.get_value('Batch', batch, 'batch_size').then(r => {
            const batch_size = r && r.message ? parseFloat(r.message.batch_size) : null;

            if (batch_size && parseFloat(qty) > batch_size) {
                // Use frappe.msgprint because it reliably shows a primary action.
                // The primary button will set the override flag (optional) and save.
                frappe.msgprint({
                    title: 'Batch size exceeded',
                    message: `<div>Qty <b>${qty}</b> exceeds batch size <b>${batch_size}</b> for batch ${batch}.</div>`,
                    indicator: 'orange',
                    primary_action: {
                        label: 'Save Anyway',
                        action: () => {
                            // optionally set a persistent flag for audit
                            // if you created the checkbox in Customize Form:
                            // frm.set_value('allow_batch_exceed', 1).then(() => frm.save());
                            // If you didn't create the checkbox, you can just save:
                            frm.save();
                        }
                    },
                    secondary_action: {
                        label: 'Cancel',
                        action: () => { /* nothing */ }
                    }
                });
            }
        }).catch(err => {
            console.error('Error fetching batch_size', err);
        });
    }
});
