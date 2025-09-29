def calculate_amount(doc, method=None):
    """
    If Manual Amount is entered, derive Rate from it.
    Otherwise keep ERPNext's default qty * rate = amount.
    """
    if not doc.qty:
        return

    if doc.manual_amount and float(doc.manual_amount) > 0:
        # user entered manual amount
        doc.rate = float(doc.manual_amount) / float(doc.qty)
        doc.amount = float(doc.manual_amount)
    else:
        # default calculation
        doc.amount = float(doc.qty) * float(doc.rate or 0)
