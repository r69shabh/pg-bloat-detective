"use client"

import type { ReactNode } from "react"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { TrendingDownIcon, TrendingUpIcon, TriangleAlertIcon, CheckCircle2Icon } from "lucide-react"
import type { Feed } from "@/lib/feed"

export function SectionCards({ feed }: { feed: Feed }) {
  const blocked = feed.findings.filter((f) => f.verdict.startsWith("blocked-by")).length
  const totalDead = feed.findings.reduce((s, f) => s + f.dead, 0)
  const worstApprox = Math.max(0, ...Object.values(feed.approx).flat().map((p) => p.dead_pct))
  const cards = [
    {
      desc: "Tables monitored",
      value: String(feed.findings.length),
      badge: null as ReactNode,
      foot: "From pg_stat_user_tables",
    },
    {
      desc: "Blocked tables",
      value: String(blocked),
      badge:
        blocked > 0 ? (
          <Badge variant="destructive">
            <TriangleAlertIcon /> needs attention
          </Badge>
        ) : (
          <Badge variant="secondary">
            <CheckCircle2Icon /> vacuum advancing
          </Badge>
        ),
      foot: "xmin pinned by a live session",
    },
    {
      desc: "Total dead tuples",
      value: totalDead.toLocaleString(),
      badge: (
        <Badge variant="outline">
          <TrendingUpIcon /> reclaimable?
        </Badge>
      ),
      foot: "Sum across monitored tables",
    },
    {
      desc: "Worst approx bloat",
      value: `${worstApprox.toFixed(1)}%`,
      badge: (
        <Badge variant="outline">
          <TrendingDownIcon /> pgstattuple_approx
        </Badge>
      ),
      foot: ">30% suggests a rewrite",
    },
  ]
  return (
    <div className="grid grid-cols-1 gap-4 px-4 *:data-[slot=card]:bg-linear-to-t *:data-[slot=card]:from-primary/5 *:data-[slot=card]:to-card *:data-[slot=card]:shadow-xs lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4 dark:*:data-[slot=card]:bg-card">
      {cards.map((c) => (
        <Card key={c.desc} className="@container/card">
          <CardHeader>
            <CardDescription>{c.desc}</CardDescription>
            <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">{c.value}</CardTitle>
            {c.badge && <CardAction>{c.badge}</CardAction>}
          </CardHeader>
          <CardFooter className="flex-col items-start gap-1.5 text-sm">
            <div className="text-muted-foreground">{c.foot}</div>
          </CardFooter>
        </Card>
      ))}
    </div>
  )
}
