# Lead Database — Cycle 001

## Integrity rules applied
- Every company below was surfaced in live search this cycle and is real.
- **No email address or phone number is recorded here, because I could not verify one.**
  This session's network egress blocks these company domains, so any contact detail I wrote
  would be a guess. Guessed contacts bounce, damage sender reputation, and are exactly the
  fabrication this operation forbids.
- The `Contact route` column is therefore a **capture instruction**, not a contact.
  Saif captures the real detail in ~2 minutes per company (procedure at the bottom).
- Named individuals are deliberately absent for the same reason — find the real person on
  LinkedIn at capture time.

---

## Segment A — BIM outsourcing bureaus (highest repeat value)
These firms resell offshore MEP capacity as their business model. They hire continuously,
they are structurally comfortable with remote offshore engineers, and one won relationship
produces recurring monthly work. **Offer O4 + O1. Message M1.**

| # | Company | Website | Why they may buy | Est. value | Score |
|---|---|---|---|---|---|
| A1 | United-BIM | united-bim.com | Dedicated MEP BIM outsourcing arm; works with contractors, subs and VDC teams; US market | $400–2,000/mo recurring | 88 |
| A2 | Tejjy Inc. | tejjy.com | Maryland-based, 8A/WOSB certified; MEP in Revit + CAD; broad client mix incl. GCs and subs | $400–1,800/mo | 85 |
| A3 | Excelize | excelize.com | Publishes $25–55/hr client rates and a 24-hour quote turnaround — a fast-moving buyer | $300–1,500/mo | 84 |
| A4 | eLogicTech | elogictech.com | MEP coordination and clash detection focus — needs modellers who understand systems, not just geometry | $300–1,200/mo | 80 |
| A5 | Outsource BIM Services (Optimar Precon) | outsourcebimservices.us | 3D MEP modelling, shop drawings, scan-to-BIM, as-builts — matches O4/O5/O9 exactly | $300–1,200/mo | 79 |
| A6 | Hi-Tech CADD Services | hitechcaddservices.com | Large established MEP BIM outsourcer | $300–1,200/mo | 76 |
| A7 | urcadservices | urcadservices.com | Explicitly markets outsourced MEP BIM | $200–900/mo | 72 |
| A8 | Gsource Technologies | gsourcedata.com | Publishes on electrical drafting outsourcing economics — already sells this exact service | $200–900/mo | 71 |

## Segment B — Specialist drafting / fire-alarm firms
Smaller, faster decisions, and a direct match for O5. **Message M4.**

| # | Company | Website | Why they may buy | Est. value | Score |
|---|---|---|---|---|---|
| B1 | Unicad, Inc. | unicad.net | Fire alarm design + shop drawings is their entire business — pure overflow candidate | $150–600/job | 78 |
| B2 | Draft Tech Design | draft-tech.com | Fire alarm CAD drafting for contractors, developers, architects; also security and low voltage | $150–600/job | 77 |
| B3 | Formative Concepts | formativeconcepts.com | Fire protection drafting — sprinkler and alarm | $150–500/job | 73 |
| B4 | Advanced Mechanix | advancedmechanix.com | Publishes an electrical drafting outsourcing guide — actively in this market | $150–500/job | 70 |
| B5 | Best Bid Estimating | bestbidestimating.com | Publishes extensively on contractors outsourcing electrical drafting; likely subcontracts | $150–500/job | 69 |

## Segment C — Platform presence (inbound, not outbound)
Not "leads" — channels where buyers find Saif. Set up once, they work in the background.

| # | Platform | URL | Action | Cost | Score |
|---|---|---|---|---|---|
| C1 | Fiverr | fiverr.com | Publish gigs O1, O2, O3 | **Free** | 76 |
| C2 | Cad Crowd | cadcrowd.com | Create freelance profile — Revit MEP + fire alarm categories both active | **Free** | 58 |
| C3 | PeoplePerHour | peopleperhour.com | Profile + proposals within free monthly allowance | **Free tier** | 60 |
| C4 | Upwork | upwork.com | **PAID — see approval request.** 10 free Connects/month only | $15 or $19.99/mo | 45 |

## Segment D — Regional (fastest cash, lowest friction)
No verified company list yet — this segment is found by search, not by directory, and
requires Saif's logged-in LinkedIn. **This is the highest-priority segment for speed**
because payment can be domestic (EGP, InstaPay / bank transfer), skipping every
international payment obstacle. **Message M3.**

| Target profile | Where to find | Why it is fastest |
|---|---|---|
| Egyptian MEP consultants & contractors (Cairo, Giza, New Capital, 6th October) | LinkedIn search: `MEP consultant Egypt`, `مكتب استشاري كهرباء`; Egyptian engineering Facebook groups | Domestic payment, shared language, referrals travel fast in a small market |
| Gulf MEP consultants & contractors (KSA, UAE, Qatar) | LinkedIn search: `MEP Manager Saudi Arabia`, `Electrical Design Manager UAE`; GulfTalent company profiles | Same timezone, Arabic, established Egypt→Gulf remote norm, far higher budgets |
| Egyptian/Gulf BIM managers | LinkedIn: `BIM Manager` + country filter | They personally feel the schedule-production pain the demo solves |

---

## Contact capture procedure — 2 minutes per company
Do this at the moment of sending, not in bulk. A contact captured today and used today
is worth ten harvested and left to rot.

1. Open the company website → `Contact` / `Contact Us` page. Record the published business
   email exactly as written. If only a form exists, note "form only".
2. Open LinkedIn → search the company → `People` tab → filter by title:
   `BIM Manager`, `Production Manager`, `MEP Lead`, `Resourcing`, `Operations Manager`.
3. Record the **real person's name and their LinkedIn profile URL**. Prefer a named person
   over `info@` every time — `info@` is a graveyard.
4. Note one true, specific thing about the company from their site or the person's recent
   activity. This becomes the OBSERVATION line in the message. If you cannot find one that
   is genuinely true, **delete that line** rather than inventing it.
5. Log it in `ops/funnel.csv` with status `contacted` and the date.

**Do not** use email-guessing tools, scrapers, or bought lists. Bounces poison the sending
domain and the resulting reply rate is worse than sending fewer, better messages.

## Send discipline
- **Maximum 15–20 personalised messages per day.** More than that from a new Gmail address
  gets throttled or spam-foldered, and quality collapses.
- Segment A and B by email + a LinkedIn connection note. Segment D by LinkedIn only.
- Follow-ups: M6 at day 4, M7 at day 11. Then stop permanently.
