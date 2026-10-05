"use client"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Finding } from "@/lib/feed"

function verdictVariant(v: string): "secondary" | "outline" | "destructive" | "default" {
  if (v === "normal") return "secondary"
  if (v === "vacuum-starved" || v === "index-unused") return "outline"
  if (v.startsWith("blocked-by") || v === "index-bloated") return "destructive"
  return "default"
}

export function DataTable({ data }: { data: Finding[] }) {
  return (
    <Card className="mx-4 lg:mx-6">
      <CardHeader>
        <CardTitle>Findings</CardTitle>
        <CardDescription>One verdict per table — every finding links to its evidence</CardDescription>
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
