/** The steps that take a new student from an empty app to a first risk check, and what each is for. */

const MONTHS_NEEDED = 4;

export type StepInput = {
  monthsOfHistory: number;
  recurringCount: number;
  limitsRecorded: number;
  forecastReady: boolean;
  riskChecked: boolean;
};

export type Step = {
  id: "history" | "recurring" | "limits" | "forecast" | "risk";
  title: string;
  why: string;
  done: boolean;
  /** Where the person is on the way, when that helps ("2 of 4 months so far"). */
  detail?: string;
  href?: string;
  action?: string;
};

export function gettingStartedSteps(input: StepInput): Step[] {
  const historyDone = input.monthsOfHistory >= MONTHS_NEEDED;
  return [
    {
      id: "history",
      title: "Bring in your spending",
      why: "The forecast learns from at least four months of what you really spent. Import a statement or add transactions by hand.",
      done: historyDone,
      detail: historyDone ? undefined : `${input.monthsOfHistory} of ${MONTHS_NEEDED} months so far`,
      href: "/import",
      action: "Import",
    },
    {
      id: "recurring",
      title: "Confirm your regular bills and income",
      why: "Rent, allowance, PTPTN and subscriptions land on set dates. Confirming them lets the forecast place them exactly and only guess your everyday spending.",
      done: input.recurringCount > 0,
      href: "/recurring",
      action: "Recurring items",
    },
    {
      id: "limits",
      title: "Record your BNPL limits",
      why: "Copy each limit from the provider's app. The risk check then counts only what the provider would really finance, and what you would pay yourself.",
      done: input.limitsRecorded > 0,
      detail: input.limitsRecorded > 0 ? undefined : "Skip this if you do not use BNPL",
      href: "/plans",
      action: "BNPL plans",
    },
    {
      id: "forecast",
      title: "See your forecast",
      why: "Your running margin shows how much you are likely to have left, or be short, month by month, and how sure the forecast is.",
      done: input.forecastReady,
    },
    {
      id: "risk",
      title: "Check a purchase before you buy",
      why: "Pick a provider and a price: you get Safe, Caution or At Risk, the reasons, and the smallest change that would make it safe.",
      done: input.riskChecked,
      href: "/risk",
      action: "Risk check",
    },
  ];
}
