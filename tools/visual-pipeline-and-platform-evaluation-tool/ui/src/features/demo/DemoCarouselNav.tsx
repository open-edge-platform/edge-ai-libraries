// SPDX-License-Identifier: Apache-2.0
import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

export type DemoCarouselNavProps = {
  index: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  onGoTo: (idx: number) => void;
  /** Add z-10 to arrow buttons when they need to stack above overlapping content. */
  layered?: boolean;
};

export const DemoCarouselNav = ({
  index,
  total,
  onPrev,
  onNext,
  onGoTo,
  layered = false,
}: DemoCarouselNavProps) => (
  <>
    <button
      onClick={onPrev}
      disabled={index === 0}
      className={cn(
        "absolute left-0 top-1/2 -translate-y-1/2 -translate-x-3 bg-demo-carousel-button-surface hover:bg-demo-carousel-button-surface-hover disabled:opacity-30 disabled:cursor-not-allowed rounded-full p-2 shadow-lg backdrop-blur-sm border border-demo-carousel-button-border transition-all",
        layered && "z-10",
      )}
    >
      <ChevronLeft className="w-5 h-5 text-demo-carousel-button-icon" />
    </button>

    <button
      onClick={onNext}
      disabled={index >= total - 1}
      className={cn(
        "absolute right-0 top-1/2 -translate-y-1/2 translate-x-3 bg-demo-carousel-button-surface hover:bg-demo-carousel-button-surface-hover disabled:opacity-30 disabled:cursor-not-allowed rounded-full p-2 shadow-lg backdrop-blur-sm border border-demo-carousel-button-border transition-all",
        layered && "z-10",
      )}
    >
      <ChevronRight className="w-5 h-5 text-demo-carousel-button-icon" />
    </button>

    <div className="absolute -bottom-4 left-1/2 -translate-x-1/2 flex gap-1.5">
      {Array.from({ length: total }).map((_, idx) => (
        <button
          key={idx}
          onClick={() => onGoTo(idx)}
          className={cn(
            "w-2 h-2 rounded-full transition-all",
            idx === index
              ? "bg-demo-carousel-dot-active w-6"
              : "bg-demo-carousel-dot hover:bg-demo-carousel-dot-hover",
          )}
        />
      ))}
    </div>
  </>
);
