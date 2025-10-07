// --- helpers & CSS injector from your last version, unchanged ---
function mark_row(frm, row, has_error) {
    const grid = frm.fields_dict.items.grid;
    const gr = grid?.grid_rows_by_docname?.[row.name];
    if (gr?.$row?.length) gr.$row.toggleClass('row-error', !!has_error);
}

function get_batch_size_sync(batch_no) {
    if (!batch_no) return null;
    let value = null;
    frappe.call({
        method: "frappe.client.get_value",
        args: { doctype: "Batch", filters: { name: batch_no }, fieldname: "batch_size" },
        async: false,
        callback: r => value = (r?.message?.batch_size != null ? flt(r.message.batch_size) : null)
    });
    return value;
}
function ensure_row_limit(row) {
    let lim = (row.batch_size_limit != null && row.batch_size_limit !== "") ? flt(row.batch_size_limit) : null;
    if (!lim && row.batch_no) lim = get_batch_size_sync(row.batch_no);
    return lim;
}
(function inject_custom_css_once() {
    const id = "batch-size-validation-style";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
        .row-error { background: rgba(217, 48, 37, 0.08) !important; }
        .row-error-pulse { animation: flash-bg 1s ease-in-out; }
        @keyframes flash-bg { 0% { background: rgba(217,48,37,0.28); } 100% { background: rgba(217,48,37,0.08); } }
        .frappe-message-dialog.error-dialog .modal-header { background: linear-gradient(135deg,#d93025,#b71c1c)!important; color:#fff!important; border-bottom:0!important; }
        .frappe-message-dialog.error-dialog .modal-title { color:#fff!important; display:flex; align-items:center; gap:8px; }
        .frappe-message-dialog.error-dialog .modal-content { border:1px solid rgba(217,48,37,.5)!important; box-shadow:0 10px 24px rgba(217,48,37,.25)!important; border-radius:12px!important; overflow:hidden; }
        .frappe-message-dialog.error-dialog .modal-body { background:#fff8f8!important; }
        .frappe-message-dialog.error-dialog .modal-footer .btn-primary { background:#d93025!important; border-color:#b71c1c!important; }
        .frappe-message-dialog.error-dialog .btn-danger { background:#b71c1c!important; border-color:#8e1313!important; }
        .batch-alert .summary { display:flex; align-items:center; gap:10px; margin-bottom:10px; font-weight:600; color:#b71c1c; }
        .batch-alert .badge { display:inline-block; padding:2px 8px; border-radius:999px; background:#ffe1e1; color:#b71c1c; font-weight:700; font-size:12px; }
        .batch-alert .table thead th { position:sticky; top:0; background:#ffe5e5; z-index:1; }
        .batch-alert .table td, .batch-alert .table th { vertical-align: middle !important; }
    `;
    document.head.appendChild(style);
})();

// --- main ---
frappe.ui.form.on('Sales Invoice', {
    validate: function(frm) {
        const allow_override = cint(frm.doc.allow_batch_exceed) === 1;
        const violations = [];

        (frm.doc.items || []).forEach(row => {
            mark_row(frm, row, false);
            if (!row.batch_no) return;

            const qty = flt(row.qty) || 0;
            const lim = ensure_row_limit(row);

            if (!lim) {
                violations.push({ idx: row.idx, item_code: row.item_code || '', batch_no: row.batch_no, qty, limit: '—', reason: 'Batch size not available' });
                mark_row(frm, row, true);
                return;
            }
            if (qty > lim) {
                violations.push({ idx: row.idx, item_code: row.item_code || '', batch_no: row.batch_no, qty, limit: lim, reason: 'Qty exceeds batch size' });
                mark_row(frm, row, true);
            }
        });

        if (violations.length && !allow_override) {
            const count = violations.length;
            const rows_html = violations.map(v =>
                `<tr>
                    <td style="text-align:center">${frappe.utils.escape_html(String(v.idx))}</td>
                    <td>${frappe.utils.escape_html(v.item_code)}</td>
                    <td>${frappe.utils.escape_html(v.batch_no)}</td>
                    <td style="text-align:right">${v.qty}</td>
                    <td style="text-align:right">${v.limit}</td>
                    <td>${frappe.utils.escape_html(v.reason)}</td>
                </tr>`
            ).join('');

            const html =
                `<div class="batch-alert">
                    <div class="summary">
                        <span>🚫 ${__("Batch Size Violations Detected")}</span>
                        <span class="badge">${count} ${count === 1 ? __("issue") : __("issues")}</span>
                    </div>
                    <div style="margin-bottom:8px; color:#5f2120;">
                        ${__("Please adjust quantities or change batches before saving.")}
                    </div>
                    <div class="grid-overflow" style="max-height:280px; overflow:auto; border:1px solid var(--border-color); border-radius:10px; background:#fff;">
                        <table class="table table-bordered table-sm" style="margin:0">
                            <thead>
                                <tr>
                                    <th style="width:70px; text-align:center">#</th>
                                    <th>${__("Item")}</th>
                                    <th>${__("Batch")}</th>
                                    <th style="text-align:right">${__("Qty")}</th>
                                    <th style="text-align:right">${__("Limit")}</th>
                                    <th>${__("Reason")}</th>
                                </tr>
                            </thead>
                            <tbody>${rows_html}</tbody>
                        </table>
                    </div>
                 </div>`;

            // scroll to first offending row
            const first = violations[0];
            const grid = frm.fields_dict.items.grid;
            if (first && grid) {
                const target = (frm.doc.items || []).find(r => r.idx === first.idx);
                const gr = target ? grid.grid_rows_by_docname?.[target.name] : null;
                if (gr?.$row?.length) {
                    gr.$row[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
                    gr.$row.addClass('row-error-pulse');
                    setTimeout(() => gr.$row.removeClass('row-error-pulse'), 1000);
                }
            }

            // Build dialog manually so we can add a "Save Anyway" button
            const d = new frappe.ui.Dialog({
                title: __('Batch Size Validation'),
                indicator: 'red',
                primary_action_label: __('Adjust Items'),
                primary_action: () => d.hide()
            });
            d.$body.html(html);

            // Add "Save Anyway" (danger) if user really wants to bypass
            const $footer = d.$wrapper.find('.modal-footer');
            const $saveAnyway = $(`<button class="btn btn-danger">${__('Save Anyway')}</button>`)
                .on('click', async () => {
                    // set override flag & attempt save again
                    await frm.set_value('allow_batch_exceed', 1);
                    d.hide();
                    // prevent loops: if validate runs again, it will skip due to flag
                    frm.save();
                });
            $footer.prepend($saveAnyway);

            d.show();

            // Make it the red theme
            setTimeout(() => {
                const el = d.$wrapper.closest('.frappe-message-dialog')[0];
                if (el) el.classList.add('error-dialog');
            }, 10);

            // Block the original save with a throw (after showing dialog)
            frappe.validated = false; // cancel current save without extra popup
            throw new Error('Validation blocked'); // stop further execution
        }
    }
});
