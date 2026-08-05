"""Credit Card intent taxonomy.

Structure
---------
Product          : one root node ("Credit Card")
Unified intents  : 31 bank services attached to the product
Sub-intents      : 8 per unified intent (248 total)
Life events      : 10 standalone nodes, linked to relevant sub-intents
Complaints       : 10 standalone nodes, linked to relevant sub-intents

Life events and complaints are their own groups: they hang off sub-intents
only, never off the product or the unified intents.
"""

PRODUCT = "Credit Card"

# --- 31 unified intents, each with its 8 sub-intents -------------------------
# key = unified intent name, value = list of 8 sub-intent names
UNIFIED_INTENTS: dict[str, list[str]] = {
    "Increase Credit Limit": [
        "Check limit increase eligibility",
        "Request permanent limit increase",
        "Request temporary limit increase",
        "Upload income proof for limit review",
        "Track limit increase application status",
        "Understand limit increase decline reason",
        "Reapply after a declined limit request",
        "Set limit increase reminder",
    ],
    "Decrease Credit Limit": [
        "Request permanent limit reduction",
        "Set a self-imposed spending cap",
        "Reverse a previous limit reduction",
        "Understand impact on credit score",
        "Reduce limit on a supplementary card",
        "Confirm new limit effective date",
        "Cancel a pending reduction request",
        "Limit reduction for budgeting support",
    ],
    "Card Activation": [
        "Activate a newly issued card",
        "Activate a replacement card",
        "Activate via mobile app",
        "Activate via IVR or phone banking",
        "Troubleshoot failed activation",
        "Confirm activation status",
        "Activate contactless payments",
        "Activate card for online transactions",
    ],
    "Card Replacement": [
        "Request replacement for damaged card",
        "Request replacement for expiring card",
        "Request replacement for worn magnetic stripe",
        "Request expedited replacement delivery",
        "Check replacement card fee",
        "Update address before replacement",
        "Track replacement card shipment",
        "Cancel a replacement request",
    ],
    "Report Lost or Stolen Card": [
        "Report card lost",
        "Report card stolen",
        "Block card immediately",
        "Unblock a card found again",
        "Order emergency replacement card",
        "Review transactions after loss",
        "File police report reference",
        "Request emergency cash advance abroad",
    ],
    "Dispute a Transaction": [
        "Raise a new transaction dispute",
        "Dispute a duplicate charge",
        "Dispute an incorrect amount",
        "Dispute a merchant refund not received",
        "Upload supporting dispute evidence",
        "Track dispute case status",
        "Understand provisional credit",
        "Withdraw an existing dispute",
    ],
    "Fraud Report": [
        "Report unauthorized transaction",
        "Report suspected card skimming",
        "Report phishing or scam contact",
        "Request card reissue after fraud",
        "Track fraud investigation status",
        "Request fraud loss reimbursement",
        "Add extra verification on account",
        "Report identity theft",
    ],
    "Balance Inquiry": [
        "Check current outstanding balance",
        "Check available credit",
        "Check pending transactions",
        "Check last statement balance",
        "Check minimum amount due",
        "Check balance across multiple cards",
        "Set low available credit alert",
        "Explain balance discrepancy",
    ],
    "Statement Request": [
        "Download latest e-statement",
        "Request historical statements",
        "Request physical statement copy",
        "Change statement delivery preference",
        "Change statement cycle date",
        "Explain a statement line item",
        "Request consolidated annual statement",
        "Resend statement to email",
    ],
    "Payment Processing": [
        "Make a one-time card payment",
        "Pay minimum amount due",
        "Pay full outstanding balance",
        "Check payment posting status",
        "Report payment not credited",
        "Reverse a duplicate payment",
        "Change payment source account",
        "Request payment receipt",
    ],
    "Autopay Setup": [
        "Enroll in autopay",
        "Modify autopay amount option",
        "Change autopay debit account",
        "Change autopay debit date",
        "Cancel autopay enrollment",
        "Investigate failed autopay run",
        "Pause autopay temporarily",
        "Confirm autopay enrollment status",
    ],
    "Late Fee Waiver": [
        "Request one-time late fee waiver",
        "Check late fee waiver eligibility",
        "Dispute an incorrectly charged late fee",
        "Request waiver due to hardship",
        "Track waiver request status",
        "Understand late fee policy",
        "Request reversal of related interest",
        "Escalate a declined waiver",
    ],
    "Interest Rate Inquiry": [
        "Check current purchase APR",
        "Check cash advance APR",
        "Request an APR reduction",
        "Understand promotional 0% APR period",
        "Understand penalty APR trigger",
        "Explain interest charged on statement",
        "Compare APR across products",
        "Check variable rate change notice",
    ],
    "Rewards Redemption": [
        "Redeem points for cashback",
        "Redeem points for travel booking",
        "Redeem points for merchandise",
        "Redeem points for gift vouchers",
        "Transfer points to partner program",
        "Cancel or reverse a redemption",
        "Check redemption processing status",
        "Understand redemption rates",
    ],
    "Points Balance": [
        "Check current points balance",
        "Check points earned this cycle",
        "Check points expiry schedule",
        "Report missing points from a purchase",
        "Understand points earning rules",
        "Request retroactive points credit",
        "Combine points across cards",
        "Set points expiry reminder",
    ],
    "Cashback Enquiry": [
        "Check accrued cashback amount",
        "Understand cashback categories",
        "Report missing cashback",
        "Check cashback caps and limits",
        "Request cashback credit to statement",
        "Understand cashback exclusions",
        "Check rotating category enrollment",
        "Check cashback payout schedule",
    ],
    "Travel Notification": [
        "Register a travel plan",
        "Modify travel dates",
        "Cancel a travel notification",
        "Add countries to existing travel plan",
        "Confirm card works at destination",
        "Understand travel plan expiry",
        "Report card blocked while travelling",
        "Request travel emergency contact number",
    ],
    "Foreign Transaction Fees": [
        "Check foreign transaction fee rate",
        "Dispute an unexpected foreign fee",
        "Understand dynamic currency conversion",
        "Check exchange rate applied",
        "Request fee waiver for a trip",
        "Compare no-foreign-fee card options",
        "Understand fees on foreign online purchases",
        "Request refund of duplicate foreign fee",
    ],
    "Annual Fee Enquiry": [
        "Check annual fee amount and due date",
        "Request annual fee waiver",
        "Understand fee waiver spend criteria",
        "Dispute an annual fee charge",
        "Request pro-rated fee refund on closure",
        "Switch to a no-annual-fee card",
        "Understand supplementary card fees",
        "Track annual fee waiver request",
    ],
    "Card Upgrade": [
        "Check upgrade eligibility",
        "Compare higher-tier card benefits",
        "Request upgrade to premium card",
        "Understand upgrade fee and APR changes",
        "Track upgrade application status",
        "Retain benefits after upgrade",
        "Understand impact on rewards balance",
        "Cancel a pending upgrade",
    ],
    "Card Downgrade": [
        "Check downgrade options",
        "Request downgrade to lower-fee card",
        "Understand benefits lost on downgrade",
        "Understand impact on credit history",
        "Track downgrade request status",
        "Retain points after downgrade",
        "Reverse a recent downgrade",
        "Downgrade instead of closing account",
    ],
    "Close Account": [
        "Request card account closure",
        "Check outstanding balance before closure",
        "Redeem remaining rewards before closure",
        "Cancel recurring payments on the card",
        "Confirm closure completion",
        "Understand impact on credit score",
        "Close a supplementary card only",
        "Reopen a recently closed account",
    ],
    "Add Authorized User": [
        "Add a supplementary cardholder",
        "Remove an authorized user",
        "Set spending limit for authorized user",
        "Check supplementary card fee",
        "Track supplementary card delivery",
        "Update authorized user details",
        "Review authorized user transactions",
        "Convert authorized user to primary",
    ],
    "Update Personal Details": [
        "Update mailing address",
        "Update phone number",
        "Update email address",
        "Update name after legal change",
        "Update employment and income details",
        "Update marital status",
        "Update communication preferences",
        "Verify identity for a detail change",
    ],
    "PIN Management": [
        "Set a PIN for a new card",
        "Reset a forgotten PIN",
        "Change existing PIN",
        "Unblock PIN after failed attempts",
        "Retrieve PIN via secure channel",
        "Set PIN for international ATM use",
        "Understand PIN security policy",
        "Report PIN compromise",
    ],
    "Balance Transfer": [
        "Check balance transfer eligibility",
        "Initiate a balance transfer",
        "Check balance transfer fee",
        "Understand promotional transfer rate",
        "Track balance transfer status",
        "Cancel a pending balance transfer",
        "Transfer balance from another bank card",
        "Understand repayment order after transfer",
    ],
    "Cash Advance": [
        "Check cash advance limit",
        "Withdraw cash advance at ATM",
        "Understand cash advance fees",
        "Understand cash advance interest accrual",
        "Repay a cash advance early",
        "Dispute a cash advance charge",
        "Request emergency cash abroad",
        "Disable cash advance feature",
    ],
    "Installment Plan Conversion": [
        "Convert a purchase to installments",
        "Convert full balance to installments",
        "Check installment plan interest rate",
        "Check remaining installment tenure",
        "Foreclose an installment plan early",
        "Check installment prepayment charges",
        "Cancel a newly created plan",
        "Change installment tenure",
    ],
    "Credit Score Inquiry": [
        "Check current credit score",
        "Understand factors affecting the score",
        "Check score change since last month",
        "Dispute a credit bureau record",
        "Understand hard vs soft inquiry",
        "Get score improvement guidance",
        "Enroll in credit score monitoring",
        "Request a credit report copy",
    ],
    "Card Delivery Status": [
        "Track new card shipment",
        "Report card not received",
        "Change delivery address",
        "Reschedule card delivery",
        "Collect card from branch",
        "Verify courier identity",
        "Report card delivered to wrong address",
        "Request redelivery after failed attempt",
    ],
    "Insurance and Protection Plans": [
        "Check bundled travel insurance cover",
        "Check purchase protection cover",
        "Enroll in payment protection plan",
        "File an insurance claim",
        "Track claim status",
        "Cancel a protection plan",
        "Understand exclusions and limits",
        "Request policy documents",
    ],
}

# --- 10 life events, linked to (unified intent, sub-intent) pairs -------------
LIFE_EVENTS: dict[str, list[tuple[str, str]]] = {
    "Marriage": [
        ("Update Personal Details", "Update name after legal change"),
        ("Update Personal Details", "Update marital status"),
        ("Add Authorized User", "Add a supplementary cardholder"),
        ("Increase Credit Limit", "Request permanent limit increase"),
        ("Rewards Redemption", "Redeem points for travel booking"),
        ("Points Balance", "Combine points across cards"),
    ],
    "New Baby": [
        ("Increase Credit Limit", "Check limit increase eligibility"),
        ("Update Personal Details", "Update communication preferences"),
        ("Installment Plan Conversion", "Convert a purchase to installments"),
        ("Cashback Enquiry", "Understand cashback categories"),
        ("Decrease Credit Limit", "Set a self-imposed spending cap"),
    ],
    "Moving Home": [
        ("Update Personal Details", "Update mailing address"),
        ("Card Delivery Status", "Change delivery address"),
        ("Card Replacement", "Update address before replacement"),
        ("Statement Request", "Change statement delivery preference"),
        ("Installment Plan Conversion", "Convert full balance to installments"),
    ],
    "Starting a New Job": [
        ("Update Personal Details", "Update employment and income details"),
        ("Increase Credit Limit", "Upload income proof for limit review"),
        ("Card Upgrade", "Check upgrade eligibility"),
        ("Autopay Setup", "Change autopay debit account"),
        ("Credit Score Inquiry", "Check current credit score"),
    ],
    "Job Loss": [
        ("Late Fee Waiver", "Request waiver due to hardship"),
        ("Interest Rate Inquiry", "Request an APR reduction"),
        ("Installment Plan Conversion", "Convert full balance to installments"),
        ("Decrease Credit Limit", "Limit reduction for budgeting support"),
        ("Annual Fee Enquiry", "Request annual fee waiver"),
        ("Balance Transfer", "Check balance transfer eligibility"),
    ],
    "Retirement": [
        ("Update Personal Details", "Update employment and income details"),
        ("Card Downgrade", "Request downgrade to lower-fee card"),
        ("Annual Fee Enquiry", "Switch to a no-annual-fee card"),
        ("Rewards Redemption", "Redeem points for travel booking"),
        ("Card Downgrade", "Downgrade instead of closing account"),
    ],
    "Travelling Abroad": [
        ("Travel Notification", "Register a travel plan"),
        ("Travel Notification", "Confirm card works at destination"),
        ("Foreign Transaction Fees", "Check foreign transaction fee rate"),
        ("Cash Advance", "Request emergency cash abroad"),
        ("PIN Management", "Set PIN for international ATM use"),
        ("Insurance and Protection Plans", "Check bundled travel insurance cover"),
        ("Increase Credit Limit", "Request temporary limit increase"),
    ],
    "Buying a Home": [
        ("Credit Score Inquiry", "Get score improvement guidance"),
        ("Credit Score Inquiry", "Understand hard vs soft inquiry"),
        ("Decrease Credit Limit", "Understand impact on credit score"),
        ("Balance Transfer", "Initiate a balance transfer"),
        ("Payment Processing", "Pay full outstanding balance"),
        ("Close Account", "Understand impact on credit score"),
    ],
    "Starting University": [
        ("Card Activation", "Activate a newly issued card"),
        ("Increase Credit Limit", "Check limit increase eligibility"),
        ("Annual Fee Enquiry", "Understand fee waiver spend criteria"),
        ("Autopay Setup", "Enroll in autopay"),
        ("Credit Score Inquiry", "Understand factors affecting the score"),
    ],
    "Bereavement": [
        ("Close Account", "Request card account closure"),
        ("Update Personal Details", "Verify identity for a detail change"),
        ("Add Authorized User", "Convert authorized user to primary"),
        ("Late Fee Waiver", "Request waiver due to hardship"),
        ("Insurance and Protection Plans", "File an insurance claim"),
    ],
}

# --- 10 complaint labels, linked to (unified intent, sub-intent) pairs --------
COMPLAINTS: dict[str, list[tuple[str, str]]] = {
    "Unauthorized Charge": [
        ("Fraud Report", "Report unauthorized transaction"),
        ("Fraud Report", "Request fraud loss reimbursement"),
        ("Dispute a Transaction", "Raise a new transaction dispute"),
        ("Cash Advance", "Dispute a cash advance charge"),
        ("Report Lost or Stolen Card", "Review transactions after loss"),
    ],
    "Hidden or Unexpected Fees": [
        ("Foreign Transaction Fees", "Dispute an unexpected foreign fee"),
        ("Annual Fee Enquiry", "Dispute an annual fee charge"),
        ("Late Fee Waiver", "Dispute an incorrectly charged late fee"),
        ("Cash Advance", "Understand cash advance fees"),
        ("Installment Plan Conversion", "Check installment prepayment charges"),
    ],
    "Rewards Not Credited": [
        ("Points Balance", "Report missing points from a purchase"),
        ("Points Balance", "Request retroactive points credit"),
        ("Cashback Enquiry", "Report missing cashback"),
        ("Rewards Redemption", "Check redemption processing status"),
    ],
    "Payment Not Posted": [
        ("Payment Processing", "Report payment not credited"),
        ("Payment Processing", "Check payment posting status"),
        ("Autopay Setup", "Investigate failed autopay run"),
        ("Late Fee Waiver", "Request one-time late fee waiver"),
    ],
    "Card Declined Unexpectedly": [
        ("Balance Inquiry", "Check available credit"),
        ("Travel Notification", "Report card blocked while travelling"),
        ("Card Activation", "Troubleshoot failed activation"),
        ("PIN Management", "Unblock PIN after failed attempts"),
        ("Increase Credit Limit", "Request temporary limit increase"),
    ],
    "Card Delivery Failure": [
        ("Card Delivery Status", "Report card not received"),
        ("Card Delivery Status", "Report card delivered to wrong address"),
        ("Card Delivery Status", "Request redelivery after failed attempt"),
        ("Card Replacement", "Track replacement card shipment"),
    ],
    "Poor Customer Service": [
        ("Late Fee Waiver", "Escalate a declined waiver"),
        ("Dispute a Transaction", "Track dispute case status"),
        ("Increase Credit Limit", "Understand limit increase decline reason"),
        ("Insurance and Protection Plans", "Track claim status"),
    ],
    "Misleading Promotion": [
        ("Interest Rate Inquiry", "Understand promotional 0% APR period"),
        ("Balance Transfer", "Understand promotional transfer rate"),
        ("Cashback Enquiry", "Understand cashback exclusions"),
        ("Annual Fee Enquiry", "Understand fee waiver spend criteria"),
        ("Rewards Redemption", "Understand redemption rates"),
    ],
    "Interest Charged Incorrectly": [
        ("Interest Rate Inquiry", "Explain interest charged on statement"),
        ("Interest Rate Inquiry", "Understand penalty APR trigger"),
        ("Cash Advance", "Understand cash advance interest accrual"),
        ("Balance Transfer", "Understand repayment order after transfer"),
        ("Late Fee Waiver", "Request reversal of related interest"),
    ],
    "Data Privacy Concern": [
        ("Fraud Report", "Report phishing or scam contact"),
        ("Fraud Report", "Report identity theft"),
        ("PIN Management", "Report PIN compromise"),
        ("Update Personal Details", "Update communication preferences"),
        ("Card Delivery Status", "Verify courier identity"),
    ],
}


def validate() -> None:
    """Fail loudly if the taxonomy is internally inconsistent."""
    if len(UNIFIED_INTENTS) != 31:
        raise ValueError(f"expected 31 unified intents, got {len(UNIFIED_INTENTS)}")

    for ui, subs in UNIFIED_INTENTS.items():
        if len(subs) != 8:
            raise ValueError(f"'{ui}' has {len(subs)} sub-intents, expected 8")
        if len(set(subs)) != 8:
            raise ValueError(f"'{ui}' has duplicate sub-intent names")

    if len(LIFE_EVENTS) != 10:
        raise ValueError(f"expected 10 life events, got {len(LIFE_EVENTS)}")
    if len(COMPLAINTS) != 10:
        raise ValueError(f"expected 10 complaints, got {len(COMPLAINTS)}")

    for group_name, group in (("life event", LIFE_EVENTS), ("complaint", COMPLAINTS)):
        for label, links in group.items():
            if not links:
                raise ValueError(f"{group_name} '{label}' has no sub-intent links")
            for ui, sub in links:
                if ui not in UNIFIED_INTENTS:
                    raise ValueError(
                        f"{group_name} '{label}' references unknown unified intent '{ui}'"
                    )
                if sub not in UNIFIED_INTENTS[ui]:
                    raise ValueError(
                        f"{group_name} '{label}' references unknown sub-intent "
                        f"'{sub}' under '{ui}'"
                    )


validate()
