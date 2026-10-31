"""The signature under a person's emails: the one they wrote, else the
company's, else one made for them from their name, position and the
company's details."""


def suggested_signature(user, company) -> str:
    position = (user.job_title or "").strip()
    lines = [
        user.full_name,
        f"{position} · {company.company_name}" if position else company.company_name,
        user.email,
        company.phone,
        company.website,
    ]
    return "\n".join(line.strip() for line in lines if line and line.strip())


def signature_for(user, company) -> str | None:
    if user is None:
        return company.email_signature
    return user.email_signature or company.email_signature or suggested_signature(user, company)
