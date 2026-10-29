/*
 * The free business check-up: the questions, and the arithmetic that turns
 * the answers into an operations score, the biggest gaps, the hours YGT
 * could give back and the plan that fits. It's plain rules, not a model
 * guessing, so every number can be explained (the report prints its
 * assumptions). Bump MODEL_VERSION whenever a rule changes, so a lead's
 * summary says which rules produced it.
 */
import { PEOPLE } from "../home/HomePeople";

export const MODEL_VERSION = 2;

export const QUESTIONS = [
  // Business type and the people who'd use YGT, on one card.
  { key: "profile", kind: "profile", industry: [...PEOPLE.map((p) => p.key), "other"], team: ["solo", "small", "team", "large"] },
  { key: "customers", kind: "multi", options: ["phone", "whatsapp", "excel", "paper", "email", "crm"] },
  { key: "enquiries", kind: "single", options: ["memory", "whatsapp", "excel", "crm"] },
  { key: "slip", kind: "single", options: ["rarely", "some", "often", "unsure"] },
  { key: "tasks", kind: "multi", options: ["memory", "paper", "whatsapp", "calendar", "excel", "taskApp"] },
  { key: "documents", kind: "multi", options: ["word", "excel", "whatsapp", "paper", "accounting", "invoicing"] },
  { key: "volume", kind: "range", min: 5, max: 300, step: 5, initial: 30 },
  { key: "payments", kind: "single", options: ["rarely", "manual", "remember", "automatic"] },
  { key: "needs", kind: "multi", options: ["basics", "whatsapp", "marketing", "recurring", "owing", "chat", "leads", "priority"] },
  { key: "tools", kind: "count", min: 1, max: 20 },
];

// The answers that name a tool (an app, a book, a chat, or memory). The
// same tool picked in several questions counts once: that's the point.
const TOOL_QUESTIONS = ["customers", "enquiries", "tasks", "documents"];
const NOT_TOOLS = new Set(["rarely", "some", "often", "unsure"]);
// A proper system of record for the job. Supporting tools next to one are
// normal (a CRM plus WhatsApp is fine); the same job spread over loose
// tools is what loses information.
const SYSTEMS = new Set(["crm", "taskApp", "invoicing", "accounting"]);

export function toolsUsed(answers) {
  const found = new Set();
  for (const key of TOOL_QUESTIONS) {
    for (const v of [answers[key]].flat()) if (v && !NOT_TOOLS.has(v)) found.add(v);
  }
  return [...found];
}

// How well each answer holds up, out of the most an area can score.
const QUALITY = {
  customers: { crm: 20, excel: 12, email: 9, phone: 8, whatsapp: 6, paper: 4 },
  enquiries: { crm: 14, excel: 9, whatsapp: 4, memory: 2 },
  slip: { rarely: 6, some: 3, unsure: 1, often: 0 },
  tasks: { taskApp: 20, calendar: 13, excel: 11, whatsapp: 7, paper: 6, memory: 3 },
  documents: { invoicing: 20, accounting: 17, excel: 9, word: 8, whatsapp: 5, paper: 3 },
  payments: { automatic: 20, rarely: 16, manual: 9, remember: 4 },
};
export const AREAS = ["customers", "pipeline", "tasks", "documents", "payments"];
export const AREA_MAX = 20;

// Team answers count the people who handle customers, quotes, invoices or
// follow-ups (the ones who'd use YGT), not the whole headcount. The factor
// scales the time spent looking things up; it grows slower than the team,
// since people share some of it.
const TEAM = {
  solo: { seats: 1, factor: 1 },
  small: { seats: 3, factor: 1.7 },
  team: { seats: 6, factor: 2.6 },
  large: { seats: 12, factor: 3.8 },
};

const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
const mean = (list) => list.reduce((a, b) => a + b, 0) / list.length;

/** With a system of record: the best one, less 1 for each loose tool
    beside it (at most 4). Without one: the average of what was picked,
    less 2 for each extra place, since the same job spread over three loose
    tools is worse than any one of them. */
function areaScore(picked = [], table) {
  if (!picked.length) return 0;
  const systems = picked.filter((v) => SYSTEMS.has(v));
  if (systems.length) {
    const loose = picked.length - systems.length;
    return clamp(Math.max(...systems.map((v) => table[v] ?? 0)) - Math.min(4, loose), 0, AREA_MAX);
  }
  return clamp(Math.round(mean(picked.map((v) => table[v] ?? 0)) - 2 * (picked.length - 1)), 0, AREA_MAX);
}

// Minutes per quote or invoice, by where it's made today; YGT_MINUTES with YGT.
const DOC_MINUTES = { word: 20, excel: 18, whatsapp: 15, paper: 25, accounting: 10, invoicing: 8 };
const YGT_MINUTES = 5;
// Hours a month, per person, looking up a customer's number or history.
const CUSTOMER_HOURS = 1;
// Hours a month, per person, working out where enquiries and tasks stand.
const PIPELINE_HOURS = { memory: 3, whatsapp: 2.5, excel: 1.5, crm: 0.25 };
const TASK_HOURS = { memory: 2.5, paper: 2, whatsapp: 2, calendar: 1.25, excel: 1.5, taskApp: 0.25 };
// The same lookups in YGT, per person.
const YGT_LOOKUP_HOURS = 0.25;
// Of the documents, the share that are invoices, the share of those paid
// late, and the minutes each chase takes by hand (or just to check, with
// YGT's reminders doing the chasing).
const INVOICE_SHARE = 0.6;
const LATE_SHARE = { rarely: 0.05, manual: 0.3, remember: 0.3, automatic: 0.05 };
const CHASE_MINUTES = 12;
const YGT_CHASE_MINUTES = 3;
// Copying between loose tools, per tool past two, per person. Only this
// line counts switching: the lookups above are the searching itself, so
// the same minute isn't counted twice.
const SWITCH_HOURS = 0.5;
// Loose tools past this many cost points.
const TOOLS_OK = 3;
// The cautious end of the range: you move about half your admin into YGT,
// and each quote or invoice takes 10 minutes rather than 5.
const LOW_SHARE = 0.5;
const LOW_YGT_MINUTES = 10;

export const ASSUMPTIONS = { DOC_MINUTES, YGT_MINUTES, LOW_YGT_MINUTES, CHASE_MINUTES, SWITCH_HOURS, TOOLS_OK, LOW_SHARE };

/** What each part of the admin takes now, and with YGT, in hours a month. */
function timeSheet(answers, team, volume, loose, ygtMinutes) {
  const docs = answers.documents?.length ? answers.documents : ["excel"];
  const crmOnly = answers.customers?.length === 1 && answers.customers[0] === "crm";
  const late = volume * INVOICE_SHARE * (LATE_SHARE[answers.payments] ?? 0.3);
  const lookup = YGT_LOOKUP_HOURS * team.factor;
  return {
    documents: { now: (volume * mean(docs.map((d) => DOC_MINUTES[d]))) / 60, ygt: (volume * ygtMinutes) / 60 },
    customers: { now: (crmOnly ? YGT_LOOKUP_HOURS : CUSTOMER_HOURS) * team.factor, ygt: lookup },
    pipeline: { now: (PIPELINE_HOURS[answers.enquiries] ?? 2) * team.factor, ygt: lookup },
    tasks: { now: (answers.tasks?.length ? mean(answers.tasks.map((v) => TASK_HOURS[v])) : 2) * team.factor, ygt: lookup },
    payments: { now: (late * CHASE_MINUTES) / 60, ygt: (late * YGT_CHASE_MINUTES) / 60 },
    switching: { now: Math.max(0, loose - 2) * SWITCH_HOURS * team.factor, ygt: 0 },
  };
}

const saved = (sheet, share = 1) => Object.values(sheet).reduce((sum, line) => sum + Math.max(0, line.now - line.ygt) * share, 0);

// Features each need asks for, as the plans name them (see backend plans.py).
const NEED_FEATURES = {
  whatsapp: "whatsapp_sms",
  marketing: "marketing",
  recurring: "recurring_invoices",
  owing: "reports",
  chat: "team_chat",
  leads: "discovery",
  priority: "priority_support",
};

/** The cheapest plan that has every feature asked for and room for the
    team, from the live plans (so a price or feature change follows). */
export function recommendPlan(plans, needs = [], seats = 1) {
  if (!plans?.length) return null;
  const wanted = needs.map((n) => NEED_FEATURES[n]).filter(Boolean);
  const fits = plans.filter((p) => wanted.every((f) => p.features?.includes(f)) && (p.max_users == null || seats <= p.max_users));
  const options = (fits.length ? fits : plans).map((p) => ({ plan: p, cost: planCost(p, seats) }));
  options.sort((a, b) => a.cost - b.cost);
  const best = options[0];
  return { ...best, wanted: wanted.filter((f) => best.plan.features?.includes(f)) };
}

export function assess(answers) {
  const team = TEAM[answers.team] ?? TEAM.solo;
  const volume = answers.volume ?? 30;
  const detected = toolsUsed(answers);
  // Never fewer than the answers already named: the count can only add.
  const tools = Math.max(answers.tools ?? 0, detected.length, 1);
  const systems = detected.filter((v) => SYSTEMS.has(v)).length;
  const loose = tools - systems;

  const areas = {
    customers: areaScore(answers.customers, QUALITY.customers),
    pipeline: clamp((QUALITY.enquiries[answers.enquiries] ?? 0) + (QUALITY.slip[answers.slip] ?? 0), 0, AREA_MAX),
    tasks: clamp(areaScore(answers.tasks, QUALITY.tasks) - (team.seats > 1 && !answers.tasks?.includes("taskApp") ? 2 : 0), 1, AREA_MAX),
    documents: areaScore(answers.documents, QUALITY.documents),
    payments: QUALITY.payments[answers.payments] ?? 0,
  };
  const toolPenalty = Math.min(12, Math.max(0, loose - TOOLS_OK) * 2);
  const score = clamp(Math.round(AREAS.reduce((sum, a) => sum + areas[a], 0) - toolPenalty), 0, 100);

  const sheet = timeSheet(answers, team, volume, loose, YGT_MINUTES);
  const total = (key) => Object.values(sheet).reduce((sum, line) => sum + line[key], 0);
  const high = Math.max(1, Math.round(saved(sheet)));
  const low = Math.max(1, Math.min(high, Math.round(saved(timeSheet(answers, team, volume, loose, LOW_YGT_MINUTES), LOW_SHARE))));

  // The weakest areas, worst first; anything nearly full marks isn't a gap.
  const gaps = AREAS.filter((a) => areas[a] < AREA_MAX * 0.85)
    .sort((a, b) => areas[a] - areas[b])
    .slice(0, 3);

  return {
    areas,
    score,
    toolPenalty,
    tools,
    loose,
    detected,
    sheet,
    hoursNow: Math.round(total("now")),
    hoursYgt: Math.round(total("ygt")),
    hours: { low, high },
    gaps,
    team,
    volume,
  };
}

export function band(score) {
  if (score >= 85) return "high";
  if (score >= 70) return "organised";
  if (score >= 40) return "progress";
  return "attention";
}

/** What a plan costs a month for this many people, from the live prices. */
export function planCost(plan, seats) {
  if (!plan) return null;
  if (!plan.per_user) return plan.monthly_cents / 100;
  const n = Math.max(seats, plan.min_users);
  const seat = plan.team_monthly_cents && n >= plan.team_seats ? plan.team_monthly_cents : plan.monthly_cents;
  return (seat * n) / 100;
}
