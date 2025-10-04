# DevP Custom App for ERPNext

**DevP Custom** is a custom ERPNext extension developed for **DevParv Surgico** by **Techsolvo LLP**.  
It enhances ERPNext’s Selling and Item modules with:

- 🔹 **Customer-Specific Item Mapping** – Assign unique item names & descriptions for each customer.  
- 🔹 **Last 5 Selling Price Lookup** – Show the customer’s last selling rates while creating a transaction.  
- 🔹 **Unified Transaction Flow** – When an item is selected, you can pick a previous rate and auto-apply customer-specific item details.

---

## ⚙️ Installation

Run these commands one after another in your bench directory:

```bash
bench get-app https://github.com/mradul010/devp_custom --branch main
bench --site devparv11 install-app devp_custom
bench --site devparv11 migrate
bench build
bench clear-cache
bench restart
