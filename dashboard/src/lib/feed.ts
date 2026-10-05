export interface Finding {
  table: string;
  verdict: string;
  evidence: string;
  dead: number;
  live: number;
  horizon: string | null;
}

export interface SeriesPoint {
  ts: number;
  live: number;
  dead: number;
}

export interface Blocker {
  ts: number;
  kind: string;
  pid: number | null;
  age: string;
  query: string;
  slot: string;
}

export interface Feed {
  generated_at: number;
  findings: Finding[];
  series: Record<string, SeriesPoint[]>;
  approx: Record<string, { ts: number; dead_pct: number }[]>;
  blockers: Blocker[];
}
