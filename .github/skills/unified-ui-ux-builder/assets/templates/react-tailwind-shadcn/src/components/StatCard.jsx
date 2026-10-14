// Copyright (C) 2026 Intel Corporation
// SPDX-License-Identifier: Apache-2.0
//
// Dashboard Grid stat card row (see references/layout-patterns.md, pattern 2).
// Pass one entry per metric; `color` must be one of the shared accent keys so
// the gradient bar and icon tint stay consistent with design-tokens.md.

const BAR_GRADIENT = {
  blue: 'from-[#0071C5] to-[#38B2F4]',
  purple: 'from-[#7B2FBE] to-[#B07EE8]',
  green: 'from-[#0DBF8C] to-[#34D3A9]',
  orange: 'from-[#F59E0B] to-[#FBBF24]',
  teal: 'from-[#0891B2] to-[#22D3EE]',
};

const ICON_BG = {
  blue: 'bg-[#0071C5]/10 text-[#0071C5]',
  purple: 'bg-[#7B2FBE]/10 text-[#7B2FBE]',
  green: 'bg-[#0DBF8C]/10 text-[#0DBF8C]',
  orange: 'bg-[#F59E0B]/10 text-[#F59E0B]',
  teal: 'bg-[#0891B2]/10 text-[#0891B2]',
};

export default function StatCard({ label, value, icon: Icon, color = 'blue' }) {
  return (
    <div className="relative overflow-hidden rounded-xl bg-card shadow-(--shadow-card)">
      <div className={`absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r ${BAR_GRADIENT[color]}`} />
      <div className="flex items-center gap-4 pt-[22px] pb-[18px] px-5">
        <div className={`flex items-center justify-center size-10 rounded-full ${ICON_BG[color]}`}>
          {Icon ? <Icon size={20} strokeWidth={1.8} /> : null}
        </div>
        <div className="min-w-0">
          <div className="text-2xl font-semibold leading-tight text-foreground">{value}</div>
          <div className="text-xs text-muted-foreground">{label}</div>
        </div>
      </div>
    </div>
  );
}
