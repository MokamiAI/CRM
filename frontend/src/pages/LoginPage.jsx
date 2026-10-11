import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import LanguagePicker from "../components/LanguagePicker";
import GlowField from "../components/GlowField";
import LoginShowcase from "../components/LoginShowcase";
import { APP_FULL_NAME, APP_NAME, BrandMark } from "../components/Brand";
import { usePlans } from "../hooks/useApi";
import { formatMoneyWhole } from "../utils/format";
import QuoteOfTheWeek from "../components/QuoteOfTheWeek";

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
          <Link to="/login" className="flex items-center gap-2.5 rounded-lg">
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
        {/* Desktop: kept within this (left) half, clear of the showcase. */}
        <QuoteOfTheWeek className="bottom-[max(env(safe-area-inset-bottom,0px),1rem)] md:bottom-6 md:right-auto md:mx-0 md:left-6 md:w-[min(28rem,calc(46.5vw-3rem))]" />

        <footer className="relative flex items-center justify-between py-6 text-xs text-zinc-400">
          <span>
            © {new Date().getFullYear()} {APP_NAME} ·{" "}
            <Link to="/about" className="hover:text-zinc-600">
              {t("about.link")}
            </Link>
            {" · "}
            <Link to="/contact" className="hover:text-zinc-600">
              {t("contact.link")}
            </Link>
            {" · "}
            <Link to="/terms" className="hover:text-zinc-600">
              {t("legal.terms")}
            </Link>
            {" · "}
            <Link to="/privacy" className="hover:text-zinc-600">
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
      <Link to={to} className="font-medium text-indigo-600 hover:text-indigo-700">
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
            <Link to="/forgot-password" className="text-xs font-medium text-indigo-600 hover:text-indigo-700">
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
  const [form, setForm] = useState({ company_name: "", full_name: "", email: "", password: "" });
  // ?plan=scale from a "Start free trial" button; Grow otherwise.
  const [plan, setPlan] = useState(() => (["hustle", "grow", "scale"].includes(location.search.match(/plan=(\w+)/)?.[1]) ? location.search.match(/plan=(\w+)/)[1] : "grow"));
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const set = (field) => (event) => setForm((prev) => ({ ...prev, [field]: event.target.value }));

  async function handleSubmit(event) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      await register({ ...form, plan });
      navigate("/", { replace: true });
    } catch (err) {
      const code = err?.response?.data?.error_code;
      setError(t(code === "USER_EMAIL_TAKEN" ? "register.emailTaken" : code === "RATE_LIMITED" ? "errors.RATE_LIMITED" : "register.failed"));
    } finally {
      setIsSubmitting(false);
    }
  }

  const fields = [
    { id: "company_name", autoComplete: "organization", autoFocus: true },
    { id: "full_name", autoComplete: "name" },
    { id: "email", type: "email", inputMode: "email", autoComplete: "email", autoCapitalize: "none", autoCorrect: "off" },
    { id: "password", type: "password", autoComplete: "new-password", minLength: 8, hint: t("register.passwordHint") },
  ];

  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold text-zinc-900">{t("register.title")}</h1>
      <p className="mt-1.5 text-sm text-zinc-500">{t("register.subtitle")}</p>

      <form onSubmit={handleSubmit} className="mt-7 space-y-4">
        {fields.map(({ id, hint, ...props }) => (
          <div key={id}>
            <label className="label" htmlFor={id}>
              {t(`register.${id}`)}
            </label>
            <GlowField id={id} required value={form[id]} onChange={set(id)} {...props} />
            {hint && <span className="mt-1.5 block text-xs text-zinc-500">{hint}</span>}
          </div>
        ))}
        <PlanPicker value={plan} onChange={setPlan} />
        <FormError>{error}</FormError>
        <button type="submit" disabled={isSubmitting} className="btn btn-primary w-full">
          {isSubmitting ? t("register.submitting") : t("register.submit")}
        </button>
      </form>
      <SwitchLink prompt={t("register.haveAccount")} to="/login" label={t("login.signIn")} />
    </AuthShell>
  );
}

/** Sign-up: which plan to try. Every plan starts with the same free trial. */
function PlanPicker({ value, onChange }) {
  const { t } = useTranslation();
  const { data: plans } = usePlans();
  if (!plans) return null;
  return (
    <fieldset>
      <legend className="label">{t("register.planTitle")}</legend>
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
              </span>
            </button>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-zinc-500">{t("register.planHint")}</p>
    </fieldset>
  );
}
