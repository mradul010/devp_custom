// apps/devp_custom/devp_custom/public/js/item_client.js

frappe.ui.form.on('Item', {
    refresh: function(frm) {
        // Always keep item_code non-editable
        frm.set_df_property('item_code', 'read_only', 1);

        // Clear preview debounce on refresh
        if (frm._preview_timeout) {
            clearTimeout(frm._preview_timeout);
            frm._preview_timeout = null;
        }

        // Show preview if new doc + has item_group
        if (frm.is_new() && frm.doc.item_group && !frm.doc.item_code) {
            _set_item_code_preview(frm);
        }
    },

    item_group: function(frm) {
        if (!frm.doc.item_group) {
            // Clear preview if no group
            frm.set_value('item_code', '');
            return;
        }

        // Only show preview for new unsaved docs without code
        if (frm.is_new() && !frm.doc.item_code) {
            if (frm._preview_timeout) clearTimeout(frm._preview_timeout);
            frm._preview_timeout = setTimeout(() => {
                _set_item_code_preview(frm);
            }, 400);
        }
    }
});

function _set_item_code_preview(frm) {
    frappe.call({
        method: 'devp_custom.api.get_next_item_code_preview',
        args: {
            item_group: frm.doc.item_group,
            digits: 3,
            max_prefix_levels: 3
        },
        callback: function(r) {
            if (r && r.message) {
                frm.set_value('item_code', r.message);
                frappe.show_alert({
                    message: __('Suggested Item Code (final will be assigned on Submit): {0}', [r.message]),
                    indicator: 'blue'
                });
            }
        }
    });
}
