#!/usr/bin/env python3
"""
Seed CMS content for ClinGroup (health) and Academy Portal (education).

Usage:
    python scripts/seed_cms.py

The script creates the tenants and their admin accounts if they do not already
exist, then seeds content.  It is fully idempotent: re-running it is safe.

Edit the MANAGER_* variables and TENANTS_TO_SEED list below to match your setup.
"""
from __future__ import annotations

import sys
from pathlib import Path
import httpx

# Absolute path to the demo-sites directory inside widget/
_DEMO_DIR = Path(__file__).parent.parent / "widget" / "demo-sites"

BACKEND_URL = "http://localhost:8000"

# ── Edit these ─────────────────────────────────────────────────────────────────
# Credentials for the tenant_manager account (the one you log in with in Streamlit)
MANAGER_EMAIL = "manager@concierge.com"
MANAGER_PASSWORD = "Manager1234!"

# One entry per tenant to provision.  Re-running is safe — existing tenants and
# users are detected and skipped; only missing content items are created.
TENANTS_TO_SEED = [
    {
        "name":           "ClinGroup",
        "slug":           "clingroup",
        "admin_email":    "admin@clingroup.com",
        "admin_password": "Admin1234!",
        "demo_subdir":    "clingroup",
        "widget_greeting": "Hi! I'm Cleo, your ClinGroup health assistant. How can I help you today?",
        "widget_theme":    "#0B5394",
    },
    {
        "name":           "Academy Portal",
        "slug":           "academy",
        "admin_email":    "admin@academy.com",
        "admin_password": "Admin1234!",
        "demo_subdir":    "academy",
        "widget_greeting": "Hi! I'm Alex, your Academy Portal assistant. Ask me about programs, enrollment, or student support!",
        "widget_theme":    "#4F46E5",
    },
]
# ───────────────────────────────────────────────────────────────────────────────


# ── ClinGroup content ──────────────────────────────────────────────────────────
_CLINGROUP_PERSONA = (
    "You are Cleo, a friendly and professional virtual health assistant for ClinGroup "
    "Medical Centre. You help patients find information about our services, departments, "
    "appointments, and general health topics. You are warm, reassuring, and always "
    "remind patients that serious medical concerns should be discussed with a qualified "
    "healthcare professional. You never provide diagnoses or prescribe treatments."
)

_CLINGROUP_GUARDRAILS = {
    "blocked_topics": ["legal advice", "financial investment", "academic admissions"],
    "refusal_tone": (
        "I'm here to help with health and ClinGroup-related queries only. "
        "For other topics, please contact the appropriate service."
    ),
    "enabled_tools": ["rag_search", "capture_lead", "escalate"],
}

_CLINGROUP_CONTENT = [
    # ── FAQs ──
    {
        "title": "What services does ClinGroup offer?",
        "content_type": "faq",
        "body": (
            "ClinGroup Medical Centre provides a full spectrum of healthcare services including "
            "general practice, specialist consultations, diagnostic imaging (X-ray, MRI, CT), "
            "pathology and blood testing, physiotherapy, mental health counselling, and a "
            "24-hour urgent care unit. We also operate an on-site pharmacy stocked with both "
            "prescription and over-the-counter medications. Our Telehealth service allows "
            "patients to consult with GPs and specialists remotely via video call."
        ),
    },
    {
        "title": "How do I book an appointment at ClinGroup?",
        "content_type": "faq",
        "body": (
            "Appointments can be booked online through the ClinGroup patient portal at "
            "patients.clingroup.com, by calling our reception on 1800-CLIN-GRP, or in person "
            "at the front desk. For urgent same-day appointments, please call before 9 AM. "
            "Telehealth appointments are available daily 7 AM–10 PM. New patients should arrive "
            "15 minutes early to complete registration. Cancellations require at least 24 hours' "
            "notice to avoid a late-cancellation fee."
        ),
    },
    {
        "title": "What should I do in a medical emergency?",
        "content_type": "faq",
        "body": (
            "If you are experiencing a life-threatening emergency — chest pain, difficulty "
            "breathing, loss of consciousness, severe bleeding, stroke symptoms (face drooping, "
            "arm weakness, speech difficulty), or suspected poisoning — call 000 immediately. "
            "Do not drive yourself to hospital. "
            "Our Urgent Care Unit on Level 1 handles non-life-threatening emergencies "
            "7 days a week, 6 AM–midnight, with average wait times under 30 minutes. "
            "For after-hours medical advice, the National Health Direct line is available 24/7."
        ),
    },
    {
        "title": "What medications are available at the ClinGroup pharmacy?",
        "content_type": "faq",
        "body": (
            "The ClinGroup in-house pharmacy carries a comprehensive range of prescription "
            "medications, over-the-counter analgesics (paracetamol, ibuprofen, aspirin), "
            "antihistamines, antacids, vitamins, and wound care supplies. Controlled substances "
            "require a valid prescription from a registered practitioner. Our pharmacists offer "
            "free medication reviews for patients on five or more regular medications and can "
            "advise on drug interactions, dosage, and storage. "
            "Pharmacy hours: Monday–Friday 8 AM–7 PM, Saturday 9 AM–4 PM."
        ),
    },
    {
        "title": "How do I access and request copies of my medical records?",
        "content_type": "faq",
        "body": (
            "Patients can access their medical records through the secure ClinGroup patient "
            "portal. Alternatively, submit a Medical Records Request Form available at reception "
            "or on our website. Under the Privacy Act 1988, you are entitled to access your "
            "health information. Processing takes 10–15 business days. A small administrative "
            "fee may apply for paper copies. Records are never shared with third parties without "
            "explicit written consent, except where required by law. Deceased patient records "
            "may be requested by authorised next-of-kin."
        ),
    },
    {
        "title": "What health insurance and payment options does ClinGroup accept?",
        "content_type": "faq",
        "body": (
            "ClinGroup bulk-bills Medicare-eligible consultations for patients with a valid "
            "Medicare card. We accept all major private health insurers: Medibank, Bupa, HCF, "
            "NIB, and HBF. Out-of-pocket gaps vary by specialist and procedure — our billing "
            "team can provide an upfront estimate before any elective procedure. "
            "Accepted payments: EFTPOS, Visa, Mastercard, Amex, and bank transfer. "
            "Payment plans are available for procedures over $500 via our finance partner. "
            "WorkCover, DVA, and NDIS patients are welcome — bring your relevant card."
        ),
    },
    {
        "title": "What are ClinGroup's opening hours?",
        "content_type": "faq",
        "body": (
            "Main Reception: Monday–Friday 7 AM–8 PM, Saturday 8 AM–5 PM, Sunday 9 AM–2 PM. "
            "Urgent Care Unit: 7 days 6 AM–midnight. "
            "Pharmacy: Monday–Friday 8 AM–7 PM, Saturday 9 AM–4 PM, Sunday closed. "
            "Pathology: Monday–Friday 7:30 AM–5 PM, Saturday 8 AM–12 PM. "
            "Telehealth: Daily 7 AM–10 PM. "
            "Public holidays: Urgent Care and Telehealth remain open; other services are "
            "reduced — call 1800-CLIN-GRP or check our website for specific holiday hours."
        ),
    },
    {
        "title": "Does ClinGroup offer mental health services?",
        "content_type": "faq",
        "body": (
            "Yes. ClinGroup's Mental Health Hub offers individual psychotherapy, cognitive "
            "behavioural therapy (CBT), trauma-focused therapy, and group support programs. "
            "Our team includes psychologists, psychiatrists, and mental health nurses. "
            "GP-referred patients may be eligible for up to 20 Medicare-subsidised psychology "
            "sessions per calendar year under a Mental Health Treatment Plan. "
            "We also provide EAP (Employee Assistance Program) services to corporate clients. "
            "If you are in crisis, call Lifeline on 13 11 14 or present to our Urgent Care "
            "Unit immediately — no referral is needed in a crisis."
        ),
    },
    # ── Pages ──
    {
        "title": "About ClinGroup Medical Centre",
        "content_type": "page",
        "body": (
            "ClinGroup Medical Centre was founded in 2004 by Dr. Meredith Holt with a vision "
            "to deliver integrated, patient-centred healthcare under one roof. Today ClinGroup "
            "operates three campuses — CBD, Northside, and Eastfield — serving over 80,000 "
            "active patients. Our multidisciplinary team of 200+ clinicians spans 35 medical "
            "specialties. ClinGroup is accredited by AGPAL (Australian General Practice "
            "Accreditation Limited) and holds ISO 15189 accreditation for our pathology lab. "
            "We are a privately owned, not-for-profit organisation that reinvests surpluses "
            "into staff training, infrastructure, and community health programs."
        ),
    },
    {
        "title": "Cardiology Department",
        "content_type": "page",
        "body": (
            "ClinGroup's Cardiology Department provides comprehensive assessment and management "
            "of heart and vascular conditions. Services include resting and stress ECG, "
            "echocardiography, Holter monitoring (24–72 hour rhythm recording), coronary "
            "angiography, pacemaker review, and cardiac rehabilitation. "
            "Our three consultant cardiologists — Dr. James Osei, Dr. Priya Nair, and "
            "Dr. Leon Marchetti — each hold fellowship with CSANZ. "
            "Conditions treated: atrial fibrillation, heart failure, coronary artery disease, "
            "hypertension, valvular disease, congenital heart conditions. "
            "A GP referral is required. Urgent assessments can be arranged within 48 hours."
        ),
    },
    {
        "title": "Pathology and Diagnostic Imaging",
        "content_type": "page",
        "body": (
            "ClinGroup's NATA-accredited pathology lab processes over 2,000 specimens daily. "
            "Tests include FBC, LFT, HbA1c, lipid panel, thyroid function, STI screening, "
            "COVID-19 PCR and RAT, urine culture, genetic testing, and tumour markers. "
            "Routine results available within 24 hours, urgent within 4 hours, via patient portal. "
            "Imaging services: plain X-ray, ultrasound, CT scan, and MRI. Contrast studies and "
            "interventional radiology are available by specialist referral. All imaging is "
            "interpreted by RANZCR-qualified radiologists. Fasting may be required — your GP "
            "will advise."
        ),
    },
    {
        "title": "Patient Privacy and Data Protection Policy",
        "content_type": "page",
        "body": (
            "ClinGroup collects and stores personal health information in accordance with the "
            "Privacy Act 1988 (Cth) and the Australian Privacy Principles (APPs). Health "
            "information is classified as sensitive data and receives the highest level of "
            "protection. Data is stored on encrypted Australian servers and never sold to third "
            "parties. Access is restricted to treating clinicians and authorised administrative "
            "staff on a need-to-know basis. Records are retained for a minimum of 7 years from "
            "last contact (or until the patient turns 25, whichever is later). Patients may "
            "access, correct, or request deletion of their records. ClinGroup uses ISO "
            "27001-certified security controls and conducts annual penetration testing."
        ),
    },
    {
        "title": "Physiotherapy and Rehabilitation Services",
        "content_type": "page",
        "body": (
            "ClinGroup's physiotherapy team assesses and treats musculoskeletal injuries, "
            "post-surgical rehabilitation, chronic pain, sports injuries, and neurological "
            "conditions including stroke rehabilitation. Services include manual therapy, dry "
            "needling, hydrotherapy, clinical Pilates, TENS therapy, and custom orthotics. "
            "No GP referral required, though a referral may entitle eligible patients to "
            "Medicare-rebated sessions under a Chronic Disease Management plan. "
            "Physiotherapists are registered with the APA. WorkCover and NDIS claims accepted. "
            "Home visit physiotherapy available for patients with mobility limitations."
        ),
    },
    # ── Blog posts ──
    {
        "title": "Understanding High Blood Pressure: What Every Patient Should Know",
        "content_type": "blog",
        "body": (
            "Hypertension affects approximately 1 in 3 Australian adults and is a leading risk "
            "factor for heart disease, stroke, and kidney failure. Blood pressure is expressed "
            "as systolic over diastolic in mmHg. A reading of 120/80 is normal; 140/90 or above "
            "on multiple readings constitutes hypertension — the 'silent killer' as it usually "
            "causes no symptoms. "
            "Risk factors: obesity, high salt intake, physical inactivity, smoking, heavy "
            "alcohol use, stress, and family history. "
            "First-line management: reduce sodium to under 2 g/day, 30 minutes of moderate "
            "aerobic exercise five days per week, limit alcohol, quit smoking, healthy BMI. "
            "When lifestyle changes are insufficient, antihypertensive medications such as "
            "ACE inhibitors, calcium channel blockers, or diuretics may be prescribed by your GP. "
            "Book a blood pressure check at ClinGroup — it takes under 5 minutes."
        ),
    },
    {
        "title": "Managing Type 2 Diabetes: Lifestyle, Medication, and Monitoring",
        "content_type": "blog",
        "body": (
            "Type 2 diabetes is characterised by insulin resistance and elevated blood glucose. "
            "Over 1.3 million Australians are diagnosed; many more are undiagnosed. "
            "Symptoms: increased thirst, frequent urination, fatigue, blurred vision, "
            "slow-healing wounds, recurrent infections. "
            "Diagnosis: fasting glucose ≥ 7.0 mmol/L or HbA1c ≥ 48 mmol/mol on two occasions. "
            "Management: low-GI diet, regular exercise, weight loss, blood glucose monitoring. "
            "First-line medication is metformin. SGLT2 inhibitors, GLP-1 agonists, and DPP-4 "
            "inhibitors may be added based on cardiovascular and renal risk. "
            "Annual review: HbA1c, kidney function, lipid panel, blood pressure, foot exam, "
            "retinal screening. ClinGroup's Diabetes Care Clinic offers multidisciplinary "
            "support: dietitian, podiatrist, and diabetes educator."
        ),
    },
    {
        "title": "Adult Vaccination Schedule: Are You Up to Date?",
        "content_type": "blog",
        "body": (
            "Many Australian adults are behind on recommended immunisations. Key vaccines to "
            "discuss with your ClinGroup GP: "
            "Influenza — annually for everyone 6 months+, especially pregnant women, over-65s, "
            "and those with chronic illness. "
            "COVID-19 — booster every 12 months for high-risk groups. "
            "Pneumococcal — for adults 65+ and younger high-risk individuals. "
            "Shingles (Shingrix) — for adults 50+; two-dose schedule, 90%+ protection. "
            "Tdap — tetanus/diphtheria/pertussis booster every 10 years. "
            "HPV — recommended up to age 45 for those not previously vaccinated. "
            "Travel vaccines (hepatitis A/B, typhoid, rabies) depend on destination — book a "
            "Travel Medicine consult at least 6 weeks before departure."
        ),
    },
    {
        "title": "Children's Health Checks: What to Expect at Each Developmental Stage",
        "content_type": "blog",
        "body": (
            "Regular health checks at key milestones help detect issues early. ClinGroup "
            "follows RACGP guidelines. "
            "Newborn (1–5 days): hearing screen, bloodspot screening (heel prick for 30+ "
            "conditions including PKU and hypothyroidism), hip ultrasound if risk factors. "
            "6–8 weeks: growth assessment, developmental screen, maternal check, immunisations. "
            "4, 6, 12 months: NIP immunisations and milestone assessment. "
            "18 months: developmental surveillance, language screen, iron check. "
            "3.5 years: pre-school check — vision, hearing, speech, behaviour. "
            "School age: annual check covering growth, BMI, blood pressure, mental health, "
            "substance use, and immunisation catch-up. "
            "Book at patients.clingroup.com."
        ),
    },
]


# ── Academy Portal content ─────────────────────────────────────────────────────
_ACADEMY_PERSONA = (
    "You are Alex, a knowledgeable and enthusiastic virtual assistant for Academy Portal "
    "Online University. You help prospective and current students navigate programs, "
    "enrollment, fees, scholarships, and campus life. You are encouraging, precise, and "
    "always point students to the right department when a question needs human follow-up. "
    "You do not provide medical advice or help with topics unrelated to education."
)

_ACADEMY_GUARDRAILS = {
    "blocked_topics": [
        "medical diagnosis", "medication", "clinical procedures", "financial investment"
    ],
    "refusal_tone": (
        "I can only assist with Academy Portal academic and student services topics. "
        "Please contact the relevant department for other enquiries."
    ),
    "enabled_tools": ["rag_search", "capture_lead", "escalate"],
}

_ACADEMY_CONTENT = [
    # ── FAQs ──
    {
        "title": "What programs does Academy Portal offer?",
        "content_type": "faq",
        "body": (
            "Academy Portal Online University offers over 80 fully accredited undergraduate and "
            "postgraduate programs across six faculties: Business & Management, Computer Science "
            "& Data, Health Sciences (non-clinical), Law & Social Justice, Education & Teaching, "
            "and Creative Arts & Design. Programs are delivered 100% online with optional "
            "on-campus intensives twice per year. Degrees include Bachelor's (3 years full-time), "
            "Honours (1 year), Graduate Certificate (6 months), Graduate Diploma (1 year), and "
            "Master's (1.5–2 years). All programs are AQF-registered and recognised nationally."
        ),
    },
    {
        "title": "How do I enrol in a course at Academy Portal?",
        "content_type": "faq",
        "body": (
            "Complete the online application at apply.academyportal.edu.au. You will need: "
            "certified copies of previous qualifications, a 500-word personal statement, two "
            "academic or professional referees, English proficiency evidence if applicable "
            "(IELTS 6.5+), and your Unique Student Identifier (USI). "
            "Domestic students apply directly; international students apply via authorised agents. "
            "Applications open 1 October for Semester 1 (February start) and 1 April for "
            "Semester 2 (July start). Offers are sent within 10 business days. Confirm enrolment "
            "by paying the deposit within 14 days. Some programs cap at 120 students — apply early."
        ),
    },
    {
        "title": "What are Academy Portal's fees and payment options?",
        "content_type": "faq",
        "body": (
            "Domestic undergraduate: $3,200–$4,800 per subject. "
            "Domestic postgraduate: $3,800–$5,500 per subject. "
            "International: $4,500–$7,000 per subject. "
            "Domestic students may defer fees using HECS-HELP or FEE-HELP, repaid through the "
            "ATO once income exceeds $51,550. Payment plans available for ineligible students. "
            "Payment methods: BPAY, Visa, Mastercard, bank transfer. "
            "Late payment incurs a $150 fee; students with outstanding balances may be "
            "de-enrolled if not resolved within 30 days."
        ),
    },
    {
        "title": "What are Academy Portal's contact and support hours?",
        "content_type": "faq",
        "body": (
            "Student Services (online chat): Monday–Friday 8 AM–9 PM, Saturday 9 AM–5 PM AEST. "
            "Phone: Monday–Friday 9 AM–6 PM AEST on 1800-ACADEMY. "
            "Email: studentservices@academyportal.edu.au — responses within 2 business days. "
            "The LMS (Learning Management System) is available 24/7. "
            "Digital Library: 24/7 access to 500,000+ e-books and 50+ databases. "
            "Campus intensives are 4-day residential blocks in February and July "
            "in Melbourne and Sydney."
        ),
    },
    {
        "title": "How are grades calculated and what is the assessment policy?",
        "content_type": "faq",
        "body": (
            "Assessment mix per subject: online quizzes (10–20%), written assignments (40–60%), "
            "group projects (10–20%), final exam or capstone (20–40%). "
            "Grade bands: HD 85–100%, D 75–84%, C 65–74%, P 50–64%, F below 50%. "
            "Students must pass ALL components — a high quiz average cannot compensate for a "
            "failed assignment. Word limits carry a 10% tolerance; over the limit = penalty. "
            "Late submissions lose 5% per day up to 5 days, then receive zero. "
            "Academic integrity is monitored via Turnitin. Submitting AI-generated content as "
            "your own constitutes academic misconduct and may result in failure or suspension."
        ),
    },
    {
        "title": "What scholarships and financial support are available?",
        "content_type": "faq",
        "body": (
            "Academy Portal offers 120+ scholarships annually. Key awards: "
            "Vice-Chancellor's Excellence Scholarship — full tuition for one year, one per "
            "faculty (6 total per year). "
            "First-in-Family Scholarship — 20% fee reduction for first-generation university students. "
            "Regional and Remote Scholarship — $5,000 one-off for students from remote postcodes. "
            "Women in Technology Grant — $3,000 for women enrolling in Computer Science or Data. "
            "International Merit Scholarship — 15–25% fee reduction based on prior results. "
            "Applications open 1 November at scholarships.academyportal.edu.au."
        ),
    },
    {
        "title": "Can I transfer credits from previous study?",
        "content_type": "faq",
        "body": (
            "Yes. Credit Recognition and Prior Learning (RPL) assessments are available. "
            "Eligibility: equivalent study at a recognised institution, a relevant vocational "
            "qualification (Cert IV or Diploma), or demonstrated professional experience. "
            "Submit a Credit Assessment Application with certified transcripts and subject "
            "outlines within 30 days of enrolment. Up to 50% of a program may be granted as "
            "credit (max 12 of 24 subjects for a Bachelor's degree). "
            "The fee is $100 per subject block, refunded if credit is granted."
        ),
    },
    {
        "title": "What student support services does Academy Portal offer?",
        "content_type": "faq",
        "body": (
            "Academic Success Coaches — free 1:1 sessions for study skills, time management, "
            "and academic writing. "
            "Counselling and Wellbeing — free, confidential sessions with accredited counsellors. "
            "Disability Access — reasonable adjustments (extensions, alternative formats, "
            "assistive technology) for students with a documented disability or mental health "
            "diagnosis. "
            "Career Services — resume reviews, mock interviews, internship placement, employer "
            "networking. "
            "Peer Mentoring — senior students paired with first-years for guidance. "
            "Indigenous Student Support — a dedicated Liaison Officer for First Nations students."
        ),
    },
    # ── Pages ──
    {
        "title": "About Academy Portal Online University",
        "content_type": "page",
        "body": (
            "Academy Portal Online University was established in 2011 to democratise access to "
            "higher education for Australians regardless of location, work commitments, or "
            "personal circumstances. Today we enrol over 22,000 students from every Australian "
            "state and territory and 40 countries. Our 350-strong academic team includes "
            "industry practitioners, researchers, and award-winning educators. "
            "We are registered with TEQSA and have achieved a 5-star online QILT rating for "
            "four consecutive years. Our mission: confident, capable, ethically grounded "
            "graduates who make a positive difference in their communities and industries."
        ),
    },
    {
        "title": "Computer Science and Data Science Faculty",
        "content_type": "page",
        "body": (
            "Programs: Bachelor of Computer Science, Bachelor of Data Science, Bachelor of "
            "Cybersecurity, Graduate Certificate in AI, Graduate Diploma in Data Engineering, "
            "Master of AI, Master of Cybersecurity. "
            "Core curriculum: algorithms, operating systems, software engineering, machine "
            "learning, statistical modelling, database design, cloud infrastructure, ethical AI. "
            "Students complete a 12-week industry capstone in the final year with partners "
            "including major banks, healthcare providers, and government agencies. "
            "All programs are ACS-accredited at the Professional level."
        ),
    },
    {
        "title": "Student Rights and Academic Integrity Policy",
        "content_type": "page",
        "body": (
            "Student Rights: fair assessment, right of appeal, harassment-free learning, access "
            "to personal data under the Privacy Act 1988, and reasonable adjustments for disability. "
            "Academic Misconduct includes plagiarism, collusion, contract cheating, data "
            "fabrication, and improper use of AI tools. "
            "Penalties range from a zero grade to expulsion depending on severity and history. "
            "Appeals: submit a written Academic Appeal Form to the relevant Dean within "
            "20 business days of notification."
        ),
    },
    {
        "title": "Library and Digital Learning Resources",
        "content_type": "page",
        "body": (
            "The Academy Portal Digital Library provides 24/7 access to 500,000+ e-books, "
            "50+ databases, and 10 million journal articles. "
            "Key databases: ProQuest, JSTOR, Westlaw AU, Mintel, IBISWorld, LinkedIn Learning. "
            "Citation tools: RefWorks and Mendeley licences provided free to all enrolled students. "
            "Learning Centre: self-paced modules on academic writing, referencing (APA 7th, "
            "Chicago, AGLC), and exam preparation. "
            "Physical library access is available during campus intensives in Melbourne and Sydney."
        ),
    },
    {
        "title": "Business and Management Faculty",
        "content_type": "page",
        "body": (
            "Programs: BBA, Bachelor of Accounting, Bachelor of Marketing, Graduate Certificate "
            "in Project Management, Graduate Diploma in HRM, MBA, Master of Financial Planning. "
            "The MBA is ranked among Australia's top 10 online MBAs and is AACSB-recognised. "
            "Core subjects: managerial economics, financial accounting, organisational behaviour, "
            "business analytics, strategic management, business law, and ethics. "
            "Electives: entrepreneurship, sustainability, supply chain, digital marketing, "
            "corporate governance. "
            "CPA Australia and CAANZ affiliate: accounting graduates can count their degree "
            "towards professional membership."
        ),
    },
    # ── Blog posts ──
    {
        "title": "5 Study Strategies Backed by Cognitive Science",
        "content_type": "blog",
        "body": (
            "Online study gives you flexibility — but without campus rhythm many students "
            "struggle. Five evidence-based strategies: "
            "1. Spaced repetition: review at increasing intervals (day 1, 3, 7, 14). "
            "Apps like Anki automate this and dramatically outperform cramming. "
            "2. Retrieval practice: test yourself without notes before reviewing source material. "
            "3. Interleaving: mix topics within a session to improve concept discrimination. "
            "4. Elaborative interrogation: ask 'why' and 'how' about every concept. "
            "5. Sleep: 7–9 hours before an exam improves retention by up to 40% vs an all-nighter. "
            "Contact your Academy Portal Academic Success Coach to build a personalised plan."
        ),
    },
    {
        "title": "New Scholarship Opportunities for 2025–26: Apply Before November 1",
        "content_type": "blog",
        "body": (
            "Three new scholarships open for 2025–26: "
            "Tech Accessibility Grant ($4,000) — for students with financial need who lack "
            "reliable computer or internet access. Recipients receive a laptop and 12 months "
            "of subsidised broadband on enrolment. "
            "Climate and Sustainability Scholarship ($6,000/year, renewable) — for students "
            "with a sustainability or climate policy focus. Two awards per year. "
            "Mature-Age Returner Bursary ($2,500 one-off) — for students aged 35+ who have "
            "been out of formal education for at least five years. "
            "All applications open 1 November 2025, close 31 January 2026. "
            "Apply at scholarships.academyportal.edu.au."
        ),
    },
    {
        "title": "How Our Data Science Graduates Are Shaping AI in Australia",
        "content_type": "blog",
        "body": (
            "When Priya Sharma enrolled in the Academy Portal Master of AI in 2022, she was "
            "already a mid-career software engineer. Two years later she leads the data science "
            "team at a major Sydney insurer. "
            "'Academy Portal gave me the theoretical foundation I was missing. The capstone "
            "project got me a referral that led directly to my current role.' "
            "2024 outcomes: 91% of Master of AI graduates employed in a directly related role "
            "within 6 months; median salary uplift of $28,000. Employers cite communication of "
            "complex findings to non-technical stakeholders as the top differentiating strength. "
            "Applications for Semester 1 2026 open 1 October 2025."
        ),
    },
    {
        "title": "What the New Australian AI Ethics Framework Means for Students",
        "content_type": "blog",
        "body": (
            "Australia's Responsible AI Framework (2025) mandates conformance assessments for "
            "AI in high-risk domains: healthcare, finance, justice, and education. "
            "Key obligations: transparency (explainable decisions), fairness (bias audits before "
            "deployment), human oversight (review possible for any consequential AI decision), "
            "and privacy (Privacy Act and APP 8 compliance). "
            "Academy Portal's curriculum already incorporates all eight National AI Ethics "
            "Principles. From 2026, 'AI Governance and Ethics' becomes a core subject in "
            "Computer Science and Data Science degrees. "
            "Watch the free on-demand webinar 'Navigating the AI Ethics Landscape' on the LMS "
            "under Professional Development resources."
        ),
    },
]


# ── Seeder logic ───────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def login(client: httpx.Client, email: str, password: str) -> str:
    r = client.post("/auth/login", data={"username": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def get_or_create_tenant(client: httpx.Client, manager_token: str,
                         name: str, slug: str) -> str:
    """Return the tenant UUID, creating the tenant if it doesn't exist yet."""
    r = client.get("/tenants/", headers=_auth(manager_token))
    r.raise_for_status()
    for t in r.json():
        if t["slug"] == slug:
            print(f"  → Tenant '{slug}' already exists, skipping creation.")
            return t["id"]
    r = client.post("/tenants/", json={"name": name, "slug": slug},
                    headers=_auth(manager_token))
    r.raise_for_status()
    tenant_id = r.json()["id"]
    print(f"  → Created tenant '{name}' (slug={slug}).")
    return tenant_id


def get_or_create_admin(client: httpx.Client, manager_token: str,
                        email: str, password: str, tenant_id: str) -> None:
    """Register a tenant_admin user, skipping if the email is already taken."""
    r = client.post(
        "/auth/register",
        json={"email": email, "password": password,
              "role": "tenant_admin", "tenant_id": tenant_id},
        headers=_auth(manager_token),
    )
    if r.status_code == 400 and "REGISTER_USER_ALREADY_EXISTS" in r.text:
        print(f"  → Admin '{email}' already exists, skipping registration.")
        return
    r.raise_for_status()
    print(f"  → Registered admin '{email}'.")


def inject_widget_id(demo_subdir: str, tenant_id: str) -> None:
    import re
    html_file = _DEMO_DIR / demo_subdir / "index.html"
    html = html_file.read_text(encoding="utf-8")
    # Replace placeholder or any previously injected UUID in the widgetId= param
    updated = re.sub(r"widgetId=[^\"&]+", f"widgetId={tenant_id}", html)
    if updated != html:
        html_file.write_text(updated, encoding="utf-8")
        print(f"  → Wrote tenant ID into demo-sites/{demo_subdir}/index.html")
    else:
        print(f"  → demo-sites/{demo_subdir}/index.html already up to date.")


def get_existing_titles(client: httpx.Client, token: str) -> set[str]:
    r = client.get("/content", headers=_auth(token))
    r.raise_for_status()
    return {item["title"] for item in r.json()}


def create_or_update_widget_config(
    client: httpx.Client, token: str, greeting: str, theme_color: str
) -> str:
    r = client.post(
        "/widget/config",
        json={"greeting": greeting, "theme_color": theme_color},
        headers=_auth(token),
    )
    r.raise_for_status()
    widget_id = r.json()["widget_id"]
    print(f"  → Widget config saved (widget_id={widget_id[:8]}…, theme={theme_color})")
    return widget_id


def patch_config(client: httpx.Client, token: str, persona: str, guardrails: dict) -> None:
    r = client.patch(
        "/tenants/me/config",
        json={"llm_persona": persona, "guardrail_config": guardrails},
        headers=_auth(token),
    )
    r.raise_for_status()


def post_content(client: httpx.Client, token: str, item: dict) -> None:
    r = client.post("/content", json=item, headers=_auth(token))
    r.raise_for_status()


def reindex_content(client: httpx.Client, token: str) -> None:
    r = client.post("/content/reindex", headers=_auth(token))
    r.raise_for_status()


def seed_tenant(client: httpx.Client, manager_token: str, cfg: dict,
                persona: str, guardrails: dict, content: list) -> None:
    name        = cfg["name"]
    slug        = cfg["slug"]
    admin_email = cfg["admin_email"]
    admin_pw    = cfg["admin_password"]
    demo_subdir = cfg["demo_subdir"]
    greeting    = cfg["widget_greeting"]
    theme_color = cfg["widget_theme"]

    print(f"\n── {name}")

    tenant_id = get_or_create_tenant(client, manager_token, name, slug)
    get_or_create_admin(client, manager_token, admin_email, admin_pw, tenant_id)

    admin_token = login(client, admin_email, admin_pw)

    print("  → Updating persona and guardrails...")
    patch_config(client, admin_token, persona, guardrails)

    widget_id = create_or_update_widget_config(client, admin_token, greeting, theme_color)
    inject_widget_id(demo_subdir, widget_id)

    existing = get_existing_titles(client, admin_token)
    to_create = [item for item in content if item["title"] not in existing]
    skipped = len(content) - len(to_create)

    if skipped:
        print(f"  → Skipping {skipped} already-existing item(s).")

    if to_create:
        print(f"  → Creating {len(to_create)} new content item(s)...")
        for item in to_create:
            post_content(client, admin_token, item)
            print(f"     ✓ [{item['content_type']:4s}] {item['title'][:68]}")

    print("  → Indexing all content (embedding into pgvector)...")
    reindex_content(client, admin_token)
    print("  Done.")


_CONTENT_MAP = {
    "clingroup": (_CLINGROUP_PERSONA, _CLINGROUP_GUARDRAILS, _CLINGROUP_CONTENT),
    "academy":   (_ACADEMY_PERSONA,   _ACADEMY_GUARDRAILS,   _ACADEMY_CONTENT),
}


def main() -> None:
    with httpx.Client(base_url=BACKEND_URL, timeout=30.0) as client:
        print(f"Logging in as manager ({MANAGER_EMAIL})...")
        try:
            manager_token = login(client, MANAGER_EMAIL, MANAGER_PASSWORD)
        except httpx.HTTPStatusError as exc:
            print(f"\n  ERROR: Manager login failed ({exc.response.status_code}). "
                  f"Check MANAGER_EMAIL / MANAGER_PASSWORD at the top of this script.")
            sys.exit(1)
        except httpx.ConnectError:
            print(f"\n  ERROR: Cannot connect to {BACKEND_URL}. Is the backend running?")
            sys.exit(1)

        for cfg in TENANTS_TO_SEED:
            persona, guardrails, content = _CONTENT_MAP[cfg["demo_subdir"]]
            try:
                seed_tenant(client, manager_token, cfg, persona, guardrails, content)
            except httpx.HTTPStatusError as exc:
                print(f"\n  ERROR {exc.response.status_code}: {exc.response.text[:300]}")
                sys.exit(1)

    print("\nAll tenants seeded successfully.")


if __name__ == "__main__":
    main()
