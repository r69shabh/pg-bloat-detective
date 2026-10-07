"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Blocker, Finding } from "@/lib/feed"

function verdictVariant(v: string): "secondary" | "outline" | "destructive" | "default" {
  if (v === "normal") return "secondary"
  if (v === "vacuum-starved" || v === "index-unused") return "outline"
  if (v.startsWith("blocked-by") || v === "index-bloated" || v === "needs-rewrite") return "destructive"
  return "default"
}

export function DataTable({ data }: { data: Finding[] }) {
  return (
    <Card className="w-full" id="findings">
      <CardHeader>
        <CardTitle>Findings — what should I do?</CardTitle>
        <CardDescription>
          One verdict per table or index. Read it as an instruction: normal = leave it alone,
          blocked-by-* = kill or wait out the named session then VACUUM,
          vacuum-starved = tune autovacuum, needs-rewrite / index-bloated = schedule
          pg_repack / VACUUM FULL / REINDEX. Evidence says why.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Table</TableHead>
              <TableHead>Verdict</TableHead>
              <TableHead className="text-right">Dead</TableHead>
              <TableHead className="text-right">Live</TableHead>
              <TableHead>Evidence</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((f) => (
              <TableRow key={f.table}>
                <TableCell className="font-medium">{f.table}</TableCell>
                <TableCell>
                  <Badge variant={verdictVariant(f.verdict)}>{f.verdict}</Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">{f.dead.toLocaleString()}</TableCell>
                <TableCell className="text-right tabular-nums">{f.live.toLocaleString()}</TableCell>
                <TableCell className="max-w-md truncate text-muted-foreground">{f.evidence}</TableCell>
              </TableRow>
            ))}
            {data.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No tables collected yet — run `bloatdetective collect`.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export function BlockersTable({ data }: { data: Blocker[] }) {
  return (
    <Card className="w-full" id="blockers">
      <CardHeader>
        <CardTitle>Blockers — who is pinning VACUUM?</CardTitle>
        <CardDescription>
          Sessions holding backend_xmin open. Postgres cannot vacuum any row newer than
          the oldest holder — that&apos;s the xmin horizon. Fix: end the session
          (or drop the stale slot / commit the prepared xact), then VACUUM.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Kind</TableHead>
              <TableHead className="text-right">PID</TableHead>
              <TableHead>Age</TableHead>
              <TableHead>Query / slot</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((b, i) => (
              <TableRow key={`${b.pid ?? b.slot}-${b.ts}-${i}`}>
                <TableCell>
                  <Badge variant={b.kind === "stale-slot" || b.kind === "prepared-xact" ? "destructive" : "outline"}>
                    {b.kind}
                  </Badge>
                </TableCell>
                <TableCell className="text-right tabular-nums">{b.pid ?? "—"}</TableCell>
                <TableCell className="tabular-nums">{b.age || "—"}</TableCell>
                <TableCell className="max-w-md truncate font-mono text-xs text-muted-foreground">
                  {b.slot || b.query || "—"}
                </TableCell>
              </TableRow>
            ))}
            {data.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No blockers — vacuum is free to advance.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
