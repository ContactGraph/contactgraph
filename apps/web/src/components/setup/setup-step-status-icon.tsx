import { CheckCircle2, CircleHelp, Loader2 } from "lucide-react";

interface SetupStepStatusIconProps {
  complete: boolean;
  inProgress: boolean;
}

export function SetupStepStatusIcon({
  complete,
  inProgress,
}: SetupStepStatusIconProps) {
  if (complete) {
    return <CheckCircle2 className="size-5 text-green-600" />;
  }
  if (inProgress) {
    return <Loader2 className="size-5 animate-spin text-muted-foreground" />;
  }
  return (
    <CircleHelp
      className="size-5 text-muted-foreground/50"
      aria-hidden
    />
  );
}
