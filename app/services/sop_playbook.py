"""Comprehensive Dental Front Desk SOP & Objection Handling Playbook.

Directly derived from 'IRA Ai Sop - Objection Handling.csv'.
Used by GeminiEvaluationService to evaluate trainee adherence to official
Spot on Schedulers / Dental Clinic standard operating procedures.
"""

from typing import Any, Optional

DENTAL_SOP_RULES: list[dict[str, Any]] = [
    # ─── SECTION 1: SELECT OFFICE / SYSTEM COMPLIANCE ───
    {
        "id": "sop_system_down",
        "csv_row": 1,
        "section": "select office",
        "title": "System Down / Computer Freeze Protocol",
        "trigger_condition": "Trainee's PMS or computer freezes, reboots, or is offline during the call.",
        "approved_verbiage": (
            "If taking time: 'Hey [pt name], sorry my system is down right now, I am just restarting my computer. "
            "In the meantime can I collect a few details from you if you could wait for a couple of minutes, or shall I get back to you after a while once the system is up?'\n"
            "If completely frozen: 'Hey [pt name], my system just froze right now. I cannot confirm the appointment right now, "
            "but I can give you a tentative date, and once the system is up I will call you back and confirm it.'"
        ),
        "key_rule": "Buy time politely while speaking. Never hang up abruptly. Always offer tentative date + confirmed callback.",
    },
    {
        "id": "sop_spanish_caller",
        "csv_row": 2,
        "section": "select office",
        "title": "Spanish-Speaking Patient Protocol",
        "trigger_condition": "Caller speaks Spanish or asks if anyone speaks Spanish ('¿Habla español?').",
        "approved_verbiage": (
            "- 'I apologize, I don't speak Spanish (Lo siento muchísimo. Yo no hablo español).'\n"
            "- 'Please hold the line, let me transfer your call (Espera un momento, déjeme transferir su llamada).'\n"
            "- 'Is it okay if I arrange a call back for you with our Spanish speaker? (¿Está bien si programo una llamada para usted con nuestro hablante de español?)'"
        ),
        "key_rule": "Politely apologize in Spanish, then transfer or offer a callback with a Spanish-speaking team member.",
    },
    {
        "id": "sop_doctor_request",
        "csv_row": 3,
        "section": "select office",
        "title": "Caller Demands to Speak Directly with Doctor",
        "trigger_condition": "Caller demands to speak with the doctor on the phone immediately.",
        "approved_verbiage": (
            "- Standard: 'Hey, Dr. is busy with a patient, is there anything I can help you with?'\n"
            "- If office is closed: 'Hey, Dr. is not in today because we are closed, is there anything I can help you with?'\n"
            "- If they insist: 'Hey, Dr. is busy with a patient; if I can take the message for you, I will pass on the message to them and they will call you back.'\n"
            "- If they refuse details: 'Hey, the more details you can give me, the faster I can arrange a call back.'"
        ),
        "key_rule": "CRITICAL: NEVER put caller on hold to search for the doctor or interrupt clinical chair time. Take message for callback.",
    },
    {
        "id": "sop_note_taking_pauses",
        "csv_row": 4,
        "section": "select office",
        "title": "Note-Taking Pauses (Avoiding Dead Air)",
        "trigger_condition": "Trainee needs a pause to enter notes or lookup information in the PMS.",
        "approved_verbiage": (
            "'Can you please give me a moment while I note down all that you are informing so that I can inform the team so they can be prepared to take best care of you.'"
        ),
        "key_rule": "Prevent dead air (> 4-5 seconds of silence) by politely informing caller that you are taking notes for the clinical team.",
    },
    {
        "id": "sop_moving_away",
        "csv_row": 5,
        "section": "select office",
        "title": "Patient Moving Away from Town",
        "trigger_condition": "Patient states they are relocating or moving to another city/state.",
        "approved_verbiage": (
            "'[pt name], we are sorry to hear that you are leaving us and we wish you best of luck on your move! "
            "If ever you are back and want to come for an appointment, we are here for you. We will be happy to have you.'"
        ),
        "key_rule": "Express warm well-wishes, keep the door open for future visits, and flag account per office protocol.",
    },
    {
        "id": "sop_billing_dept",
        "csv_row": 6,
        "section": "select office",
        "title": "Billing / Other Department Inquiry",
        "trigger_condition": "Caller demands the billing department or financial coordinator.",
        "approved_verbiage": (
            "'Hey, the person who handles billing is not available at the moment. Let me take all your information and I will pass it to them. "
            "They will get back to you by [within 2 business days]. Is that okay?' (If patient refuses, escalate to office manager immediately)."
        ),
        "key_rule": "Collect caller details, promise callback within 2 business days, and escalate if caller is irate or urgent.",
    },
    {
        "id": "sop_remote_inquiry",
        "csv_row": 7,
        "section": "select office",
        "title": "Curiosity Regarding Remote / Answering Service Role",
        "trigger_condition": "Caller asks: 'I've never seen you in the office, do you work remotely?' or 'Are you an answering service?'",
        "approved_verbiage": (
            "'Yes, I completely understand your curiosity! I work remotely to help the team with this part of the process, "
            "and I work closely with them to collect all the necessary information so that when they have you in the office, "
            "they have more time to focus on taking best care of you.'"
        ),
        "key_rule": "Empathize with curiosity and positively reframe remote scheduling as enabling the in-office team to focus 100% on patient care.",
    },

    # ─── SECTION 2: SEARCH PATIENT / ACCOUNT STATUS ───
    {
        "id": "sop_repeat_offender",
        "csv_row": 8,
        "section": "Search Patient",
        "title": "Repeated Appointment Offender (Frequent Cancellations / No-Shows)",
        "trigger_condition": "Caller has a history of repeated missed appointments, chronic reschedules, or no-shows.",
        "approved_verbiage": (
            "'I apologize [pt name], but it looks like we are booked out. What I can advise you to do is, on a day when you are available, "
            "call the office to see if there is any same-day appointment available.'"
        ),
        "key_rule": "Do not tie up prime future slots for repeat offenders; guide them to same-day call-in openings or deposit requirements.",
    },
    {
        "id": "sop_archived_patient",
        "csv_row": 9,
        "section": "Search Patient",
        "title": "Archived / Dismissed Patient Protocol",
        "trigger_condition": "Patient chart is archived or flagged that doctor no longer sees them.",
        "approved_verbiage": (
            "If true emergency: Book emergency triage per clinical safety protocol.\n"
            "If general exam/cleaning: 'I apologize [pt name], but it looks like we are booked out. What I can advise you to do is, "
            "on a day when you are available, call the office to see if there is any same-day appointment available,' or refer to insurance provider directory."
        ),
        "key_rule": "Never argue or tell the patient they are blacklisted; offer same-day emergency protocol if in pain or guide to insurance directory.",
    },
    {
        "id": "sop_inactive_patient",
        "csv_row": 10,
        "section": "Search Patient",
        "title": "Inactive Patient Reactivation",
        "trigger_condition": "Patient file is marked inactive in PMS.",
        "approved_verbiage": (
            "Check PMS reason. If moved away and returned: Schedule 3-4 days out to give office team time to review chart.\n"
            "If inactive due to unpaid balance or rude behavior: 'Hey [pt name], I do not have an appointment available right away. "
            "Let me take your information and give you a call back if anything opens up.'"
        ),
        "key_rule": "Audit PMS chart notes before reactivation. Never book immediate slots without resolving past chart flags.",
    },
    {
        "id": "sop_balance_due",
        "csv_row": 11,
        "section": "Search Patient",
        "title": "Patient Has Outstanding Balance Due",
        "trigger_condition": "Patient has an overdue balance in their chart notes.",
        "approved_verbiage": (
            "'Hey [pt name], I'd be happy to schedule an appointment for you! I see you currently have a balance of [amount], "
            "and we do need to collect that before booking the appointment. How would you like to take care of it today?'\n"
            "If patient refuses: 'Unfortunately, the balance has been pending for a while, and office protocol requires collecting payment before scheduling.'"
        ),
        "key_rule": "Require balance resolution prior to confirming new appointments. Offer secure payment options.",
    },

    # ─── SECTION 3: REASON OF APPOINTMENT / CLINICAL & RECORDS ───
    {
        "id": "sop_first_visit_rapport",
        "csv_row": 12,
        "section": "Reason of Appointment",
        "title": "1st Appointment Workflow & Rapport Building",
        "trigger_condition": "New patient inquiring about what happens during their first visit.",
        "approved_verbiage": (
            "'Hey [pt name], we can definitely help you with that! Please know that your 1st appointment is going to be for a comprehensive exam "
            "with the doctor, so the doctor can take a look at the affected area and see what it looks like. Then, if clinically needed, "
            "the doctor will take X-rays to diagnose the area and go over all different treatment options with you. "
            "Dr. [Name] loves her patients and treats everyone like family!'\n"
            "(If implant consult: mention 3D cone beam scan for safe, precision bone planning)."
        ),
        "key_rule": "Always explain exam-first flow, clinical diagnosis need, and build personal warmth around the doctor.",
    },
    {
        "id": "sop_external_xrays",
        "csv_row": 13,
        "section": "Reason of Appointment",
        "title": "Existing X-Rays from Another Dental Office",
        "trigger_condition": "Patient states they already have X-rays from another clinic and do not want to pay for new ones.",
        "approved_verbiage": (
            "'If you've had X-rays taken within the last 6 months, you're welcome to send them to us by email at least 48 hours before your appointment. "
            "Please make sure the images include the date they were taken. If the quality of the X-rays is good and, during your exam, "
            "the doctor sees that your oral condition hasn't changed since then, we may not need to take new ones.'"
        ),
        "key_rule": "Enforce: (1) 6-month validity rule, (2) 48-hour advance email rule, (3) doctor must verify diagnostic clarity.",
    },
    {
        "id": "sop_medical_clearance",
        "csv_row": 14,
        "section": "Reason of Appointment",
        "title": "Medical Clearance Protocol (Pregnancy / Systemic Conditions)",
        "trigger_condition": "Patient discloses pregnancy (OBGYN), joint replacement, heart conditions, or premedication requirements.",
        "approved_verbiage": (
            "'Hey [pt name], for your safety Dr. needs a medical clearance from your physician. Can you share your medical doctor's name, phone, "
            "and fax number so we can request that clearance before your treatment appointment?'"
        ),
        "key_rule": "Collect MD contact info and confirm clearance on file prior to booking clinical procedures.",
    },
    {
        "id": "sop_specialist_referral",
        "csv_row": 15,
        "section": "Reason of Appointment",
        "title": "Specialist Referral Request",
        "trigger_condition": "Patient demands a direct referral to an oral surgeon, endodontist, or orthodontist without an exam.",
        "approved_verbiage": (
            "'Hey [pt name], I understand that you need a specialist referral, but the doctor still needs to complete a preliminary examination "
            "and diagnosis first to determine the exact type of referral and clinical notes the specialist will need. Let's get that initial exam scheduled.'"
        ),
        "key_rule": "Explain that doctor must evaluate condition to prepare proper clinical referral.",
    },
    {
        "id": "sop_dental_anxiety",
        "csv_row": 16,
        "section": "Reason of Appointment",
        "title": "Dental Anxiety & Fear of Dentists / Needles",
        "trigger_condition": "Caller expresses fear, nervous feelings, needle phobia, or past traumatic dental experiences.",
        "approved_verbiage": (
            "'Hey [pt name], I totally understand how you feel! So many of our patients feel nervous before coming in. "
            "Our entire team and Dr. [Name] are known for being extremely gentle and patient. We never rush, we explain every step beforehand, "
            "and we offer comfort options so you will be completely relaxed.'"
        ),
        "key_rule": "Validate fear empathetically; reassure gentle bedside manner and comfort/sedation accommodations.",
    },
    {
        "id": "sop_direct_treatment_no_exam",
        "csv_row": 17,
        "section": "Reason of Appointment",
        "title": "Direct Treatment Request Without Exam ('My last dentist said...')",
        "trigger_condition": "Patient wants to book straight into a crown, root canal, or extraction without an initial exam.",
        "approved_verbiage": (
            "'Mr./Mrs. [pt name], I completely understand! While we respect your previous dentist's diagnosis, our doctor must perform their own "
            "independent examination and take current diagnostic X-rays to verify the condition of the tooth and bone. "
            "Depending on the doctor's diagnosis and schedule, same-day treatment may be initiated, but the exam comes first.'"
        ),
        "key_rule": "Respect previous recommendations but firmly maintain that doctor must complete independent exam before performing treatment.",
    },
    {
        "id": "sop_refuses_xrays",
        "csv_row": 18,
        "section": "Reason of Appointment",
        "title": "Patient Refuses All Dental X-Rays",
        "trigger_condition": "Patient adamantly refuses to allow any X-rays to be taken.",
        "approved_verbiage": (
            "'[pt name], I understand your concern about X-rays. However, visual exams only show the surface of the tooth. "
            "X-rays are clinically required to evaluate the roots, underlying bone structure, and decay hidden between teeth. "
            "Without X-rays, the doctor cannot safely, legally, or ethically diagnose and treat you.'"
        ),
        "key_rule": "Explain the safety, diagnostic necessity, and legal requirement of dental radiographs.",
    },

    # ─── SECTION 4: INSURANCE & FEES / COST REBUTTALS ───
    {
        "id": "sop_out_of_network",
        "csv_row": 19,
        "section": "Insurance & Fees",
        "title": "Out-of-Network Insurance Rebuttal",
        "trigger_condition": "Patient has an insurance plan that the dental office does not accept or is out of network with.",
        "approved_verbiage": (
            "'Hey [pt name], while we are not in-network with that specific plan, we have many patients with your exact insurance who still choose "
            "our office because of the personalized, high-quality care that Dr. [Name] provides. We also offer an in-house dental savings membership "
            "and flexible options that often save patients as much or more than traditional insurance!'"
        ),
        "key_rule": "Reframe around care quality and present in-house dental membership plans / new patient specials.",
    },
    {
        "id": "sop_insurance_referral_help",
        "csv_row": 21,
        "section": "Insurance & Fees",
        "title": "Help Finding Another Doctor (Out-of-Network Referral)",
        "trigger_condition": "Patient asks the trainee: 'Who should I call?' or 'Can you find me an in-network doctor?'",
        "approved_verbiage": (
            "'The best thing would be to call the member services number on the back of your insurance card. "
            "They will have the most up-to-date, accurate directory of providers currently accepting your plan.'"
        ),
        "key_rule": "Direct patient to their insurance member services directory for in-network provider lists.",
    },
    {
        "id": "sop_insurance_maxed_out",
        "csv_row": 22,
        "section": "Insurance & Fees",
        "title": "Insurance Benefits Maxed Out",
        "trigger_condition": "Patient says their annual insurance benefit maximum has been reached for the year.",
        "approved_verbiage": (
            "'Thank you for letting us know! The good thing is that even though your benefits are maxed out, "
            "you still receive our contracted in-network discounted fee schedule for your visits. Also, addressing dental concerns early "
            "prevents far more expensive and invasive complications later when benefits renew.'"
        ),
        "key_rule": "Highlight that contracted fee discounts still apply and warn against delaying needed care.",
    },
    {
        "id": "sop_uncovered_procedure",
        "csv_row": 23,
        "section": "Insurance & Fees",
        "title": "Questioning Necessity If Insurance Does Not Cover Procedure",
        "trigger_condition": "Caller asks: 'Do I really need that procedure if my insurance refuses to cover it?'",
        "approved_verbiage": (
            "'I completely understand your frustration! Dental insurance policies are written to cover basic maintenance, not necessarily all clinical necessities. "
            "Dr. [Name] only recommends procedures that are essential to protect your health, save your natural tooth, and prevent painful infections.'"
        ),
        "key_rule": "Differentiate insurance coverage limitations from clinical health necessity.",
    },
    {
        "id": "sop_perio_vs_prophy_copay",
        "csv_row": 24,
        "section": "Insurance & Fees",
        "title": "Cleaning Covered 100% vs. Periodontal Maintenance Copay",
        "trigger_condition": "Patient complains: 'My card says cleanings are 100% covered, why is there a copay for periodontal maintenance?'",
        "approved_verbiage": (
            "'I completely understand your concern! Regular cleaning (prophylaxis) is preventive care for healthy gums without active disease. "
            "Periodontal maintenance is specialized medical follow-up for patients treated for gum disease/infection, which insurance categorizes and codes differently. "
            "Coming every 3-4 months keeps active bacteria from destroying bone.'"
        ),
        "key_rule": "Educate on clinical distinction between healthy prophy and perio maintenance. Strictly refuse fraudulent downcoding.",
    },
    {
        "id": "sop_unverified_promotion",
        "csv_row": 25,
        "section": "Insurance & Fees",
        "title": "Unverified Promotion Inquiries",
        "trigger_condition": "Caller claims they saw a promotional offer or discount that the scheduler is unaware of.",
        "approved_verbiage": (
            "'Hey, this might be a new promotion that just became active and I haven't received the memo yet! "
            "If you can send me a picture or screenshot of the promotion via text or email, we will verify it with the office manager and apply it if valid.'"
        ),
        "key_rule": "Never argue or flatly deny; politely ask for a screenshot/link to verify with office management.",
    },
    {
        "id": "sop_cost_extraction",
        "csv_row": 27,
        "section": "Insurance & Fees",
        "title": "Extraction Costing Rebuttal",
        "trigger_condition": "Patient demands to know the exact cost of a tooth extraction over the phone.",
        "approved_verbiage": (
            "If insured: Verify insurance first.\n"
            "If uninsured or insists on phone quote: 'Extraction costs depend entirely on whether the tooth is simple or surgical, root curvature, "
            "and whether there is active infection or bone involvement. The doctor must take an X-ray and evaluate the tooth in person to give you an exact price. "
            "Our comprehensive exam and X-ray special is only [amount], and the doctor will review all pricing before doing any work.'"
        ),
        "key_rule": "Refuse arbitrary flat phone quotes; explain clinical variables (simple vs surgical) and offer exam special.",
    },
    {
        "id": "sop_cost_root_canal",
        "csv_row": 29,
        "section": "Insurance & Fees",
        "title": "Root Canal Costing Rebuttal",
        "trigger_condition": "Patient insists on a phone quote for root canal and crown.",
        "approved_verbiage": (
            "'Root canal pricing depends on which tooth is affected—front teeth have 1 canal, while molars have 3 to 4 canals—as well as the degree of infection "
            "and whether a core buildup and crown are required. Because of this, the doctor must complete a diagnostic exam and X-ray first to give you an exact quote. "
            "We go over all costs and financing options before any treatment begins.'"
        ),
        "key_rule": "Explain anatomical factors (number of canals, molar vs front) and promote diagnostic exam first.",
    },
    {
        "id": "sop_cost_filling",
        "csv_row": 30,
        "section": "Insurance & Fees",
        "title": "Filling Costing Rebuttal",
        "trigger_condition": "Patient insists on knowing the cost of a filling over the phone.",
        "approved_verbiage": (
            "'Filling costs depend on the number of tooth surfaces involved (1, 2, 3, or more surfaces) and the depth of the decay near the nerve. "
            "The doctor needs to examine the tooth and review current X-rays to see how many surfaces need restoration before giving an accurate fee.'"
        ),
        "key_rule": "Explain surfaces and depth dependency; offer diagnostic exam.",
    },
    {
        "id": "sop_cost_cleaning",
        "csv_row": 31,
        "section": "Insurance & Fees",
        "title": "Cost of Cleaning Inquiry",
        "trigger_condition": "Patient asks: 'How much is a basic cleaning?'",
        "approved_verbiage": (
            "'The type of cleaning required depends on gum health and bone levels. A standard routine cleaning is for healthy gums, while deeper cleanings "
            "are needed if there is tartar below the gumline. That's why your first visit begins with a comprehensive exam, gum measurements, and X-rays.'"
        ),
        "key_rule": "Explain that cleaning type is determined by clinical gum and bone diagnosis during exam.",
    },
    {
        "id": "sop_just_calling_for_info",
        "csv_row": 32,
        "section": "Insurance & Fees",
        "title": "Patient 'Just Calling for Information'",
        "trigger_condition": "Caller hesitates and states: 'I'm just calling for information right now, not booking.'",
        "approved_verbiage": (
            "'Of course, I can definitely help you with that! What specific questions or symptoms can I help answer for you? ... "
            "Let me share with you that we have a new patient comprehensive exam and X-ray special for [amount]. "
            "Our schedule fills up fast, so let's reserve a tentative time on Dr. [Name]'s calendar while we're talking.'"
        ),
        "key_rule": "Be warm, helpful, probe for the underlying dental concern, and guide toward holding a tentative spot.",
    },
    {
        "id": "sop_weekend_out_of_pocket",
        "csv_row": 33,
        "section": "Insurance & Fees",
        "title": "Weekend Out-of-Pocket Payment Protocol",
        "trigger_condition": "Patient booking on weekends when insurance clearinghouses are closed.",
        "approved_verbiage": (
            "'Since it's the weekend, insurance companies are closed and we are unable to verify live benefits. "
            "Weekend appointments require payment out-of-pocket at time of service, and our billing team will file your claim first thing Monday "
            "and refund any overpayment directly back to you.'"
        ),
        "key_rule": "Explain weekend insurance limitation transparently and reassure claim filing + refund on Monday.",
    },

    # ─── SECTION 5: DATE & TIME OF APPOINTMENT / URGENCY & TRIAGE ───
    {
        "id": "sop_negotiating_timings",
        "csv_row": 34,
        "section": "date & time of appt",
        "title": "Negotiating Appointment Times / Doctor Chair Time",
        "trigger_condition": "Caller insists on a specific unavailable time or questions why slots are limited.",
        "approved_verbiage": (
            "'I completely understand that you need that specific time! Dr. [Name] spends dedicated one-on-one time with every patient "
            "so you never have to wait in a crowded lobby. Because of that dedicated scheduling, slots fill quickly. "
            "Let me offer you [closest alternative slot], and I will place you on our VIP priority cancellation list if an earlier slot opens up.'"
        ),
        "key_rule": "Highlight dedicated doctor chair time without overbooking, and offer closest opening + VIP cancellation list.",
    },
    {
        "id": "sop_cleaning_with_exam_same_day",
        "csv_row": 35,
        "section": "date & time of appt",
        "title": "Requesting Cleaning & Exam Together on Same Day",
        "trigger_condition": "Patient asks: 'Can I get my exam and cleaning done at the same time during my lunch break?'",
        "approved_verbiage": (
            "'Hey [pt name], I understand you'd love to get both done in one visit! The doctor first completes a full exam and periodontal evaluation "
            "to check your gum health. If your gums are healthy and our hygiene schedule permits, we will do our best to take care of it right then. "
            "If specialized or deep cleaning is required, we schedule dedicated time to make sure you get the thorough care you deserve.'"
        ),
        "key_rule": "Set realistic expectations: exam and gum measurements come first; cleaning follows if clinically appropriate and time permits.",
    },
    {
        "id": "sop_emergency_slot_unavailable",
        "csv_row": 36,
        "section": "date & time of appt",
        "title": "Emergency Patient When Schedule is Booked Out",
        "trigger_condition": "Caller has acute dental pain/trauma but schedule is completely full.",
        "approved_verbiage": (
            "'I understand that there is nothing worse than a toothache! I will do everything possible to get you seen as soon as possible. "
            "Let me create a priority emergency triage opening for you, or have you come in right at [time] so the doctor can evaluate the pain between scheduled patients.'"
        ),
        "key_rule": "Never turn away an emergency toothache. Offer triage hold slot, work-in opening, or earliest morning priority.",
    },
    {
        "id": "sop_office_closed_pain",
        "csv_row": 37,
        "section": "date & time of appt",
        "title": "Patient in Severe Pain When Office is Closed",
        "trigger_condition": "After-hours caller in severe acute pain when office is closed.",
        "approved_verbiage": (
            "'Hey, I understand you are experiencing discomfort, but our physical clinic is closed right now. "
            "However, if you have severe swelling spreading to your eye or throat, difficulty swallowing or breathing, or uncontrollable bleeding, "
            "please go to the nearest emergency room immediately. Otherwise, I can book you for our very first emergency opening at 8:00 AM tomorrow morning.'"
        ),
        "key_rule": "Triage for red-flag ER symptoms (facial swelling/breathing/swallowing) and book first opening next morning.",
    },
    {
        "id": "sop_late_evening_weekend_request",
        "csv_row": 38,
        "section": "date & time of appt",
        "title": "Late Evening or Weekend Availabilities",
        "trigger_condition": "Patient asks: 'Why don't you have late evening or weekend hours?'",
        "approved_verbiage": (
            "'I apologize for that limitation! To ensure our clinical team provides the highest focus and precision, our clinical hours are [hours]. "
            "I can offer you our earliest morning appointment at [8:00 AM] or our last afternoon slot at [4:00 PM] so it won't disrupt your work day.'"
        ),
        "key_rule": "Offer first-morning or last-afternoon edge slots to accommodate work schedules.",
    },
    {
        "id": "sop_unsure_of_schedule",
        "csv_row": 39,
        "section": "date & time of appt",
        "title": "Patient Unsure of Their Schedule",
        "trigger_condition": "Caller says: 'I need to check my calendar, I'm not sure when I'm free.'",
        "approved_verbiage": (
            "'No problem at all! Would you like me to hold a tentative time on Dr. [Name]'s schedule for you right now? "
            "You can check your calendar today, and if you need to adjust it, you can just reply to our text or call us back.'"
        ),
        "key_rule": "Offer a tentative placeholder reservation with easy rescheduling.",
    },
    {
        "id": "sop_urgency_unscheduled_treatment",
        "csv_row": 40,
        "section": "date & time of appt",
        "title": "Creating Sense of Urgency for Unscheduled Treatment",
        "trigger_condition": "Patient procrastinating root canal, crown, or deep cavity ('I'll wait a few weeks until work slows down').",
        "approved_verbiage": (
            "'[pt name], dental infections and fractured teeth flare up unpredictably, often over weekends, holidays, or during travel when clinics are closed. "
            "Delaying treatment allows bacteria to spread deeper into the bone, turning a straightforward repair into severe emergency pain or tooth loss. "
            "In the meantime, please avoid chewing on that side of your mouth and let's get you in this week.'"
        ),
        "key_rule": "Explain unpredictability of infections (weekend flare-ups), warn against tooth loss, and instruct not to chew on that side.",
    },

    # ─── SECTION 6: COLLECT PAYMENT / CARD HOLDS ───
    {
        "id": "sop_payment_link_security",
        "csv_row": 41,
        "section": "collect payment",
        "title": "Payment Link & Credit Card Security",
        "trigger_condition": "Caller questions whether the payment portal or card reservation is secure.",
        "approved_verbiage": (
            "'It is completely secure! Our payment portal is fully HIPAA and PCI compliant with 256-bit encryption. "
            "No one in our office has access to view or store your full card details.'"
        ),
        "key_rule": "Reassure HIPAA & PCI compliance, end-to-end encryption, and staff cannot view card details.",
    },
    {
        "id": "sop_refuses_to_pay_hold",
        "csv_row": 42,
        "section": "collect payment",
        "title": "Patient Refuses to Pay / Refuses Card Hold",
        "trigger_condition": "Patient refuses to provide card details or payment hold to reserve an appointment.",
        "approved_verbiage": (
            "'I understand your hesitation. This is Dr. Scott's office protocol because we reserve dedicated chair time exclusively for you "
            "without double-booking. Let me share your concern with the office manager to see if an exception can be approved, "
            "or we can schedule you for a same-day call-in opening.'"
        ),
        "key_rule": "Explain dedicated doctor time, escalate to office manager if patient pushes back, or offer same-day call-in.",
    },
    {
        "id": "sop_prepayment_rebuttal",
        "csv_row": 43,
        "section": "collect payment",
        "title": "Prepayment / $1 Reservation Hold Rebuttal",
        "trigger_condition": "Patient questions why a $1 card hold or reservation deposit is needed over the phone.",
        "approved_verbiage": (
            "'I completely understand your question! The $1 card hold simply reserves dedicated time on Dr. [Name]'s schedule exclusively for you. "
            "It prevents overbooking and ensures you don't have to wait in a crowded lobby. Your card is NOT charged for your appointment—it is only held "
            "in case of a missed appointment without notice—and you can still pay with cash or any card when you arrive at the office.'"
        ),
        "key_rule": "Explain: (1) reserves dedicated doctor time, (2) reduces lobby wait times, (3) not charged unless no-showed, (4) can pay cash upon arrival.",
    },

    # ─── SECTION 7: ONBOARDING / PAPERWORK (PPW) ───
    {
        "id": "sop_no_smartphone_paperwork",
        "csv_row": 45,
        "section": "ppw",
        "title": "Patient Does Not Have a Smartphone for Online Forms",
        "trigger_condition": "Patient says: 'I don't have a smartphone or computer to fill out online paperwork.'",
        "approved_verbiage": (
            "1) Ask if a friend or family member can help them open the link.\n"
            "2) Offer to email the link so they can complete it on a desktop computer.\n"
            "3) If still unable: 'No problem at all! Please arrive 15 to 20 minutes prior to your appointment time, "
            "and our front desk team will provide a sanitized office iPad or paper clipboard so you can complete everything comfortably in our lobby.'"
        ),
        "key_rule": "Provide frictionless alternatives: family assistance, desktop email, or arriving 15-20 minutes early for office iPad/paper forms.",
    },
]


def format_sop_playbook_for_prompt() -> str:
    """Formats all 41 SOP rules into a structured, readable markdown guide for the evaluator prompt."""
    sections: dict[str, list[dict[str, Any]]] = {}
    for rule in DENTAL_SOP_RULES:
        sec = rule["section"]
        sections.setdefault(sec, []).append(rule)

    lines: list[str] = [
        "## COMPREHENSIVE SPOT ON SCHEDULERS (DENTAL) SOP PLAYBOOK (ALL 41 RULES)",
        "Every single rule below is an official clinic protocol. Scan the conversation transcript for ANY of these situations.",
    ]

    for section_name, rules in sections.items():
        lines.append(f"\n### SECTION: {section_name.upper()}")
        for r in rules:
            lines.append(
                f"- **[{r['id']}] {r['title']}** (CSV Row {r['csv_row']}):\n"
                f"  - *Trigger Condition*: {r['trigger_condition']}\n"
                f"  - *Approved SOP Verbiage / Directives*:\n{r['approved_verbiage']}\n"
                f"  - *Mandatory Rule*: {r['key_rule']}\n"
            )

    return "\n".join(lines)


DENTAL_SOP_PLAYBOOK_PROMPT_TEXT = format_sop_playbook_for_prompt()
