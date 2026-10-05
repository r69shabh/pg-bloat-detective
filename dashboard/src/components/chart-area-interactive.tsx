"use client"

import * as React from "react"
import type { ReactNode } from "react"
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { Feed } from "@/lib/feed"

export const description = "Dead tuples over time per table"

const PALETTE = ["var(--chart-1, #2563eb)", "var(--chart-2, #dc2626)", "var(--chart-3, #16a34a)", "var(--chart-4, #d97706)", "var(--chart-5, #9333ea)"]

function fmtTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString("en-US", { hour12: false })
}

export function ChartAreaInteractive({ feed }: { feed: Feed }) {
  const tables = Object.keys(feed.series).slice(0, 5)
  const rows = React.useMemo(() => {
    const byTs = new Map<number, Record<string, number>>()
    for (const t of tables) {
      for (const p of feed.series[t] ?? []) {
        byTs.set(p.ts, { ...(byTs.get(p.ts) ?? {}), [t]: p.dead })
      }
    }
    return [...byTs.entries()].map(([ts, rest]) => ({ ts, ...rest })).sort((a, b) => a.ts - b.ts)
  }, [feed, tables.join(",")]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Card className="@container/card">
      <CardHeader>
        <CardTitle>Dead tuples</CardTitle>
        <CardDescription>Per-table timeline from the collector snapshots</CardDescription>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        <div className="h-[250px] w-full">
          <ResponsiveContainer>
            <AreaChart data={rows}>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="ts" tickLine={false} axisLine={false} tickMargin={8} minTickGap={32} tickFormatter={fmtTime} />
              <YAxis tickLine={false} axisLine={false} width={60} tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v))} />
              <Tooltip labelFormatter={(label: ReactNode) => fmtTime(Number(label))} />
              {tables.map((t, i) => (
                <Area key={t} dataKey={t} type="monotone" fill={PALETTE[i % PALETTE.length]} stroke={PALETTE[i % PALETTE.length]} fillOpacity={0.25} />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
