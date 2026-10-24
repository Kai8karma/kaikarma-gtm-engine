"""Builds the Claude prompts and assembles the final HTML for both emails.

This module owns the SOW's content contract (Section 5.3):
  T-2 — five sections: contact profile, company deep-dive, industry
        customers, relevant agents/use-cases, 6-8 discovery questions.
  T-1 — a one-screen recap: why the call matters, top contact/company
        fact, three talking points, 1-2 references, three opening questions.

It builds the *prompt* sent to Claude (live web search happens at the
Anthropic-API call site, outside this module — see 00-operating-system
doctrine: strategy/content-shape is pure code, the live call is the only
thing that egresses) and assembles the model's structured output into the
HTML actually mailed. Validation lives on the schema (precall_schema.py);
this module fails loud if asked to assemble something invalid.
"""

from __future__ import annotations

from precall_schema import (
    BriefingSections,
    CalendarEvent,
    CompanyProfile,
    ContactProfile,
    RecapSummary,
)


def build_t2_prompt(
    contact: ContactProfile,
    company: CompanyProfile,
    event: CalendarEvent,
) -> str:
    """Build the Claude research+writing instruction for the T-2 briefing.

    Includes an explicit industry-fallback instruction when HubSpot's
    industry field was blank (SOW Section 10 risk), so the model classifies
    the industry from web search rather than the caller guessing.
    """
    industry_note = (
        "HubSpot's industry field is blank for this company — classify the "
        "company's industry yourself from live web search before selecting "
        "customer references and use-cases."
        if company.industry_source == "web_search_fallback" and not company.industry
        else f"CRM industry: {company.industry}"
    )

    return (
        f"Research and write a pre-call briefing for an Aerchain demo call.\n\n"
        f"Call: {event.title} at {event.start_iso}\n"
        f"Contact: {contact.first_name} {contact.last_name}, {contact.title} "
        f"({contact.email}), {contact.linkedin_url}\n"
        f"Company: {company.name} ({company.domain}), {company.employee_count} employees, "
        f"HQ {company.hq}. {industry_note}\n\n"
        f"Use live web search for recent news, product count, and public activity. "
        f"Write exactly five sections:\n"
        f"1. Contact profile\n"
        f"2. Company deep-dive (include an approximate product count)\n"
        f"3. Aerchain customers in the same industry, as a table\n"
        f"4. Relevant Aerchain agents/use-cases mapped to likely pain points\n"
        f"5. Six to eight suggested discovery questions"
    )


def build_t1_prompt(stored_briefing_html: str) -> str:
    """Build the Claude instruction for the T-1 recap, condensing the T-2 briefing.

    If `stored_briefing_html` is empty (SOW Section 5.2 — briefing wasn't
    stored because the prospect wasn't in HubSpot), callers should not call
    Claude at all; there is no source content to condense.
    """
    if not stored_briefing_html.strip():
        raise ValueError(
            "no stored T-2 briefing to condense — prospect likely had no HubSpot "
            "contact record at T-2 time; the T-1 recap has no source content"
        )
    return (
        f"Condense the following pre-call briefing into a one-screen recap: "
        f"who/what/why the call matters, the single most important fact on the "
        f"contact and on the company, the top three talking points, one to two "
        f"strongest customer references, and three opening questions.\n\n"
        f"--- BRIEFING ---\n{stored_briefing_html}"
    )


def assemble_briefing_html(
    sections: BriefingSections,
    contact: ContactProfile,
    company: CompanyProfile,
) -> str:
    """Render the five validated sections into the T-2 briefing HTML."""
    questions_html = "".join(f"<li>{q}</li>" for q in sections.discovery_questions)
    return (
        f"<h1>Pre-Call Briefing: {contact.first_name} {contact.last_name} @ {company.name}</h1>"
        f"<h2>1. Contact Profile</h2><p>{sections.contact_profile}</p>"
        f"<h2>2. Company Deep-Dive</h2><p>{sections.company_deep_dive}</p>"
        f"<h2>3. Aerchain Customers in {company.industry or 'This Industry'}</h2>"
        f"<p>{sections.industry_customers}</p>"
        f"<h2>4. Relevant Agents / Use-Cases</h2><p>{sections.relevant_agents}</p>"
        f"<h2>5. Suggested Discovery Questions</h2><ul>{questions_html}</ul>"
    )


def assemble_recap_html(recap: RecapSummary, contact: ContactProfile, company: CompanyProfile) -> str:
    """Render the validated recap into the T-1 email HTML."""
    talking_points_html = "".join(f"<li>{t}</li>" for t in recap.talking_points)
    references_html = "".join(f"<li>{r}</li>" for r in recap.references)
    questions_html = "".join(f"<li>{q}</li>" for q in recap.opening_questions)
    return (
        f"<h1>Tomorrow's Call: {contact.first_name} {contact.last_name} @ {company.name}</h1>"
        f"<p><b>Why it matters:</b> {recap.why_it_matters}</p>"
        f"<p><b>Top contact fact:</b> {recap.top_contact_fact}</p>"
        f"<p><b>Top company fact:</b> {recap.top_company_fact}</p>"
        f"<h2>Top 3 Talking Points</h2><ul>{talking_points_html}</ul>"
        f"<h2>Strongest References</h2><ul>{references_html}</ul>"
        f"<h2>Opening Questions</h2><ul>{questions_html}</ul>"
    )


if __name__ == "__main__":
    contact = ContactProfile(
        contact_id="501",
        first_name="Jane",
        last_name="Buyer",
        title="VP Procurement",
        email="buyer@acmecloud.com",
        linkedin_url="linkedin.com/in/janebuyer",
        company_id="1001",
    )
    company = CompanyProfile(
        company_id="1001",
        name="Acme Cloud Inc",
        industry="",
        industry_source="web_search_fallback",
        domain="acmecloud.com",
        employee_count=480,
        revenue="50000000",
        hq="Austin",
    )
    from precall_schema import Attendee, DedupFlags

    event = CalendarEvent(
        event_id="evt-1001",
        title="Aerchain demo — Acme Cloud",
        description="Discovery call",
        start_iso="2026-07-03T15:00:00+00:00",
        booked_at_iso="2026-06-20T09:00:00+00:00",
        attendees=(Attendee("rep@aerchain.io", "Rep", True),),
        flags=DedupFlags(),
    )

    print("briefing_builder demo\n")
    print("--- T-2 prompt ---")
    print(build_t2_prompt(contact, company, event))

    sections = BriefingSections(
        contact_profile="Jane Buyer, VP Procurement — 6 years at Acme Cloud.",
        company_deep_dive="Acme Cloud runs ~40 SaaS products across cloud infra.",
        industry_customers="Aerchain serves 3 cloud-infra customers in this space.",
        relevant_agents="Procurement-orchestration agent maps to their RFP bottleneck.",
        discovery_questions=(
            "What triggered evaluating procurement automation now?",
            "How many approval steps does a typical PO take today?",
            "Who owns vendor onboarding?",
            "What's blocking faster cycle times?",
            "Any recent RFP misses?",
            "Who else needs to sign off?",
        ),
    )
    html = assemble_briefing_html(sections, contact, company)
    print(f"\n--- T-2 HTML ({len(html)} chars) ---\n{html[:200]}...")

    print("\n--- T-1 prompt ---")
    print(build_t1_prompt(html))

    recap = RecapSummary(
        why_it_matters="First demo with a mid-market cloud infra buyer this quarter.",
        top_contact_fact="Jane owns procurement automation vendor selection solo.",
        top_company_fact="Acme Cloud runs ~40 products with no unified procurement tool.",
        talking_points=("RFP cycle time", "Approval sprawl", "Vendor onboarding drag"),
        references=("SimilarCo (cloud infra, -35% cycle time)",),
        opening_questions=("What triggered this now?", "Who signs off today?", "What's the timeline?"),
    )
    recap_html = assemble_recap_html(recap, contact, company)
    print(f"\n--- T-1 HTML ({len(recap_html)} chars) ---\n{recap_html[:200]}...")
    print("\nNo network I/O occurred.")
