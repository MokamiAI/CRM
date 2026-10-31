// The signature made for someone who hasn't written their own: the same
// lines the server uses (backend/app/services/signatures.py).
export function suggestedSignature(person, company) {
  const position = (person?.job_title || "").trim();
  const name = company?.company_name || "";
  return [person?.full_name, position ? `${position} · ${name}` : name, person?.email, company?.phone, company?.website]
    .map((line) => (line || "").trim())
    .filter(Boolean)
    .join("\n");
}
