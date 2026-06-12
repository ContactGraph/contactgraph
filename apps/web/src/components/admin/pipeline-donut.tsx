"use client";

interface PipelineDonutProps {
  processed: number;
  total: number;
  failed: number;
  label: string;
}

const SIZE: number = 120;
const STROKE: number = 14;
const RADIUS: number = (SIZE - STROKE) / 2;
const CIRCUMFERENCE: number = 2 * Math.PI * RADIUS;

function arcLength(value: number, max: number): number {
  if (max <= 0 || value <= 0) {
    return 0;
  }
  return (value / max) * CIRCUMFERENCE;
}

export function PipelineDonut({
  processed,
  total,
  failed,
  label,
}: PipelineDonutProps) {
  const safeTotal: number = Math.max(total, processed + failed, 1);
  const processedLen: number = arcLength(processed, safeTotal);
  const failedLen: number = arcLength(failed, safeTotal);
  const remaining: number = Math.max(safeTotal - processed - failed, 0);
  const remainingLen: number = arcLength(remaining, safeTotal);

  const processedOffset: number = 0;
  const failedOffset: number = -processedLen;
  const remainingOffset: number = -(processedLen + failedLen);

  return (
    <div className="flex flex-col items-center gap-3">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={label}>
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="currentColor"
          strokeWidth={STROKE}
          className="text-muted/30"
        />
        {remainingLen > 0 ? (
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="currentColor"
            strokeWidth={STROKE}
            strokeDasharray={`${remainingLen} ${CIRCUMFERENCE - remainingLen}`}
            strokeDashoffset={remainingOffset}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            className="text-muted-foreground/40"
          />
        ) : null}
        {processedLen > 0 ? (
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="currentColor"
            strokeWidth={STROKE}
            strokeDasharray={`${processedLen} ${CIRCUMFERENCE - processedLen}`}
            strokeDashoffset={processedOffset}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            className="text-emerald-500"
          />
        ) : null}
        {failedLen > 0 ? (
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="currentColor"
            strokeWidth={STROKE}
            strokeDasharray={`${failedLen} ${CIRCUMFERENCE - failedLen}`}
            strokeDashoffset={failedOffset}
            transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
            className="text-destructive"
          />
        ) : null}
        <text
          x="50%"
          y="50%"
          dominantBaseline="middle"
          textAnchor="middle"
          className="fill-foreground text-sm font-semibold"
        >
          {processed.toLocaleString()}
        </text>
      </svg>
      <div className="text-center">
        <p className="text-sm font-medium">{label}</p>
        <p className="text-xs text-muted-foreground">
          {processed.toLocaleString()} / {safeTotal.toLocaleString()} processed
        </p>
      </div>
    </div>
  );
}
