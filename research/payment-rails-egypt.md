# Payment Infrastructure — Egypt, September 2026

## The single most important finding

**PayPal cannot be used to receive money in Egypt.** Egyptian accounts operate under a
send-only profile: they can pay for things, but cannot receive client payments and cannot
withdraw to an Egyptian bank or convert to EGP. This is driven by Central Bank of Egypt
foreign-currency regulation and the absence of a licensed PayPal entity in Egypt. It has
persisted for years and is unchanged in 2026.

**Consequences for strategy:**
- Any platform that pays out *only* by PayPal is unusable. This is why **RD Studio**
  (Revit/Dynamo script marketplace, 50% revenue share, PayPal-only payouts) is parked
  despite being a perfect product fit.
- Never quote PayPal to a client as a payment option.

---

## Rail comparison

| Rail | Works in Egypt | Receives from | Withdrawal | Approx. total cost on $1,000 | Speed | Verification |
|---|---|---|---|---|---|---|
| **Payoneer** | ✅ Yes | Upwork, Fiverr, direct clients, most marketplaces | Direct to Egyptian bank in EGP | **~$85 (≈8.5%)** — ~1% receive, ~3% withdrawal, up to ~4.5% FX | 2–5 days | Full KYC: ID + proof of address |
| **Wise** | ✅ Yes, with limits | Clients sending to Wise details | Withdraw to Egyptian bank | Lower FX cost than Payoneer | 1–3 days | Full KYC |
| **Fiverr** → Payoneer | ✅ | Fiverr buyers | Via Payoneer | Fiverr takes 20% **plus** Payoneer cost | 14-day clearance + payout | Fiverr + Payoneer KYC |
| **Upwork** → Payoneer | ✅ | Upwork clients | Via Payoneer | Upwork 10% + Connects cost + Payoneer | 5-day clearance + payout | Upwork + Payoneer KYC |
| **Direct bank wire (SWIFT)** | ✅ | Corporate clients | Straight to Egyptian bank | Flat $15–40 — **cheapest at high value** | 2–5 days | Bank account only |
| **Domestic: InstaPay / bank / Vodafone Cash** | ✅ | Egyptian clients only | Instant | **≈0%** | **Minutes** | None beyond existing accounts |
| **Gumroad** | ⚠️ Needs confirming | Digital product buyers | Reported to support Egypt via direct bank (ACH USD); PayPal alternative is useless here | 10% + ~2.9%+$0.30 | Weekly, Fridays, $10 min | Seller verification |
| PayPal | ❌ **Cannot receive** | — | — | — | — | — |

⚠️ **Wise caveat:** the Wise card is not issued to Egyptian residents. Wise works as a
receive-and-withdraw rail, not as a spending account.

⚠️ **Gumroad caveat:** sources conflict on whether Egypt is on the direct-bank-deposit
list. Since the PayPal fallback does not work for Egypt, Gumroad is only viable if direct
deposit is confirmed. **Confirm before building any product around it** — see step 3 below.

---

## Recommended stack

**Tier 1 — set up now, this is the backbone**
> **Payoneer.** It is the rail that connects to Fiverr, Upwork and direct clients
> simultaneously. The ~8.5% cost is real but it is the price of access, and it is far
> cheaper than not being able to get paid at all.

**Tier 2 — set up alongside**
> **Wise**, for direct clients who will send to Wise details. Lower FX cost than Payoneer,
> so it is the better rail for larger direct invoices.

**Tier 3 — already available, use immediately**
> **Domestic transfer for Egyptian clients.** Zero fees, instant, no KYC wait. This is why
> Segment D (regional leads) is the fastest realistic route to a first payment — it needs
> no new payment infrastructure at all.

**Tier 4 — for large direct contracts only**
> **SWIFT bank wire.** At $2,000+ a flat $15–40 fee beats every percentage-based rail.

---

# HUMAN ACTION REQUIRED

**Task:** Create and verify a Payoneer account, and a Wise account.

**Why:** I cannot create financial accounts, submit identity documents, or complete KYC —
those are legally yours to perform, and they require your real identity documents. Without
a receiving rail, a closed deal cannot convert into money. Everything else in this
operation is already built and waiting on this.

**Where:**
1. `payoneer.com` — Sign Up
2. `wise.com` — Register

**What to do:**
1. Register on Payoneer with your own real name, exactly as written on your national ID
   or passport. Any mismatch fails verification later and is painful to unwind.
2. Complete KYC: national ID or passport, plus proof of address (a utility bill or bank
   statement in your name).
3. Add your Egyptian bank account as the withdrawal destination. The account holder name
   must match the Payoneer account name.
4. Repeat on Wise.
5. **Also confirm Gumroad**, only if you want to sell digital products later: open
   `gumroad.com` → Settings → Payments, select Egypt, and tell me whether it offers
   *direct bank deposit* or *PayPal only*. That one answer decides whether offer O10 is
   viable. It takes 60 seconds and requires no commitment.

**Do NOT:**
- Do NOT send me your password, OTP, PIN, card number, recovery codes, or ID scans.
- Do NOT use anyone else's identity or bank account.
- Do NOT pay for any "verification service", "account approval" or "guaranteed KYC"
  offer — all of these are scams. Both platforms are free to open.
- Do NOT open a PayPal account expecting to receive money into it. It will not work.

**Time required:** ~20 minutes of your time. Verification then takes 1–3 business days,
during which everything else continues.

**After you finish:** tell me **"DONE — Payoneer"** (and **"DONE — Wise"**, and the
Gumroad answer if you checked).

**What I will do next:** you do not need to wait for this. Outreach, gig setup and
delivery all proceed in parallel — the rail only has to exist by the time someone says yes.

---

# PAID ACTION — HUMAN APPROVAL REQUIRED

## Upwork Connects

| | |
|---|---|
| **Cost** | $15 for 100 Connects (one-off), or $19.99/month for Freelancer Plus (100 Connects/mo) |
| **What changed** | Upwork no longer gives new accounts free starter Connects. The Basic free plan now gives **10 Connects per month** — roughly 1–2 proposals. Bonus Connects are released only after you buy a bundle or subscribe. |
| **Expected benefit** | Access to genuine contract work with real budgets. Realistically 1 client from ~20–30 well-targeted proposals in a niche this specific. |
| **Free alternatives** | Fiverr (free to list), Cad Crowd (free profile), PeoplePerHour (free tier), and direct outreach — which costs nothing and is not rate-limited by anybody. |
| **Is it necessary?** | **No — not yet.** Every channel in the current plan is free. |
| **Expected ROI** | Good *once there is a portfolio and a first testimonial*; poor before that, because proposals from a zero-history account convert badly regardless of how many Connects you burn. |
| **My recommendation** | **Do not spend this yet.** Revisit after the first paid job, and fund it from that revenue rather than from zero. If you want it sooner, the $15 one-off beats the subscription — no recurring commitment. |

**Approve or decline. I will not spend anything without you saying so explicitly.**
