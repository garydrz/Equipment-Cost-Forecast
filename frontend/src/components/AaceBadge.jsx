import { aaceBadgeClass } from "@/lib/api";

export function AaceBadge({ value, testId }) {
  if (!value) return null;
  return (
    <span
      data-testid={testId}
      className={`inline-flex items-center px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider rounded-none ${aaceBadgeClass(value)}`}
    >
      {value}
    </span>
  );
}
