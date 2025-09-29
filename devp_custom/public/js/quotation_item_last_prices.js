// devp_custom/public/js/quotation_item_last_prices.js
// Standalone: show last selling prices for Quotation Item rows.
// Default: fetch last prices for current customer. Secondary button "Show other parties"
// fetches history across other customers and replaces the table data.

frappe.ui.form.on('Quotation Item', {
    item_code: function(frm, cdt, cdn) {
        const item = locals[cdt][cdn];
        if (!item || !item.item_code) return;

        const customer = frm.doc.customer || "";

        const fetchForCustomer = (limit=5) => {
            return frappe.call({
                method: 'devp_custom.api.get_last_item_prices',
                args: {
                    item_code: item.item_code,
                    customer: customer,
                    limit: limit,
                    include_other_customers: false
                },
                freeze: true,
                freeze_message: 'Fetching last selling prices...'
            });
        };

        const fetchOtherCustomers = (limit=50) => {
            return frappe.call({
                method: 'devp_custom.api.get_last_item_prices',
                args: {
                    item_code: item.item_code,
                    customer: customer,
                    limit: limit,
                    include_other_customers: true
                },
                freeze: true,
                freeze_message: 'Fetching last selling prices from other parties...'
            });
        };

        // Try customer-specific history first
        fetchForCustomer().then(function(resp) {
            const data = (resp && resp.message) ? resp.message : [];
            if (data.length) {
                openQuotationPriceDialog(frm, item, data, true, false, () => fetchOtherCustomers(50));
            } else {
                // fallback: if no customer-specific history, fetch other-party data immediately
                fetchOtherCustomers(50).then(function(resp2) {
                    const other = (resp2 && resp2.message) ? resp2.message : [];
                    if (other.length) {
                        openQuotationPriceDialog(frm, item, other, false, true, null);
                    } else {
                        frappe.msgprint({
                            title: 'No history',
                            message: `No sales history found for ${item.item_code} (neither for this customer nor other customers).`,
                            indicator: 'orange'
                        });
                    }
                }).catch(function(err2) {
                    console.error('Error fetching other-party prices', err2);
                    frappe.msgprint({ title: 'Error', message: 'Failed to fetch other-party prices. See console.' });
                });
            }
        }).catch(function(err) {
            console.error('Error fetching last prices', err);
            frappe.msgprint({ title: 'Error', message: 'Failed to fetch last prices. See console.' });
        });
    }
});

/**
 * openQuotationPriceDialog
 * - frm, item: passed from caller
 * - data: array of records (backend may return invoice/order/quotation/name etc.)
 * - allow_other_button: whether to show "Show other parties" secondary action
 * - is_other_party: whether data already contains other-party results
 * - fetchOtherCustomersFn: function() -> Promise used by the secondary action to fetch other-party data
 */
function openQuotationPriceDialog(frm, item, data, allow_other_button=false, is_other_party=false, fetchOtherCustomersFn=null) {
    const fields = [{
        fieldname: 'prices',
        fieldtype: 'Table',
        cannot_add_rows: true,
        cannot_delete_rows: true,
        in_place_edit: false,
        fields: [
            {
                label: 'Quotation',
                fieldname: 'document',
                fieldtype: 'Link',
                options: 'Quotation',
                in_list_view: 1,
                read_only: 1
            },
            {
                label: 'Date',
                fieldname: 'posting_date',
                fieldtype: 'Date',
                in_list_view: 1,
                read_only: 1
            },
            {
                label: 'Party',
                fieldname: 'customer',
                fieldtype: 'Data',
                in_list_view: 1,
                read_only: 1
            },
            {
                label: 'Rate',
                fieldname: 'rate',
                fieldtype: 'Currency',
                in_list_view: 1,
                read_only: 1
            }
        ],
        data: map_data_for_dialog(data)
    }];

    const title_extra = is_other_party ? ' (from other parties)' : '';
    const dialog_args = {
        title: `${item.item_code} — Last Selling Prices${title_extra}`,
        size: 'large',
        fields: fields,
        primary_action_label: 'Select',
        primary_action: function() {
            try {
                const selected = dialog.fields_dict.prices.grid.get_selected_children();
                if (!selected || selected.length !== 1) {
                    frappe.msgprint('Please select exactly one row to pick the rate.');
                    return;
                }
                const chosen = selected[0];
                // set rate on the Quotation Item child row
                frappe.model.set_value(item.doctype, item.name, 'rate', chosen.rate);
                // If needed, trigger recalculation of amounts or totals here. Example:
                // frm.script_manager.trigger('calculate_taxes_and_totals');
                dialog.hide();
            } catch (e) {
                console.error('Dialog select error', e);
                frappe.msgprint('Could not set rate — see console.');
            }
        }
    };

    if (allow_other_button && !is_other_party && typeof fetchOtherCustomersFn === 'function') {
        dialog_args.secondary_action_label = 'Show other parties';
        dialog_args.secondary_action = function() {
            // disable the button immediately to avoid double clicks
            const btn = dialog.wrapper && dialog.wrapper.find('.modal-footer .btn-secondary');
            if (btn && btn.length) btn.prop('disabled', true).text('Loading...');

            fetchOtherCustomersFn().then(function(res) {
                const other = (res && res.message) ? res.message : [];
                if (!other.length) {
                    frappe.msgprint({ title: 'No history', message: 'No records found from other parties.' });
                    if (btn && btn.length) btn.prop('disabled', false).text('Show other parties');
                    return;
                }
                try {
                    const grid = dialog.fields_dict.prices.grid;
                    grid.wrapper && grid.wrapper.scrollTop(0);
                    grid.df.data = map_data_for_dialog(other);
                    grid.refresh();
                    dialog.set_title(`${item.item_code} — Last Selling Prices (from other parties)`);
                    if (btn && btn.length) {
                        btn.prop('disabled', true).text('Shown');
                    }
                } catch (e) {
                    console.error('Failed to swap grid data', e);
                    frappe.msgprint({ title: 'Error', message: 'Failed to display other-party data. See console.' });
                    if (btn && btn.length) btn.prop('disabled', false).text('Show other parties');
                }
            }).catch(function(err) {
                console.error('Error fetching other-party prices', err);
                frappe.msgprint({ title: 'Error', message: 'Failed to fetch other-party prices. See console.' });
                if (btn && btn.length) btn.prop('disabled', false).text('Show other parties');
            });
        };
    }

    const dialog = new frappe.ui.Dialog(dialog_args);
    dialog.show();

    // auto-select first row for convenience
    try {
        const grid = dialog.fields_dict.prices.grid;
        if (grid && grid.grid_rows && grid.grid_rows.length) {
            const firstRow = grid.grid_rows[0];
            if (firstRow && firstRow.row_select_checkbox) {
                firstRow.row_select_checkbox.click();
                grid.wrapper && grid.wrapper.scrollTop(0);
            }
        }
    } catch (e) {
        console.warn('Auto-select failed', e);
    }

    // normalize server data for dialog
    function map_data_for_dialog(raw) {
        return (raw || []).map(function(r) {
            return {
                document: r.quotation || r.name || r.order || r.invoice || '',
                posting_date: r.posting_date || r.transaction_date || r.date || '',
                customer: r.customer || r.party || '',
                rate: r.rate || r.price || 0
            };
        });
    }
}
