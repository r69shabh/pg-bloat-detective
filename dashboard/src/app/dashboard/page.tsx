import { ChartAreaInteractive } from "@/components/chart-area-interactive"
import { BlockersTable, DataTable } from "@/components/data-table"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { Feed, Finding } from "@/lib/feed"

import data from "./data.json"

const feed = data as unknown as Feed

function recommendedAction(finding: Finding): string {
  const table = finding.table
  if (finding.verdict.startsWith("blocked-by")) {
    return `End the named session, then run VACUUM ${table}.`
  }
  if (finding.verdict === "vacuum-starved") {
    return `Run VACUUM (ANALYZE) ${table} or tune autovacuum.`
  }
  if (finding.verdict === "needs-rewrite") {
    return `Schedule pg_repack or VACUUM FULL on ${table}.`
  }
  if (finding.verdict === "index-bloated") {
    return `Schedule REINDEX INDEX ${table}.`
  }
  if (finding.verdict === "index-unused") {
    return `Verify with pg_stat_statements, then DROP INDEX ${table}.`
  }
  return `Investigate ${table} (${finding.verdict}).`
}

export default function Page() {
  const findings = feed.findings ?? []
  const blockers = feed.blockers ?? []
  const needsAttention = findings.filter((f) => f.verdict !== "normal")
  const worst = needsAttention[0]
  const generatedAt = new Date(feed.generated_at * 1000).toLocaleString()

  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-bold tracking-tight">
            Bloat Detective
          </h1>
          <p className="text-sm text-muted-foreground">{generatedAt}</p>
        </div>
        {needsAttention.length > 0 ? (
          <Badge variant="destructive">
            {needsAttention.length} need attention
          </Badge>
        ) : (
          <Badge variant="secondary">all clear</Badge>
        )}
      </div>

      {worst ? (
        <Card className="border-destructive/50 bg-destructive/5">
          <CardHeader>
            <CardTitle className="flex flex-wrap items-center gap-2">
              <span>{worst.table}</span>
              <Badge variant="destructive">{worst.verdict}</Badge>
            </CardTitle>
            <CardDescription>{worst.evidence}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm font-medium">
              {recommendedAction(worst)}
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-green-500/50 bg-green-500/5">
          <CardHeader>
            <CardTitle>All clear</CardTitle>
            <CardDescription>
              No action needed — vacuum is keeping up.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      <ChartAreaInteractive feed={feed} />
      <BlockersTable data={blockers} />
      <DataTable data={findings} />
    </main>
  )
}

