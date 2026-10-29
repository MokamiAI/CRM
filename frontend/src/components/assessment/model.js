/*
 * The free business check-up: the questions, and the arithmetic that turns
 * the answers into a score, the biggest gaps and the hours YGT could give
 * back. It's plain rules, not a model guessing, so every number can be
 * explained (the report prints its assumptions).
 */
import { PEOPLE } from "../home/HomePeople";

export const QUESTIONS = [
  { key: "industry", kind: "single", options: [...PEOPLE.map((p) => p.key), "other"] },
  { key: "team", kind: "single", options: ["solo", "small", "team", "large"] },
  { key: "customers", kind: "multi", options: ["phone", "whatsapp", "excel", "paper", "email", "crm"] },
  { key: "enquiries", kind: "single", options: ["memory", "whatsapp", "excel", "crm"] },
  { key: "slip", kind: "single", options: ["rarely", "some", "often", "unsure"] },
  { key: "tasks", kind: "multi", options: ["memory", "paper", "whatsapp", "calendar", "excel", "taskApp"] },
  { key: "documents", kind: "multi", options: ["word", "excel", "whatsapp", "paper", "accounting", "invoicing"] },
  { key: "volume", kind: "range", min: 5, max: 300, step: 5, initial: 30 },
  { key: "payments", kind: "single", options: ["rarely", "manual", "remember", "automatic"] },
  { key: "tools", kind: "count", min: 1, max: 20 },
];

// The answers that name a tool (an app, a book, a chat, or memory). The
// same tool picked in several questions counts once: that's the point.
const TOOL_QUESTIONS = ["customers", "enquiries", "tasks", "documents"];
const NOT_TOOLS = new Set(["rarely", "some", "often", "unsure"]);

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

const TEAM = {
  solo: { seats: 1, factor: 1, plan: "hustle" },
  small: { seats: 3, factor: 1.8, plan: "hustle" },
  team: { seats: 6, factor: 3, plan: "grow" },
  large: { seats: 12, factor: 4.5, plan: "scale" },
};

const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
const mean = (list) => list.reduce((a, b) => a + b, 0) / list.length;

/** The average of what was picked, less 2 for each extra place: the same
    job spread over three tools is worse than any one of them. */
function spreadScore(picked = [], table) {
  if (!picked.length) return 0;
  return clamp(Math.round(mean(picked.map((v) => table[v] ?? 0)) - 2 * (picked.length - 1)), 0, AREA_MAX);
}

// Minutes per quote or invoice, by where it's made today; YGT_MINUTES with YGT.
const DOC_MINUTES = { word: 20, excel: 18, whatsapp: 15, paper: 25, accounting: 10, invoicing: 8 };
const YGT_MINUTES = 5;
// Hours a month, per person, spent finding where things stand.
const PIPELINE_HOURS = { memory: 3, whatsapp: 2.5, excel: 1.5, crm: 0.25 };
const TASK_HOURS = { memory: 2.5, paper: 2, whatsapp: 2, calendar: 1.25, excel: 1.5, taskApp: 0.25 };
// Of the documents, the share that are invoices, the share of those paid
// late, and the minutes each chase takes by hand.
const INVOICE_SHARE = 0.6;
const LATE_SHARE = { rarely: 0.05, manual: 0.3, remember: 0.3, automatic: 0.05 };
const CHASE_MINUTES = 12;
// Each tool past two costs this much switching and copying, per person.
const SWITCH_HOURS = 0.5;
// Tools past this many cost points.
const TOOLS_OK = 3;

export const ASSUMPTIONS = { DOC_MINUTES, YGT_MINUTES, CHASE_MINUTES, SWITCH_HOURS, TOOLS_OK };

export function assess(answers) {
  const team = TEAM[answers.team] ?? TEAM.solo;
  const volume = answers.volume ?? 30;
  const detected = toolsUsed(answers);
  const tools = Math.max(answers.tools ?? detected.length, 1);

  const areas = {
    customers: spreadScore(answers.customers, QUALITY.customers),
    pipeline: clamp((QUALITY.enquiries[answers.enquiries] ?? 0) + (QUALITY.slip[answers.slip] ?? 0), 0, AREA_MAX),
    tasks: clamp(spreadScore(answers.tasks, QUALITY.tasks) - (team.seats > 1 && !answers.tasks?.includes("taskApp") ? 2 : 0), 1, AREA_MAX),
    documents: spreadScore(answers.documents, QUALITY.documents),
    payments: QUALITY.payments[answers.payments] ?? 0,
  };
  const toolPenalty = Math.min(12, Math.max(0, tools - TOOLS_OK) * 2);
  const score = clamp(Math.round(AREAS.reduce((sum, a) => sum + areas[a], 0) - toolPenalty), 5, 100);

  const docs = answers.documents?.length ? answers.documents : ["excel"];
  const customerSources = answers.customers ?? [];
  const hours = {
    documents: (volume * Math.max(0, mean(docs.map((d) => DOC_MINUTES[d])) - YGT_MINUTES)) / 60,
    customers: (customerSources.includes("crm") && customerSources.length === 1 ? 0.25 : 1 + 0.5 * Math.max(0, customerSources.length - 1)) * team.factor,
    pipeline: (PIPELINE_HOURS[answers.enquiries] ?? 2) * team.factor,
    tasks: (answers.tasks?.length ? mean(answers.tasks.map((v) => TASK_HOURS[v])) : 2) * team.factor,
    payments: (volume * INVOICE_SHARE * (LATE_SHARE[answers.payments] ?? 0.3) * CHASE_MINUTES) / 60,
    switching: Math.max(0, tools - 2) * SWITCH_HOURS * team.factor,
  };
  const totalHours = Math.max(1, Math.round(Object.values(hours).reduce((a, b) => a + b, 0)));

  // The weakest areas, worst first; anything nearly full marks isn't a gap.
  const gaps = AREAS.filter((a) => areas[a] < AREA_MAX * 0.85)
    .sort((a, b) => areas[a] - areas[b])
    .slice(0, 3);

  return { areas, score, toolPenalty, tools, detected, hours, totalHours, gaps, team, volume };
}

export function band(score) {
  if (score >= 70) return "strong";
  if (score >= 40) return "middle";
  return "weak";
}

/** What the recommended plan costs a month, from the live prices. */
export function planCost(plan, seats) {
  if (!plan) return null;
  if (!plan.per_user) return plan.monthly_cents / 100;
  const n = Math.max(seats, plan.min_users);
  const seat = plan.team_monthly_cents && n >= plan.team_seats ? plan.team_monthly_cents : plan.monthly_cents;
  return (seat * n) / 100;
}
