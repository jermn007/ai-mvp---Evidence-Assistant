import React, { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Copy, Check, Download, Database, Search as SearchIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";

// ---------------- Types aligned with app.press_contract ----------------

type LICO = {
  learner: string;
  intervention: string;
  context: string;
  outcome: string;
};

type StrategyLine = {
  n: number;
  type: "Learner" | "Intervention" | "Context" | "Outcome" | "Combine" | "Limits" | "MeSH" | "Text";
  text: string;
  hits?: number | null;
};

type PressStrategy = {
  database: string;
  interface: string;
  lines: StrategyLine[];
};

type PressChecklist = {
  translation: "pass" | "suggest" | "revise";
  subject_headings: "pass" | "suggest" | "revise";
  text_words: "pass" | "suggest" | "revise";
  spelling_syntax_lines: "pass" | "suggest" | "revise";
  limits_filters: "pass" | "suggest" | "revise";
  notes?: string | null;
};

type PressPlanResponse = {
  question_lico: LICO;
  strategies: Record<string, PressStrategy>; // keyed by db
  checklist: Record<string, PressChecklist>; // keyed by db
};

type DatabaseSpec = { name: string; interface: string };

// ---------------- Utilities ----------------

const defaultLICO: LICO = {
  learner: "",
  intervention: "",
  context: "",
  outcome: "",
};

function classNames(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
    return false;
  }
}

function buildCombinedQuery(lines: StrategyLine[]): string {
  // Build map of line number -> text
  const map = new Map<number, string>();
  lines.forEach((l) => map.set(l.n, l.text));

  // Find combine and limits
  const combine = lines.find((l) => l.type === "Combine");
  const limits = lines.find((l) => l.type === "Limits");

  const expandRefs = (expr: string) =>
    expr.replace(/\b(\d+)\b/g, (_, g1) => `(${map.get(Number(g1)) ?? ""})`);

  let q = "";
  if (combine) {
    q = expandRefs(combine.text);
  } else {
    // No combine line → AND all facet lines that are not limits/combine
    const parts = lines
      .filter((l) => l.type !== "Combine" && l.type !== "Limits")
      .sort((a, b) => a.n - b.n)
      .map((l) => `(${l.text})`);
    q = parts.join(" AND ");
  }
  if (limits?.text) {
    q = `(${q}) AND (${limits.text})`;
  }
  return q;
}

function downloadJson(name: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------- API ----------------

async function postPlan(baseUrl: string, lico: LICO, dbs: DatabaseSpec[], withHits: boolean): Promise<PressPlanResponse> {
  const path = withHits ? "/press/plan/hits" : "/press/plan";
  const res = await fetch((baseUrl || "") + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lico, databases: dbs }),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

async function getPlanForRun(baseUrl: string, runId: string, withHits: boolean): Promise<PressPlanResponse> {
  const path = withHits ? `/runs/${encodeURIComponent(runId)}/press.plan.hits.json` : `/runs/${encodeURIComponent(runId)}/press.plan.json`;
  const res = await fetch((baseUrl || "") + path);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

// ---------------- UI ----------------

export default function PressPlannerApp() {
  const [apiBase, setApiBase] = useState<string>("http://127.0.0.1:8000");
  const [mode, setMode] = useState<"lico" | "run">("lico");
  const [lico, setLICO] = useState<LICO>({ ...defaultLICO });
  const [runId, setRunId] = useState<string>("");
  const [dbName, setDbName] = useState<string>("MEDLINE");
  const [iface, setIface] = useState<string>("PubMed");
  const [withHits, setWithHits] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [plan, setPlan] = useState<PressPlanResponse | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [copiedCombine, setCopiedCombine] = useState<boolean>(false);

  const currentStrategy = useMemo(() => {
    if (!plan) return null;
    // Prefer chosen db; else first available
    return plan.strategies[dbName] || Object.values(plan.strategies)[0];
  }, [plan, dbName]);

  const combinedQuery = useMemo(() => {
    if (!currentStrategy) return "";
    return buildCombinedQuery(currentStrategy.lines || []);
  }, [currentStrategy]);

  const onSubmit = async () => {
    setLoading(true);
    setError(null);
    setPlan(null);
    try {
      let resp: PressPlanResponse;
      if (mode === "lico") {
        const dbs: DatabaseSpec[] = dbName ? [{ name: dbName, interface: iface }] : [];
        resp = await postPlan(apiBase.trim(), lico, dbs, withHits);
      } else {
        if (!runId.trim()) throw new Error("Please enter a run ID");
        resp = await getPlanForRun(apiBase.trim(), runId.trim(), withHits);
      }
      setPlan(resp);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const checklist = useMemo(() => {
    if (!plan) return null;
    // Try to pick checklist for active DB; else first
    return plan.checklist[dbName] || Object.values(plan.checklist)[0];
  }, [plan, dbName]);

  return (
    <div className="min-h-screen bg-gradient-to-b from-white to-slate-50">
      <div className="max-w-6xl mx-auto p-6 space-y-6">
        <motion.h1
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-3xl md:text-4xl font-semibold tracking-tight"
        >
          PRESS Planner <span className="text-slate-500">(LICO → MEDLINE/PubMed)</span>
        </motion.h1>

        <Card className="shadow-sm">
          <CardHeader className="pb-4">
            <CardTitle className="text-xl">Configuration</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-6">
            <div className="grid md:grid-cols-3 gap-4 items-end">
              <div>
                <Label htmlFor="api">API Base URL</Label>
                <Input id="api" value={apiBase} onChange={(e) => setApiBase(e.target.value)} placeholder="http://127.0.0.1:8000" />
              </div>
              <div className="flex items-center gap-3">
                <Switch checked={mode === "run"} onCheckedChange={(v) => setMode(v ? "run" : "lico")} id="mode" />
                <Label htmlFor="mode">Use existing run ID</Label>
              </div>
              <div className="flex items-center gap-3">
                <Switch checked={withHits} onCheckedChange={setWithHits} id="hits" />
                <Label htmlFor="hits">Compute counts (PubMed)</Label>
              </div>
            </div>

            {mode === "run" ? (
              <div className="grid md:grid-cols-3 gap-4">
                <div className="md:col-span-2">
                  <Label>Run ID</Label>
                  <Input value={runId} onChange={(e) => setRunId(e.target.value)} placeholder="e.g., 9ddc..." />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Database</Label>
                    <Select value={dbName} onValueChange={setDbName}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="MEDLINE">MEDLINE</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Interface</Label>
                    <Select value={iface} onValueChange={setIface}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="PubMed">PubMed</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            ) : (
              <div className="grid md:grid-cols-4 gap-4">
                <div className="md:col-span-2">
                  <Label>Learner</Label>
                  <Input value={lico.learner} onChange={(e) => setLICO({ ...lico, learner: e.target.value })} placeholder="e.g., prelicensure nursing students" />
                </div>
                <div className="md:col-span-2">
                  <Label>Intervention</Label>
                  <Input value={lico.intervention} onChange={(e) => setLICO({ ...lico, intervention: e.target.value })} placeholder="e.g., simulation-based active learning" />
                </div>
                <div className="md:col-span-2">
                  <Label>Context</Label>
                  <Input value={lico.context} onChange={(e) => setLICO({ ...lico, context: e.target.value })} placeholder="e.g., university or clinical placements" />
                </div>
                <div className="md:col-span-2">
                  <Label>Outcome</Label>
                  <Input value={lico.outcome} onChange={(e) => setLICO({ ...lico, outcome: e.target.value })} placeholder="e.g., skills, attitudes, patient outcomes" />
                </div>
                <div className="md:col-span-2">
                  <Label>Database</Label>
                  <Select value={dbName} onValueChange={setDbName}>
                    <SelectTrigger><SelectValue placeholder="Choose a database" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="MEDLINE">MEDLINE</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="md:col-span-2">
                  <Label>Interface</Label>
                  <Select value={iface} onValueChange={setIface}>
                    <SelectTrigger><SelectValue placeholder="Choose an interface" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="PubMed">PubMed</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <Button onClick={onSubmit} disabled={loading} className="gap-2">
                <SearchIcon className="h-4 w-4" />
                {loading ? "Planning..." : "Build PRESS plan"}
              </Button>
              {plan && (
                <Button variant="secondary" onClick={() => downloadJson("press-plan.json", plan)} className="gap-2">
                  <Download className="h-4 w-4" /> Download JSON
                </Button>
              )}
            </div>
            {error && (
              <div className="text-sm text-red-600">{error}</div>
            )}
          </CardContent>
        </Card>

        {plan && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="grid md:grid-cols-3 gap-6">
            <Card className="md:col-span-2 shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-xl">
                  <Database className="h-5 w-5" /> {currentStrategy?.database} <span className="text-slate-500">/ {currentStrategy?.interface}</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {currentStrategy?.lines?.map((l) => (
                    <div key={l.n} className="rounded-2xl border p-3 hover:bg-slate-50">
                      <div className="flex items-start gap-3">
                        <Badge variant="secondary" className="mt-0.5">{l.n}</Badge>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between">
                            <div className="font-medium text-slate-700">{l.type}</div>
                            <div className="flex items-center gap-4 text-sm text-slate-500">
                              {typeof l.hits === "number" && (
                                <span className="rounded-full bg-slate-100 px-2 py-0.5">{l.hits.toLocaleString()} hits</span>
                              )}
                              <button
                                className="inline-flex items-center gap-1 text-slate-600 hover:text-slate-900"
                                onClick={async () => {
                                  const ok = await copy(l.text);
                                  setCopiedIdx(ok ? l.n : null);
                                  setTimeout(() => setCopiedIdx(null), 1200);
                                }}
                                title="Copy line"
                              >
                                {copiedIdx === l.n ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} Copy
                              </button>
                            </div>
                          </div>
                          <div className="mt-1 text-sm text-slate-800 break-words">{l.text}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {currentStrategy?.lines?.length ? (
                  <div className="mt-6 border-t pt-4 space-y-2">
                    <div className="text-sm font-medium">Combined query</div>
                    <Textarea readOnly value={combinedQuery} className="min-h-[120px] text-sm" />
                    <div className="flex gap-2">
                      <Button variant="secondary" className="gap-2" onClick={async () => {
                        const ok = await copy(combinedQuery);
                        setCopiedCombine(!!ok);
                        setTimeout(() => setCopiedCombine(false), 1200);
                      }}>
                        {copiedCombine ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} Copy combined
                      </Button>
                      <Button variant="outline" onClick={() => downloadJson("press-plan-lines.json", currentStrategy)} className="gap-2">
                        <Download className="h-4 w-4" /> Download lines JSON
                      </Button>
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>

            <Card className="shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-xl">Checklist</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {checklist && (
                    <>
                      <ChecklistItem label="Translation" value={checklist.translation} />
                      <ChecklistItem label="Subject headings" value={checklist.subject_headings} />
                      <ChecklistItem label="Text words" value={checklist.text_words} />
                      <ChecklistItem label="Spelling / syntax / lines" value={checklist.spelling_syntax_lines} />
                      <ChecklistItem label="Limits & filters" value={checklist.limits_filters} />
                    </>
                  )}
                </div>
                {plan?.question_lico && (
                  <div className="mt-4 space-y-1 text-sm">
                    <div className="font-medium text-slate-700">Question (LICO)</div>
                    <div><span className="font-semibold">L:</span> {plan.question_lico.learner || "—"}</div>
                    <div><span className="font-semibold">I:</span> {plan.question_lico.intervention || "—"}</div>
                    <div><span className="font-semibold">C:</span> {plan.question_lico.context || "—"}</div>
                    <div><span className="font-semibold">O:</span> {plan.question_lico.outcome || "—"}</div>
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        )}
      </div>
    </div>
  );
}

function ChecklistItem({ label, value }: { label: string; value: "pass" | "suggest" | "revise" }) {
  const color = value === "pass" ? "bg-emerald-100 text-emerald-800" : value === "suggest" ? "bg-amber-100 text-amber-800" : "bg-rose-100 text-rose-800";
  const dot = value === "pass" ? "bg-emerald-500" : value === "suggest" ? "bg-amber-500" : "bg-rose-500";
  return (
    <div className={classNames("flex items-center justify-between rounded-xl border p-2", value === "pass" ? "border-emerald-200" : value === "suggest" ? "border-amber-200" : "border-rose-200") }>
      <span className="text-slate-700">{label}</span>
      <span className={classNames("inline-flex items-center gap-2 rounded-full px-2 py-0.5 text-xs font-medium", color)}>
        <span className={classNames("h-2 w-2 rounded-full", dot)} />
        {value}
      </span>
    </div>
  );
}
