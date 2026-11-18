(() => {
    const allocations = (frm) => frm.doc.__onload?.devp_batch_allocations || {};
    const informational_rows = (frm) => frm.doc.__onload?.devp_informational_batch_rows || [];
    const stored_reference = "custom_informational_batch_no";
    const reference_field = (frm, row) => frm.doc.__onload?.devp_informational_batch_fields?.[row.name] ||
        (row[stored_reference] ? stored_reference : "batch_no");
    const date = (value) => value ? frappe.datetime.str_to_user(value) : "";
    const escape = frappe.utils.escape_html;

    function posted_batch_summary(allocation, row) {
        if (!allocation.batches.length) {
            return escape(row.batch_no
                ? __("No posted batch could be confirmed for this row.")
                : __("This row has no posted batch details."));
        }
        return allocation.batches.map((batch) => {
            const details = [__("Batch No") + " " + batch.batch_no];
            if (batch.manufacturing_date) {
                details.push(__("Batch Manufacturing Date") + " " + date(batch.manufacturing_date));
            }
            if (batch.expiry_date) {
                details.push(__("Batch Expiry Date") + " " + date(batch.expiry_date));
            }
            return escape(details.join(" · "));
        }).join("<br>");
    }

    function show_batch_correction(frm) {
        const rows = frm.doc.items.filter((row) => allocations(frm)[row.name]?.show);
        const lines = rows.map((row) => {
            const allocation = allocations(frm)[row.name];
            const links = allocation.vouchers.map(({ doctype, name }) =>
                frappe.utils.get_form_link(doctype, name, true)
            );
            return `<li>${escape(__("Row {0}", [row.idx]))} · ${posted_batch_summary(allocation, row)}
                ${links.length ? "<br>" + links.join(", ") : ""}</li>`;
        });
        frappe.msgprint({
            title: __("Posted Batch Correction"),
            message: `<p>${escape(__(
                "Open the stock document that posted the batch. If you have permission and ERPNext allows cancellation, cancel it and use Amend to select the correct batch and submit the replacement. Resolve linked documents through their normal workflows first."
            ))}</p><ul>${lines.join("")}</ul>`,
        });
    }

    function select_item(rows, title, action, select) {
        if (!rows.length) return;
        if (rows.length === 1) {
            select(rows[0]);
            return;
        }
        const choices = new Map(rows.map((row) => [`${row.idx} · ${row.item_code}`, row]));
        frappe.prompt({
            label: __("Item Row"),
            fieldname: "item_row",
            fieldtype: "Select",
            options: [...choices.keys()],
            reqd: 1,
        }, ({ item_row }) => {
            const row = choices.get(item_row);
            if (row) select(row);
        }, title, action);
    }

    function open_submitted_item(grid) {
        const open_row = (row) => {
            const pagination = grid.grid_pagination;
            const index = grid.data.findIndex((item) => item.name === row.name);
            if (index < 0) return;
            const page = Math.floor(index / pagination.page_length) + 1;
            if (page !== pagination.page_index) pagination.go_to_page(page);
            grid.grid_rows_by_docname[row.name]?.toggle_view(true);
        };
        select_item(grid.data, __("Edit Submitted Item"), __("Open Row"), open_row);
    }

    function lookup_batch_dates(batch_no, bundle) {
        if (!batch_no && !bundle) return Promise.resolve({});
        return frappe.xcall("devp_custom.submitted_sales.get_batch_dates", { batch_no, bundle });
    }

    function edit_informational_batch(frm, row) {
        const doc = frm.doc;
        const fieldname = reference_field(frm, row);
        const reference_only = fieldname !== "batch_no";
        const filters = { disabled: 0 };
        if (!reference_only) filters.item = row.item_code;
        let dialog;
        async function update_dates() {
            if (!dialog) return;
            const batch = dialog.get_value("batch_no") || "";
            const dates = await lookup_batch_dates(batch, "");
            if ((dialog.get_value("batch_no") || "") !== batch) return;
            await dialog.set_value("batch_manufacturing_date", dates.manufacturing_date || null);
            await dialog.set_value("batch_expiry_date", dates.expiry_date || null);
        }
        dialog = new frappe.ui.Dialog({
            title: __("Edit Informational Batch"),
            fields: [
                {
                    fieldname: "batch_no",
                    label: reference_only ? __("Informational Batch Reference") : __("Batch No"),
                    fieldtype: "Link", options: "Batch", default: row[fieldname],
                    description: reference_only
                        ? __("The Batch can belong to a different Item. This reference is excluded from stock posting.")
                        : "",
                    get_query: () => ({ filters }),
                    onchange: update_dates,
                },
                {
                    fieldname: "batch_manufacturing_date", label: __("Batch Manufacturing Date"),
                    fieldtype: "Date", read_only: 1, default: row.batch_manufacturing_date,
                },
                {
                    fieldname: "batch_expiry_date", label: __("Batch Expiry Date"),
                    fieldtype: "Date", read_only: 1, default: row.batch_expiry_date,
                },
            ],
            primary_action_label: __("Apply Batch"),
            async primary_action({ batch_no }) {
                if (frm.doc !== doc || !doc.items.includes(row) || allocations(frm)[row.name]) return;
                await frappe.model.set_value(row.doctype, row.name, fieldname, batch_no || null);
                dialog.hide();
            },
        });
        dialog.show();
    }

    function can_edit_informational_batch(frm, row) {
        const batch = frappe.meta.get_docfield(row.doctype, reference_field(frm, row), frm.docname);
        return frm.doc.docstatus === 1 && !frm.read_only && frm.perm[0]?.submit &&
            batch?.allow_on_submit && !batch.read_only && frm.perm[batch.permlevel || 0]?.write;
    }

    function render_reference_details(details) {
        return details.map((batch) => {
            const fields = [
                [batch.fieldname === "batch_no" ? __("Batch No") : __("Informational Batch Reference"), batch.batch_no],
                [__("Batch Manufacturing Date"), date(batch.manufacturing_date)],
                [__("Batch Expiry Date"), date(batch.expiry_date)],
            ];
            return fields.map(([label, value]) => `<div><strong>${escape(label)}</strong> ${escape(value)}</div>`).join("");
        }).join('<hr class="my-2">');
    }

    function render_batch_details(frm, row) {
        const grid_row = frm.fields_dict?.items?.grid?.grid_rows_by_docname?.[row.name];
        const field = grid_row?.grid_form?.fields_dict.custom_posted_batches;
        if (!field) return;
        const allocation = allocations(frm)[row.name];
        const saved = frm.doc.__onload?.devp_informational_batch_details?.[row.name] || [];
        if (allocation) {
            const posted = allocation.show
                ? `<strong>${escape(__("Posted Batches"))}</strong><div>${posted_batch_summary(allocation, row)}</div>`
                : "";
            field.html([posted, render_reference_details(saved)].filter(Boolean).join('<hr class="my-2">'));
            return;
        }
        const eligible = informational_rows(frm).includes(row.name);
        if (!eligible && !row[stored_reference]) return;
        const fieldname = reference_field(frm, row);
        const details = [{
            fieldname,
            batch_no: row[fieldname] || "",
            manufacturing_date: row[fieldname] ? row.batch_manufacturing_date : null,
            expiry_date: row[fieldname] ? row.batch_expiry_date : null,
        }, ...saved.filter((batch) => batch.fieldname !== fieldname && batch.batch_no !== row[fieldname])];
        field.html(render_reference_details(details));
        if (eligible && can_edit_informational_batch(frm, row)) {
            $('<button type="button" class="btn btn-default btn-xs mt-2">')
                .text(__("Edit Informational Batch"))
                .on("click", () => edit_informational_batch(frm, row))
                .appendTo(field.$wrapper);
        }
    }

    async function fetch_batch_dates(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || allocations(frm)[cdn]) return;

        const item = row.item_code;
        const fieldname = reference_field(frm, row);
        const batch = row[fieldname] || "";
        const bundle = row.serial_and_batch_bundle || "";
        const dates = await lookup_batch_dates(batch, bundle);

        if (locals[cdt][cdn] !== row || row.item_code !== item || (row[fieldname] || "") !== batch ||
            (row.serial_and_batch_bundle || "") !== bundle) return;

        await frappe.model.set_value(cdt, cdn, {
            batch_manufacturing_date: dates.manufacturing_date || null,
            batch_expiry_date: dates.expiry_date || null,
        });
        if (frm.doc.docstatus === 1) render_batch_details(frm, row);
    }

    const doctype = cur_frm.doctype;
    const child = doctype + " Item";
    frappe.ui.form.on(doctype, {
        setup(frm) {
            const original = frm.cscript.batch_no;
            if (original) {
                frm.cscript.batch_no = function (doc, cdt, cdn) {
                    // The draft handler also sets rates and changes serial/batch mode.
                    if (doc.docstatus === 0) return original.call(this, doc, cdt, cdn);
                };
            }
        },
        refresh(frm) {
            const grid = frm.fields_dict.items.grid;
            const label = __("Edit Submitted Item");
            const batch_label = __("Edit Informational Batch");
            const permission = frm.perm[0];
            const description = frappe.meta.get_docfield(grid.doctype, "description", frm.docname);
            if (
                frm.doc.docstatus === 1 && permission?.write && permission.submit &&
                !frm.read_only && frm.doc.items.length && description?.allow_on_submit
            ) {
                grid.add_custom_button(label, () => open_submitted_item(grid), "top");
            } else {
                grid.custom_buttons[label]?.addClass("hidden");
            }
            const eligible = informational_rows(frm);
            const batch_rows = frm.doc.items.filter((row) =>
                eligible.includes(row.name) && can_edit_informational_batch(frm, row));
            if (batch_rows.length) {
                grid.add_custom_button(batch_label, () => {
                    select_item(batch_rows, batch_label, __("Select Row"), (row) => edit_informational_batch(frm, row));
                }, "top");
            } else {
                grid.custom_buttons[batch_label]?.addClass("hidden");
            }
            if (frm.doc.docstatus !== 1) return;
            frm.set_query("batch_no", "items", (doc, cdt, cdn) => ({
                filters: { item: locals[cdt][cdn].item_code, disabled: 0 },
            }));
            if (Object.values(allocations(frm)).some((allocation) => allocation.show)) {
                frm.add_custom_button(__("Posted Batch Correction"), () => show_batch_correction(frm));
            }
        },
    });

    frappe.ui.form.on(child, {
        item_code(frm, cdt, cdn) {
            if (frm.doc.docstatus !== 0) return;
            return frappe.model.set_value(cdt, cdn, {
                batch_manufacturing_date: null,
                batch_expiry_date: null,
            });
        },
        batch_no: fetch_batch_dates,
        custom_informational_batch_no: fetch_batch_dates,
        serial_and_batch_bundle: fetch_batch_dates,
        form_render(frm, cdt, cdn) {
            if (frm.doc.docstatus === 1) render_batch_details(frm, locals[cdt][cdn]);
        },
    });
})();
