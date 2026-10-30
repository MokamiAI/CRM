import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import apiClient from "../services/apiClient";
import { announceVerified, useAuth } from "../context/AuthContext";
import { APP_NAME, BrandMark, COMPANY_NAME } from "../components/Brand";
import LanguagePicker from "../components/LanguagePicker";
import GlowField from "../components/GlowField";
import { AuthShell, FormError, SwitchLink } from "./LoginPage";
import { Field } from "../components/ui";
import { errorMessage } from "../utils/format";
import { markArrived, queueWelcome } from "../components/Startup";

// Your business details for the legal pages. Fill these in before going
// live (Paystack checks them when it reviews your account).
export const LEGAL = {
  company: COMPANY_NAME,
  registration: "K2026/825202/07",
  address: "1929 Vuka Section, Oukasie, Brits, 0250, South Africa",
  email: "johannes@yougt.co.za",
  informationOfficer: "Mokami Johannes",
  updated: "29 October 2026",
};
const missing = (value) => value || "[to be added]";

/** The frame for public pages: the header, the page, and the footer links. */
export function PublicShell({ children, narrow = false }) {
  useEffect(markArrived, []);
  return (
    <div className="min-h-[100dvh] bg-white">
      <div className="safe-top mx-auto max-w-6xl px-5 sm:px-6">
        <PublicHeader />
      </div>
      <div className={`mx-auto px-6 ${narrow ? "max-w-3xl" : "max-w-4xl"}`}>
        {children}
        <PublicFooter />
      </div>
    </div>
  );
}

/** The one header every public page shares, the home page's: brand, the
    tabs, language, sign in and the trial. On phones the tabs get their own
    scrolling row under it. Features, pricing and questions live on the home
    page, so elsewhere they link there. */
export function PublicHeader({ className = "" }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { pathname } = useLocation();
  const section = (id) => (pathname === "/" ? `#${id}` : `/#${id}`);
  const links = [
    [section("features"), t("home.nav.features")],
    [section("pricing"), t("home.nav.pricing")],
    [section("faq"), t("home.nav.faq")],
    ["/assessment", t("home.nav.checkup"), true],
    ["/about", t("about.link")],
  ];
  return (
    <header className={`flex flex-wrap items-center gap-3 py-5 ${className}`}>
      <Link to="/" className="flex min-h-10 items-center gap-2.5 rounded-lg [@media(pointer:coarse)]:min-h-11">
        <BrandMark size="sm" />
        <span className="text-[15px] font-semibold tracking-tight text-zinc-900">{APP_NAME}</span>
      </Link>
      <nav
        aria-label={t("home.nav.label")}
        className="order-last -mx-5 w-[calc(100%+2.5rem)] overflow-x-auto px-5 sm:-mx-6 sm:w-[calc(100%+3rem)] sm:px-6 md:order-none md:mx-0 md:ml-6 md:w-auto md:overflow-visible md:px-0"
      >
        <ul className="flex gap-5 whitespace-nowrap text-sm">
          {links.map(([to, label, accent]) => {
            const current = to === pathname;
            const look = accent
              ? `font-medium text-indigo-700 hover:text-indigo-900 ${current ? "underline decoration-2 underline-offset-8" : ""}`
              : current
                ? "font-medium text-zinc-900"
                : "text-zinc-600 hover:text-zinc-900";
            const box = `inline-flex min-h-9 items-center [@media(pointer:coarse)]:min-h-11 ${look}`;
            return (
              <li key={to}>
                {to.startsWith("#") ? (
                  <a href={to} className={box}>
                    {label}
                  </a>
                ) : (
                  <Link to={to} aria-current={current ? "page" : undefined} className={box}>
                    {label}
                  </Link>
                )}
              </li>
            );
          })}
        </ul>
      </nav>
      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        <LanguagePicker />
        <Link to={user ? "/" : "/login"} className="btn btn-secondary !h-9 !text-sm [@media(pointer:coarse)]:!h-11">
          {t(user ? "about.backToApp" : "login.signIn")}
        </Link>
        {!user && (
          <Link to="/register" className="btn btn-primary hidden !h-9 !text-sm sm:inline-flex">
            {t("home.nav.start")}
          </Link>
        )}
      </div>
    </header>
  );
}

export function PublicFooter() {
  const { t } = useTranslation();
  const links = [
    ["/about", t("about.link")],
    ["/assessment", t("home.nav.checkup")],
    ["/contact", t("contact.link")],
    ["/terms", t("legal.terms")],
    ["/privacy", t("legal.privacy")],
    ["/refunds", t("legal.refunds")],
  ];
  return (
    <footer className="safe-bottom mt-12 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-zinc-100 py-6 text-xs text-zinc-500">
      <span>
        © {new Date().getFullYear()} {APP_NAME} · {t("about.developedBy", { company: COMPANY_NAME })}
      </span>
      {links.map(([to, label]) => (
        <Link key={to} to={to} className="inline-flex min-h-9 items-center hover:text-zinc-800 [@media(pointer:coarse)]:min-h-11">
          {label}
        </Link>
      ))}
    </footer>
  );
}

// ---------------------------------------------------------------- contact

const TOPICS = ["sales", "support", "billing", "partnership", "other"];

export function ContactForm({ compact = false }) {
  const { t } = useTranslation();
  const [form, setForm] = useState({ name: "", email: "", phone: "", company: "", topic: "sales", message: "", website: "" });
  const [state, setState] = useState("idle"); // idle | sending | sent
  const [error, setError] = useState("");
  const set = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setError("");
    setState("sending");
    try {
      await apiClient.post("/public/contact", form);
      setState("sent");
    } catch (err) {
      setError(errorMessage(err, t("contact.failed")));
      setState("idle");
    }
  }

  if (state === "sent") {
    return (
      <div className="rounded-2xl bg-emerald-50 p-6 ring-1 ring-inset ring-emerald-200/70" role="status">
        <p className="font-semibold text-emerald-900">{t("contact.sentTitle")}</p>
        <p className="mt-1 text-sm text-emerald-900/80">{t("contact.sentBody", { email: form.email })}</p>
      </div>
    );
  }
  return (
    <form onSubmit={submit} className={`grid gap-4 ${compact ? "" : "sm:grid-cols-2"}`}>
      <Field label={t("contact.name")}>
        <input className="input" required minLength={2} maxLength={200} autoComplete="name" value={form.name} onChange={set("name")} />
      </Field>
      <Field label={t("contact.email")}>
        <input className="input" required type="email" autoComplete="email" value={form.email} onChange={set("email")} />
      </Field>
      <Field label={t("contact.phone")}>
        <input className="input" type="tel" autoComplete="tel" maxLength={50} value={form.phone} onChange={set("phone")} />
      </Field>
      <Field label={t("contact.company")}>
        <input className="input" autoComplete="organization" maxLength={200} value={form.company} onChange={set("company")} />
      </Field>
      <Field label={t("contact.topic")} className={compact ? "" : "sm:col-span-2"}>
        <select className="input" value={form.topic} onChange={set("topic")}>
          {TOPICS.map((v) => (
            <option key={v} value={v}>
              {t(`contact.topics.${v}`)}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("contact.message")} className={compact ? "" : "sm:col-span-2"}>
        <textarea className="input min-h-[8rem]" required minLength={5} maxLength={5000} value={form.message} onChange={set("message")} />
      </Field>
      {/* Hidden from people; spam bots fill it in. */}
      <input type="text" name="website" tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} className="hidden" aria-hidden="true" />
      <div className={`flex flex-wrap items-center justify-between gap-3 ${compact ? "" : "sm:col-span-2"}`}>
        <FormError>{error}</FormError>
        <button type="submit" className="btn btn-primary ml-auto" disabled={state === "sending"}>
          {state === "sending" ? t("common.sending") : t("contact.send")}
        </button>
      </div>
    </form>
  );
}

export function ContactPage() {
  const { t } = useTranslation();
  return (
    <PublicShell narrow>
      <section className="py-8">
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">{t("contact.title")}</h1>
        <p className="mt-2 max-w-xl text-zinc-600">{t("contact.intro")}</p>
        {LEGAL.email && (
          <p className="mt-2 text-sm text-zinc-500">
            {t("contact.orEmail")}{" "}
            <a href={`mailto:${LEGAL.email}`} className="inline-block py-2 -my-2 font-medium text-indigo-600 hover:text-indigo-700">
              {LEGAL.email}
            </a>
          </p>
        )}
        <div className="card mt-8 p-5 sm:p-7">
          <ContactForm />
        </div>
      </section>
    </PublicShell>
  );
}

// ---------------------------------------------------------------- passwords

export function ForgotPasswordPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiClient.post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">{t("password.forgotTitle")}</h1>
      {sent ? (
        <p className="mt-3 text-sm text-zinc-600" role="status">
          {t("password.sent", { email })}
        </p>
      ) : (
        <>
          <p className="mt-1.5 text-sm text-zinc-500">{t("password.forgotIntro")}</p>
          <form onSubmit={submit} className="mt-7 space-y-5">
            <div>
              <label className="label" htmlFor="email">
                {t("login.email")}
              </label>
              <GlowField id="email" type="email" inputMode="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <FormError>{error}</FormError>
            <button type="submit" className="btn btn-primary w-full" disabled={busy}>
              {busy ? t("common.sending") : t("password.sendLink")}
            </button>
          </form>
        </>
      )}
      <SwitchLink prompt={t("password.remembered")} to="/login" label={t("login.signIn")} />
    </AuthShell>
  );
}

/** The link in "Confirm your email". Works signed in or not. */
export function VerifyEmailPage() {
  const { t } = useTranslation();
  const { user, reloadUser } = useAuth();
  const [params] = useSearchParams();
  const [state, setState] = useState("checking"); // checking | done | failed
  const [error, setError] = useState("");
  const sent = useRef(false);
  useEffect(() => {
    if (sent.current) return; // once, even in React's double-run dev mode
    sent.current = true;
    apiClient
      .post("/auth/verify-email", { token: params.get("token") || "" })
      .then(() => {
        setState("done");
        reloadUser();
        announceVerified(); // other open tabs drop their reminder at once
      })
      .catch((err) => {
        const status = err?.response?.status;
        setError(status >= 400 && status < 500 ? t("verify.badLink") : errorMessage(err));
        setState("failed");
      });
  }, [params, reloadUser]);
  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
        {t(state === "done" ? "verify.doneTitle" : state === "failed" ? "verify.failedTitle" : "verify.checking")}
      </h1>
      {state === "done" && <p className="mt-1.5 text-sm text-zinc-500">{t("verify.doneBody")}</p>}
      {state === "failed" && <FormError>{error}</FormError>}
      {state !== "checking" && (
        <Link to={user ? "/" : "/login"} className="btn btn-primary mt-7 w-full">
          {t(user ? "verify.goToApp" : "login.signIn")}
        </Link>
      )}
    </AuthShell>
  );
}

export function ResetPasswordPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    if (password !== confirm) {
      setError(t("password.mismatch"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await apiClient.post("/auth/reset-password", { token, password });
      navigate("/login", { replace: true, state: { notice: t("password.done") } });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">{t("password.resetTitle")}</h1>
      <p className="mt-1.5 text-sm text-zinc-500">{t("password.resetIntro")}</p>
      <form onSubmit={submit} className="mt-7 space-y-5">
        <div>
          <label className="label" htmlFor="password">
            {t("password.new")}
          </label>
          <GlowField id="password" type="password" autoComplete="new-password" minLength={8} required value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="confirm">
            {t("password.confirm")}
          </label>
          <GlowField id="confirm" type="password" autoComplete="new-password" minLength={8} required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </div>
        <FormError>{error}</FormError>
        <button type="submit" className="btn btn-primary w-full" disabled={busy || !token}>
          {busy ? t("common.saving") : t("password.save")}
        </button>
      </form>
      <SwitchLink prompt={t("password.remembered")} to="/login" label={t("login.signIn")} />
    </AuthShell>
  );
}

/** From the invitation email: "Join <company> on YGT". They choose a
 *  password (typed twice), and they're in. */
export function InvitePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { acceptInvite, logout, user } = useAuth();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [invite, setInvite] = useState(null);
  const [linkError, setLinkError] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    apiClient
      .get("/auth/invite", { params: { token } })
      .then(({ data }) => setInvite(data))
      .catch((err) => setLinkError(errorMessage(err)));
  }, [token]);
  const mismatch = confirm.length > 0 && password !== confirm;
  async function submit(e) {
    e.preventDefault();
    if (password !== confirm) {
      setError(t("password.mismatch"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      // Someone else signed in on this browser: this is the invited person now.
      if (user) await logout();
      await acceptInvite(token, password);
      queueWelcome();
      navigate("/", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  if (linkError) {
    return (
      <AuthShell>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">{t("invite.badLinkTitle")}</h1>
        <FormError>{linkError}</FormError>
        <SwitchLink prompt={t("invite.alreadyJoined")} to="/login" label={t("login.signIn")} />
      </AuthShell>
    );
  }
  return (
    <AuthShell>
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
        {invite ? t("invite.title", { company: invite.company_name }) : t("common.loading")}
      </h1>
      {invite && <p className="mt-1.5 text-sm text-zinc-500">{t("invite.intro", { name: invite.full_name.split(" ")[0], email: invite.email })}</p>}
      <form onSubmit={submit} className="mt-7 space-y-5">
        <div>
          <label className="label" htmlFor="password">
            {t("invite.password")}
          </label>
          <GlowField id="password" type="password" autoComplete="new-password" minLength={8} required autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
          <span className="mt-1.5 block text-xs text-zinc-500">{t("register.passwordHint")}</span>
        </div>
        <div>
          <label className="label" htmlFor="confirm">
            {t("password.confirm")}
          </label>
          <GlowField id="confirm" type="password" autoComplete="new-password" minLength={8} required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          {mismatch && <span className="mt-1.5 block text-xs font-medium text-red-600">{t("password.mismatch")}</span>}
        </div>
        <FormError>{error}</FormError>
        <button type="submit" className="btn btn-primary w-full" disabled={busy || !invite || mismatch}>
          {busy ? t("common.saving") : t("invite.submit")}
        </button>
      </form>
    </AuthShell>
  );
}

// ---------------------------------------------------------------- legal

function Section({ title, children }) {
  return (
    <section className="mt-8">
      <h2 className="text-lg font-semibold text-zinc-900">{title}</h2>
      <div className="mt-2 space-y-3 text-[15px] leading-relaxed text-zinc-700">{children}</div>
    </section>
  );
}

const LEGAL_PAGES = {
  deleteAccount: {
    titleKey: "legal.deleteAccount",
    body: () => (
      <>
        <p>You can delete your YGT account yourself, at any time, from the app or the website:</p>
        <ol className="mt-3 list-decimal space-y-1 pl-5">
          <li>Sign in to YGT.</li>
          <li>Open <strong>My profile</strong> (your name, top right) or, for admins, <strong>Settings</strong>.</li>
          <li>Choose <strong>Delete my account</strong>, enter your password and confirm.</li>
        </ol>
        <Section title="What is deleted">
          <p>
            If you are the only admin of your company, the company and everything in it is deleted permanently: customers, deals, quotes, invoices,
            files and every team member's account. Any card subscription is cancelled first. If others still run the company, only your own account is
            removed: your name, email address and password are erased and you can no longer sign in.
          </p>
          <p className="mt-2">Payment records may be kept for as long as the law requires (for example for tax), and nothing else.</p>
        </Section>
        <Section title="Can't sign in?">
          <p>
            Email {LEGAL.email ? <a href={`mailto:${LEGAL.email}?subject=Delete%20my%20YGT%20account`} className="font-medium text-indigo-600">{LEGAL.email}</a> : "us"} from the
            address you signed up with and ask us to delete your account. We'll confirm it's you and delete it within 7 days.
          </p>
        </Section>
      </>
    ),
  },
  terms: {
    titleKey: "legal.terms",
    body: () => (
      <>
        <p>
          These terms apply when you or your organisation (“you”) use YGT (You Got This), a customer relationship management and invoicing service
          developed and run from South Africa by {LEGAL.company} (“YGT”, “we”). By creating an account you agree to them on behalf of your organisation.
        </p>
        <Section title="1. Your account">
          <p>You are responsible for the people you invite, for keeping passwords safe, and for the information you put into YGT. Each person must use their own sign-in.</p>
        </Section>
        <Section title="2. Free trial, plans and payment">
          <p>
            New organisations get a 14-day free trial; no card is needed. After the trial you choose a plan (Hustle, Grow or Scale). Plans are billed in South African
            rand, monthly or yearly, in advance, through Paystack. Subscriptions renew automatically until cancelled.
          </p>
          <p>
            If a trial ends or a payment fails and isn't fixed within a few days, your account becomes read-only: you can still view and export your information, but
            you can't add, change or send anything until a plan is active again. We may change prices with at least 30 days' notice.
          </p>
        </Section>
        <Section title="3. Cancelling">
          <p>
            You can cancel at any time in Settings &gt; Billing. Cancelling stops the next renewal; it doesn't end your plan straight away. Your subscription keeps
            running, with everything working, until the end of the billing period you've already paid for (the month, or the year on a yearly plan).
          </p>
          <p>
            After that, your workspace becomes read-only: you can still sign in, see and export your information, but you can't add, change or send anything until
            you choose a plan again. Nothing is deleted. Refunds are covered in our Refund policy.
          </p>
        </Section>
        <Section title="4. Your information">
          <p>
            Everything you add (clients, invoices, messages and so on) belongs to you. You can export it at any time. Under the Protection of Personal Information Act
            (POPIA) you are the responsible party for your clients' personal information and YGT is your operator: we process it only to provide the service, keep it
            secure, keep each organisation's information separate, and don't sell it. See our Privacy policy.
          </p>
        </Section>
        <Section title="5. Acceptable use">
          <p>
            Don't use YGT to send spam or unlawful messages, to break the law (including POPIA and the Consumer Protection Act), or to interfere with the service. Marketing
            emails must go only to people who agreed to receive them; every campaign includes an unsubscribe link. We may suspend accounts that break these terms.
          </p>
        </Section>
        <Section title="6. Your invoices and tax">
          <p>
            YGT helps you prepare quotes, invoices and statements, but you are responsible for their content and for your tax obligations, including whether you are
            registered for VAT. YGT doesn't give tax, legal or accounting advice.
          </p>
        </Section>
        <Section title="7. Availability and liability">
          <p>
            We work to keep YGT available and your information backed up, but the service is provided “as is”. To the extent the law allows, our total liability for any
            claim is limited to the fees you paid in the three months before it arose, and we aren't liable for indirect or consequential loss.
          </p>
        </Section>
        <Section title="8. Changes and law">
          <p>We'll tell you about material changes to these terms by email or in the app. These terms are governed by the laws of the Republic of South Africa.</p>
        </Section>
        <Section title="9. Contact">
          <p>
            {LEGAL.company}, registration number {missing(LEGAL.registration)}, {missing(LEGAL.address)}. Email: {missing(LEGAL.email)}.
          </p>
        </Section>
      </>
    ),
  },
  privacy: {
    titleKey: "legal.privacy",
    body: () => (
      <>
        <p>This policy explains how {LEGAL.company} handles personal information, in line with the Protection of Personal Information Act, 2013 (POPIA).</p>
        <Section title="1. Two roles">
          <p>
            <strong>Your account:</strong> for the details of the people who use YGT (names, email addresses, sign-in activity, billing details), we are the responsible
            party.
          </p>
          <p>
            <strong>Your clients' information:</strong> for the information organisations add about their own clients, the organisation is the responsible party and we
            are its operator. We process it only on their instructions, to provide the service.
          </p>
        </Section>
        <Section title="2. What we collect and why">
          <p>
            Account details, to run your account and support you; usage and security logs (such as sign-ins, errors and IP addresses), to keep the service secure and
            working; billing records, to charge for plans (card details are handled by Paystack, never stored by us); and messages you send our support team.
          </p>
        </Section>
        <Section title="3. Sharing">
          <p>
            We share information only with service providers that help us run YGT (hosting, email delivery, payments through Paystack, and WhatsApp or SMS providers you
            connect yourself), under agreements that protect it, or when the law requires it. Some providers store information outside South Africa; we only use
            providers with adequate protection, as POPIA requires.
          </p>
        </Section>
        <Section title="4. Security and retention">
          <p>
            Information is encrypted in transit, passwords and connection secrets are stored encrypted, and each organisation's information is kept separate. We keep
            account information while your account is open and for as long as the law requires afterwards; organisations can export or ask us to delete their information.
          </p>
        </Section>
        <Section title="5. Your rights">
          <p>
            You may ask what personal information we hold about you, ask us to correct or delete it, object to processing, and complain to the Information Regulator
            (inforegulator.org.za). Clients of organisations using YGT should contact that organisation first.
          </p>
        </Section>
        <Section title="6. Information officer">
          <p>
            {LEGAL.informationOfficer}, {missing(LEGAL.email)}. {LEGAL.company}, {missing(LEGAL.address)}.
          </p>
        </Section>
      </>
    ),
  },
  refunds: {
    titleKey: "legal.refunds",
    body: () => (
      <>
        <Section title="Cancelling your subscription">
          <p>
            You can cancel at any time in Settings &gt; Billing. When you cancel, your subscription runs until the end of the billing period you've paid for and then
            isn't renewed. You keep full use of YGT until that date; after it, your workspace becomes read-only and nothing is deleted.
          </p>
        </Section>
        <Section title="Free trial">
          <p>Every new organisation gets 14 days free. We don't ask for a card, so nothing is charged during the trial.</p>
        </Section>
        <Section title="Monthly plans">
          <p>You can cancel at any time; your plan runs to the end of the month you've paid for and isn't renewed. We don't refund part-months.</p>
        </Section>
        <Section title="Yearly plans">
          <p>If you cancel within 14 days of a yearly payment, we refund it in full. After that the plan runs to the end of the year and isn't renewed.</p>
        </Section>
        <Section title="Mistakes and outages">
          <p>If you were charged in error, or a serious outage on our side stopped you working, we'll refund the affected amount.</p>
        </Section>
        <Section title="How to ask">
          <p>
            Log a ticket in the app under Support, or email {missing(LEGAL.email)}. Approved refunds go back to the card you paid with through Paystack, usually within 5 to
            10 business days.
          </p>
        </Section>
      </>
    ),
  },
};

export function LegalPage({ kind }) {
  const { t } = useTranslation();
  const page = LEGAL_PAGES[kind];
  return (
    <PublicShell narrow>
      <article className="py-6">
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">{t(page.titleKey)}</h1>
        <p className="mt-2 text-sm text-zinc-500">
          {t("legal.updated", { date: LEGAL.updated })} · {t("legal.englishOnly")}
        </p>
        <div className="mt-4 text-[15px] leading-relaxed text-zinc-700">{page.body()}</div>
      </article>
    </PublicShell>
  );
}
