// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Example "Dashboard Grid" page (see references/layout-patterns.md, pattern 2):
// Header -> stat card row -> content panels. Replace the sample stats/panels
// with the target app's real data, wired through src/services/api.js.

import { Activity, Boxes, CheckCircle2, Cpu } from 'lucide-react';
import Header from '@/components/layout/Header';
import StatCard from '@/components/StatCard';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

export default function App() {
  return (
    <div className="min-h-screen bg-background">
      <Header appName="App Name" subtitle="Open Edge Platform" status="connected" />

      <main className="p-5 flex flex-col gap-4">
        <section className="grid grid-cols-4 max-[1100px]:grid-cols-2 max-[480px]:grid-cols-1 gap-4">
          <StatCard label="Active sources" value={2} icon={Boxes} color="blue" />
          <StatCard label="Discovered" value={0} icon={Activity} color="purple" />
          <StatCard label="Enabled" value={0} icon={CheckCircle2} color="green" />
          <StatCard label="Compute device" value="CPU" icon={Cpu} color="orange" />
        </section>

        <section className="grid grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Panel A</CardTitle>
            </CardHeader>
            <CardContent>Replace with the app's primary control/config panel.</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Panel B</CardTitle>
            </CardHeader>
            <CardContent>Replace with results/analytics panel.</CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}
