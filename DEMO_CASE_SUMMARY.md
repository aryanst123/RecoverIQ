# Demo Case for Manual Override - Summary

## Purpose
Demonstrate Manual Override capability during live judge demo.

## Demo Case Details

**Case ID:** `case_DEMO_OVERRIDE`  
**Customer ID:** `cust_DEMO_OVERRIDE`  
**Payment ID:** `pay_DEMO_OVERRIDE`

**Key Characteristics:**
- Amount: ₹2,500.00 (high enough for all actions including ESCALATE)
- Age: 24 hours (well within 30-day recovery window)
- State: RECOVERY_ELIGIBLE
- Actions taken: 0/3
- Opt-out: No
- Active promise: No

## Eligibility Status

✅ **STOP** - Always eligible  
❌ **REMINDER** - Ineligible (incremental revenue below ₹250 threshold)  
❌ **PAYMENT_LINK** - Ineligible (incremental revenue below ₹250 threshold)  
✅ **PROMISE_TO_PAY** - Eligible (₹576.82 net recovery)  
✅ **ESCALATE** - Eligible (₹852.67 net recovery) ← **RecoverIQ Recommendation**

## Demo Flow

### Step 1: Find Demo Case
- Navigate to Recovery Queue
- Demo case appears at top with **DEMO** badge and blue highlight
- Shows: "₹2,500 · Insufficient Funds · 24h elapsed"

### Step 2: View RecoverIQ Decision
- Click on demo case
- Case Detail shows **"DEMO - Manual Override"** badge
- RecoverIQ recommends: **ESCALATE** (₹852.67 net recovery, 87% confidence)

### Step 3: Review Override Options
- Click **"Review / Override"** button
- Modal shows 5 actions with eligibility:
  - ✅ STOP - Eligible (Safe)
  - ❌ REMINDER - Blocked: "Expected incremental revenue below threshold ₹250.0"
  - ❌ PAYMENT_LINK - Blocked: "Expected incremental revenue below threshold ₹250.0"
  - ✅ PROMISE_TO_PAY - Eligible (Expected Net: ₹576.82)
  - ✅ ESCALATE - Eligible (Expected Net: ₹852.67) [Autonomous Default]

### Step 4: Manual Override
- Operator selects **PROMISE_TO_PAY** (overriding RecoverIQ's ESCALATE recommendation)
- Enters justification: "Customer prefers commitment-based approach per phone conversation"
- Clicks **"Confirm Override to PROMISE_TO_PAY"**

### Step 5: Backend Safety Gate
- Request sent to backend with operator justification
- Backend validates action is genuinely eligible
- Backend safety gate passes
- Action executes
- Audit record created with override justification

### Step 6: Simulate Payment
- Click green **"Simulate Customer Payment"** button
- Webhook processes with test-mode signature
- Case transitions to **RECOVERED**
- Audit trail records payment reconciliation

## Distinguishes
- **Economically preferred** (RecoverIQ chooses ESCALATE) vs **Eligible alternative** (operator chooses PROMISE_TO_PAY)
- **Ineligible by policy** (REMINDER/PAYMENT_LINK below threshold) vs **Safety blocked** (none in this case)
- **Autonomous decision** vs **Human override with justification**

## Technical Notes

### Backend (server.py)
- Added `_seed_manual_override_demo_case()` method
- Creates case with recent timestamp (24 hours ago)
- Clearly marked as DEMO in failure reason
- Isolated from benchmark/evaluation (not in Phase 12)
- Uses authoritative eligibility rules from `policy/eligibility.py`

### Frontend
- `Cases.tsx`: Blue highlight + "DEMO" badge for easy identification
- `CaseDetail.tsx`: "DEMO - Manual Override" badge on case header
- No hardcoded eligibility - backend remains authoritative
- Manual Override modal already correctly implemented

### Existing 40 Cases
- Remain unchanged
- 188 days old (outside recovery window by design)
- Only STOP eligible (correct behavior)
- Used for actual benchmark/evaluation

## Files Modified
1. `server.py` - Added demo case seeding
2. `frontend/src/pages/Cases.tsx` - Added DEMO badge/highlight
3. `frontend/src/pages/CaseDetail.tsx` - Added DEMO badge

## Not Modified
- Simulator/DGP semantics
- Phase 9/10/11/12 evaluation
- ML models or policies
- Benchmark logic or results
- Historical case data
- Eligibility rules

---

**Status:** Ready for live demo ✅
