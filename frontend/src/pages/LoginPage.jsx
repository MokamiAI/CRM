import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import LanguagePicker from "../components/LanguagePicker";
import GlowField from "../components/GlowField";
import LoginShowcase from "../components/LoginShowcase";
import { APP_FULL_NAME, APP_NAME, BrandMark } from "../components/Brand";
import { usePlans } from "../hooks/useApi";
import { queueWelcome } from "../components/Startup";
import { formatMoneyWhole } from "../utils/format";

/** The sign-in screens' frame: brand, language, ambient colour and the
 *  product showcase; each screen supplies its own card contents. */
export function AuthShell({ children }) {
  const { t } = useTranslation();
  return (
    <div className="grid min-h-[100dvh] bg-white md:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
      <div className="safe-top safe-bottom relative flex flex-col overflow-hidden px-6">
        {/* Ambient colour, kept faint so the form stays the focus. */}
        <div className="pointer-events-none absolute inset-0" aria-hidden="true">
          <span className="aurora-blob -left-24 top-[12%] h-72 w-72 bg-violet-300" />
          <span className="aurora-blob -right-20 top-[40%] h-80 w-80 bg-sky-300" />
          <span className="aurora-blob bottom-[-6rem] left-[20%] h-72 w-72 bg-emerald-200" />
        </div>

        <header className="relative flex items-center gap-2.5 py-6">
          <Link to="/" className="flex items-center gap-2.5 rounded-lg">
            <BrandMark join />
            <span className="text-[15px] font-semibold tracking-tight text-zinc-900">
              {APP_NAME} <span className="font-normal text-zinc-400">· {APP_FULL_NAME}</span>
            </span>
          </Link>
          <div className="ml-auto">
            <LanguagePicker />
          </div>
        </header>

        <div className="relative flex flex-1 items-center justify-center py-8">
          {/* Rises in once when the page opens: the only entrance on the screen. */}
          <div className="login-card w-full max-w-sm rounded-2xl border border-white/70 bg-white/75 p-6 shadow-pop backdrop-blur-xl sm:p-8">
            {children}
          </div>
        </div>
        <footer className="relative flex items-center justify-between py-6 text-xs text-zinc-400">
          <span>
            © {new Date().getFullYear()} {APP_NAME} ·{" "}
            <Link to="/about" className="inline-block py-2 -my-2 hover:text-zinc-600">
              {t("about.link")}
            </Link>
            {" · "}
            <Link to="/contact" className="inline-block py-2 -my-2 hover:text-zinc-600">
              {t("contact.link")}
            </Link>
            {" · "}
            <Link to="/terms" className="inline-block py-2 -my-2 hover:text-zinc-600">
              {t("legal.terms")}
            </Link>
            {" · "}
            <Link to="/privacy" className="inline-block py-2 -my-2 hover:text-zinc-600">
              {t("legal.privacy")}
            </Link>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <svg viewBox="0 0 16 16" fill="currentColor" className="h-3.5 w-3.5" aria-hidden="true">
              <path fillRule="evenodd" d="M8 1a3.5 3.5 0 0 0-3.5 3.5V6H4a1.5 1.5 0 0 0-1.5 1.5v5A1.5 1.5 0 0 0 4 14h8a1.5 1.5 0 0 0 1.5-1.5v-5A1.5 1.5 0 0 0 12 6h-.5V4.5A3.5 3.5 0 0 0 8 1Zm2 5V4.5a2 2 0 1 0-4 0V6h4Z" clipRule="evenodd" />
            </svg>
            {t("login.encrypted")}
          </span>
        </footer>
      </div>

      {/* Brand panel, tablet and up: the product demoing itself. */}
      <div className="relative hidden md:block">
        <LoginShowcase />
      </div>
    </div>
  );
}

/** "I agree to the Terms and conditions and the Privacy policy", with both
 *  opening in a new tab so the form isn't lost. `text` is a translation
 *  with {{terms}} and {{privacy}} where the links go. */
export function TermsLinks({ text }) {
  const { t } = useTranslation();
  const links = {
    terms: ["/terms", t("legal.termsFull")],
    privacy: ["/privacy", t("legal.privacyFull")],
  };
  return text.split(/(\{\{terms\}\}|\{\{privacy\}\})/).map((part, i) => {
    const key = part.slice(2, -2);
    if (!links[key] || !part.startsWith("{{")) return part;
    const [to, label] = links[key];
    return (
      <a key={i} href={to} target="_blank" rel="noopener noreferrer" className="font-medium text-indigo-700 underline underline-offset-2 hover:text-indigo-900">
        {label}
      </a>
    );
  });
}

export function FormError({ children }) {
  if (!children) return null;
  return (
    <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-inset ring-red-200/70" role="alert">
      {children}
    </p>
  );
}

export function SwitchLink({ prompt, to, label }) {
  return (
    <p className="mt-6 text-center text-sm text-zinc-500">
      {prompt}{" "}
      <Link to={to} className="inline-block py-2 -my-2 font-medium text-indigo-600 hover:text-indigo-700">
        {label}
      </Link>
    </p>
  );
}

export default function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await login(email, password);
      queueWelcome(); // the app greets them once, from the team
      navigate(location.state?.from ?? "/", { replace: true });
    } catch (err) {
      setError(t(err?.response?.data?.error_code === "RATE_LIMITED" ? "errors.RATE_LIMITED" : "login.failed"));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold text-zinc-900">{t("login.title")}</h1>
      <p className="mt-1.5 text-sm text-zinc-500">{t("login.subtitle")}</p>
      {location.state?.notice && (
        <p className="mt-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800" role="status">
          {location.state.notice}
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-7 space-y-5">
        <div>
          <label className="label" htmlFor="email">
            {t("login.email")}
          </label>
          <GlowField
            id="email"
            type="email"
            inputMode="email"
            autoComplete="username"
            autoFocus
            autoCapitalize="none"
            autoCorrect="off"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <div className="flex items-baseline justify-between gap-3">
            <label className="label" htmlFor="password">
              {t("login.password")}
            </label>
            <Link to="/forgot-password" className="inline-block py-2 -my-2 text-xs font-medium text-indigo-600 hover:text-indigo-700">
              {t("password.forgot")}
            </Link>
          </div>
          <GlowField
            id="password"
            type="password"
            autoComplete="current-password"
            enterKeyHint="go"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <FormError>{error}</FormError>
        <button type="submit" disabled={isSubmitting} className="btn btn-primary w-full">
          {isSubmitting ? t("login.signingIn") : t("login.signIn")}
        </button>
      </form>
      <SwitchLink prompt={t("login.noAccount")} to="/register" label={t("login.createAccount")} />
    </AuthShell>
  );
}

/** Self-service sign-up: creates a new company with this person as its admin. */
export function RegisterPage() {
  const { t } = useTranslation();
  const { register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ company_name: "", business_address: "", full_name: "", email: "", password: "" });
  // Optional: the year's revenue goal, for the dashboard's goal card.
  const [goal, setGoal] = useState("");
  // YGT's tips, news and offers: never ticked for them (POPIA s69).
  const [marketing, setMarketing] = useState(false);
  // Required, and recorded on the account (with the terms' version).
  const [agreed, setAgreed] = useState(false);
  // ?plan=scale from a "Start free trial" button; Grow otherwise.
  const [plan, setPlan] = useState(() => (["hustle", "grow", "scale"].includes(location.search.match(/plan=(\w+)/)?.[1]) ? location.search.match(/plan=(\w+)/)[1] : "grow"));
  // Step 1: who you are; step 2: which plan to try.
  const [step, setStep] = useState(1);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const set = (field) => (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }));

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    if (step === 1) {
      setStep(2); // the browser has already checked the fields
      return;
    }
    setIsSubmitting(true);
    try {
      const target = Number(String(goal).replace(/[^\d.]/g, ""));
      await register({ ...form, plan, marketing_opt_in: marketing, accept_terms: agreed, ...(target > 0 && { annual_revenue_goal: String(target) }) });
      navigate("/", { replace: true });
    } catch (err) {
      const code = err?.response?.data?.error_code;
      const onFirstStep = ["USER_EMAIL_TAKEN", "EMAIL_DISPOSABLE", "EMAIL_UNDELIVERABLE", "VALIDATION_ERROR"];
      if (onFirstStep.includes(code)) setStep(1); // the fix is on the first step
      setError(
        t(
          code === "USER_EMAIL_TAKEN"
            ? "register.emailTaken"
            : ["RATE_LIMITED", "EMAIL_DISPOSABLE", "EMAIL_UNDELIVERABLE"].includes(code)
              ? `errors.${code}`
              : code === "VALIDATION_ERROR"
                ? "register.checkDetails"
                : "register.failed"
        )
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const fields = [
    { id: "company_name", autoComplete: "organization", autoFocus: true },
    { id: "full_name", autoComplete: "name" },
    { id: "email", type: "email", inputMode: "email", autoComplete: "email", autoCapitalize: "none", autoCorrect: "off", hint: t("register.verifyNote") },
    { id: "password", type: "password", autoComplete: "new-password", minLength: 8, hint: t("register.passwordHint") },
  ];

  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold text-zinc-900">{t("register.title")}</h1>
      <p className="mt-1.5 text-sm text-zinc-500">{t("register.subtitle")}</p>

      <div className="mt-6 flex items-center gap-3" aria-live="polite">
        <span className="text-xs font-semibold uppercase tracking-[0.12em] text-indigo-600">{t("register.step", { n: step, total: 2 })}</span>
        <span className="text-sm font-medium text-zinc-700">{t(step === 1 ? "register.stepDetails" : "register.planTitle")}</span>
        <span className="ml-auto flex gap-1.5" aria-hidden="true">
          {[1, 2].map((n) => (
            <span key={n} className={`h-1.5 w-6 rounded-full ${n <= step ? "bg-indigo-600" : "bg-zinc-200"}`} />
          ))}
        </span>
      </div>

      <form onSubmit={handleSubmit} className="mt-5 space-y-4">
        {step === 1 ? (
          <>
            {fields.map(({ id, hint, ...props }) => (
              <div key={id}>
                <label className="label" htmlFor={id}>
                  {t(`register.${id}`)}
                </label>
                <GlowField id={id} required value={form[id]} onChange={set(id)} {...props} />
                {hint && <span className="mt-1.5 block text-xs text-zinc-500">{hint}</span>}
                {id === "company_name" && (
                  <div className="mt-4">
                    <label className="label" htmlFor="business_address">
                      {t("register.business_address")}
                    </label>
                    <textarea
                      id="business_address"
                      className="input min-h-[4.5rem] resize-y"
                      rows={2}
                      required
                      minLength={10}
                      maxLength={500}
                      autoComplete="street-address"
                      placeholder={t("register.addressPlaceholder")}
                      value={form.business_address}
                      onChange={set("business_address")}
                    />
                    <span className="mt-1.5 block text-xs text-zinc-500">{t("register.addressHint")}</span>
                  </div>
                )}
              </div>
            ))}
            <div>
              <label className="label" htmlFor="annual_revenue_goal">
                {t("goal.signupLabel")} <span className="font-normal text-zinc-400">{t("goal.optional")}</span>
              </label>
              <GlowField id="annual_revenue_goal" inputMode="decimal" placeholder={t("goal.placeholder")} value={goal} onChange={(e) => setGoal(e.target.value)} />
              <span className="mt-1.5 block text-xs text-zinc-500">{t("goal.signupHint")}</span>
            </div>
          </>
        ) : (
          <>
            <PlanPicker value={plan} onChange={setPlan} />
            <label className="flex cursor-pointer items-start gap-3 rounded-xl px-1 py-1 text-sm text-zinc-700">
              <input type="checkbox" required className="mt-0.5 h-5 w-5 shrink-0 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
              <span>
                <TermsLinks text={t("register.agree", { terms: "{{terms}}", privacy: "{{privacy}}", interpolation: { escapeValue: false } })} />
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-3 rounded-xl px-1 py-1 text-sm text-zinc-700">
              <input type="checkbox" className="mt-0.5 h-5 w-5 shrink-0 rounded border-zinc-300 text-indigo-600 focus:ring-indigo-500" checked={marketing} onChange={(e) => setMarketing(e.target.checked)} />
              <span>
                {t("register.marketing")}
                <span className="mt-0.5 block text-xs text-zinc-500">{t("register.marketingHint")}</span>
              </span>
            </label>
            <DataProtected />
          </>
        )}
        <FormError>{error}</FormError>
        {step === 1 ? (
          <button type="submit" className="btn btn-primary w-full">
            {t("register.continue")}
          </button>
        ) : (
          <div className="flex gap-2">
            <button type="button" className="btn btn-secondary" onClick={() => { setError(""); setStep(1); }}>
              {t("register.back")}
            </button>
            <button type="submit" disabled={isSubmitting} className="btn btn-primary flex-1">
              {isSubmitting ? t("register.submitting") : t("register.submit")}
            </button>
          </div>
        )}
      </form>
      <SwitchLink prompt={t("register.haveAccount")} to="/login" label={t("login.signIn")} />
    </AuthShell>
  );
}

/** How sign-up data is looked after: only what is true of YGT today. */
function DataProtected() {
  const { t } = useTranslation();
  return (
    <section className="rounded-xl bg-emerald-50/60 px-4 py-3 ring-1 ring-inset ring-emerald-200/70" aria-labelledby="data-protected">
      <h2 id="data-protected" className="flex items-center gap-2 text-sm font-semibold text-emerald-950">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 text-emerald-700" aria-hidden="true">
          <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.4 7.5 9.5 4.3-1.1 7.5-4.9 7.5-9.5V6L12 3Z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
        {t("register.protectedTitle")}
      </h2>
      <ul className="mt-2 space-y-1 text-xs leading-relaxed text-emerald-900">
        <li>{t("register.protected1")}</li>
        <li>{t("register.protected2")}</li>
        <li>{t("register.protected3")}</li>
      </ul>
      <Link to="/privacy" className="mt-2 inline-block text-xs font-medium text-emerald-800 underline underline-offset-2 hover:text-emerald-950">
        {t("register.privacyLink")}
      </Link>
    </section>
  );
}

/** Sign-up: which plan to try. Every plan starts with the same free trial. */
function PlanPicker({ value, onChange }) {
  const { t } = useTranslation();
  const { data: plans, isError, refetch, isFetching } = usePlans();
  // Never an empty step: placeholders while the plans load, and a way to
  // try again if they can't.
  if (!plans && isError && !isFetching) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-zinc-50 px-3 py-3 ring-1 ring-inset ring-zinc-200">
        <p className="text-sm text-zinc-600">{t("common.loadError")}</p>
        <button type="button" onClick={() => refetch()} className="btn btn-secondary !h-9 !text-sm">
          {t("common.tryAgain")}
        </button>
      </div>
    );
  }
  if (!plans) {
    return (
      <div className="space-y-2" aria-busy="true">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-16 animate-pulse rounded-xl bg-zinc-100 motion-reduce:animate-none" />
        ))}
      </div>
    );
  }
  return (
    <fieldset>
      <legend className="sr-only">{t("register.planTitle")}</legend>
      <div className="space-y-2" role="radiogroup">
        {plans.map((plan) => {
          const chosen = value === plan.key;
          const price = `${formatMoneyWhole(plan.monthly_cents / 100)} ${plan.per_user ? t("billing.perPerson") : ""} / ${t("billing.perMonth")}`;
          return (
            <button
              key={plan.key}
              type="button"
              role="radio"
              aria-checked={chosen}
              onClick={() => onChange(plan.key)}
              className={`flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left ring-1 ring-inset transition-colors duration-150 ${
                chosen ? "bg-indigo-50/70 ring-2 ring-indigo-500" : "bg-white/60 ring-zinc-200 hover:bg-white"
              }`}
            >
              <span className={`mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full ring-1 ring-inset ${chosen ? "bg-indigo-600 ring-indigo-600" : "ring-zinc-300"}`} aria-hidden="true">
                {chosen && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold text-zinc-900">{plan.name}</span>
                  <span className="text-xs tabular-nums text-zinc-500">{price.replace(/\s+/g, " ")}</span>
                </span>
                <span className="block text-xs text-zinc-500">{t(`billing.tagline.${plan.key}`)}</span>
                {plan.team_monthly_cents != null && (
                  <span className="block text-xs font-medium text-emerald-700">
                    {t("billing.teamFrom", { price: formatMoneyWhole(plan.team_monthly_cents / 100), count: plan.team_seats, percent: plan.team_discount_percent })}
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-zinc-500">{t("register.planHint")}</p>
    </fieldset>
  );
}
