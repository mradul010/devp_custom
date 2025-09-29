frappe.ui.form.on('Work Order', {
    // handle when qty or production_qty changes (covers common field names)
    qty: function(frm) {
        check_and_prompt_batch(frm);
    },
    production_qty: function(frm) {
        check_and_prompt_batch(frm);
    },
    // also run on refresh to catch cases where batch was chosen first
    refresh: function(frm) {
        // optional: run check for existing values but do not auto-save
        // check_and_prompt_batch(frm);
    }
});

// helper function shared by handlers
function check_and_prompt_batch(frm) {
    // determine the qty and batch fieldnames used in this Work Order
    const qty = frm.doc.production_qty || frm.doc.qty || 0;
    const batch = frm.doc.production_batch || frm.doc.batch_no || frm.doc.batch || null;

    if (!batch || !qty) return;

    // fetch batch_size
    frappe.db.get_value('Batch', batch, 'batch_size').then(r => {
        const batch_size = (r && r.message) ? parseFloat(r.message.batch_size || 0) : null;
        if (batch_size && parseFloat(qty) > batch_size) {
            // show reliable dialog with Save Anyway button using frappe.msgprint
            frappe.msgprint({
                title: 'Batch size exceeded',
                message: `<div>Work Order quantity <b>${qty}</b> exceeds batch size <b>${batch_size}</b> for batch <b>${batch}</b>.</div>`,
                indicator: 'orange',
                primary_action: {
                    label: 'Save Anyway',
                    action: () => {
                        // Optional: set persistent flag for audit (create the checkbox via Customize Form)
                        // frm.set_value('allow_batch_exceed', 1).then(() => frm.save());
                        // If you don't have the checkbox or don't want it, just save:
                        frm.save();
                    }
                },
                secondary_action: {
                    label: 'Cancel',
                    action: () => {
                        // Do nothing — user can edit values
                    }
                }
            });
        }
    }).catch(err => {
        console.error('Error checking batch size', err);
    });
}
