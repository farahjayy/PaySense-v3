/**
 * A short context box for readers outside Malaysia (WP7): the currency, the providers, and why
 * students' income arrives the way it does. Words only: no figure here is anyone's data.
 */
export function LocalTerms({ className = "" }: { className?: string }) {
  return (
    <details className={className}>
      <summary>New to BNPL in Malaysia?</summary>
      <ul>
        <li>
          Amounts are in Malaysian ringgit (RM); a ringgit is a hundred sen, and PaySense counts in
          sen so nothing is lost to rounding.
        </li>
        <li>
          SPayLater (Shopee), TikTok PayLater and Atome are the buy-now-pay-later services students
          meet most at online checkouts. Each splits a purchase into instalments, sometimes with a
          fee, up to a spending limit the provider sets.
        </li>
        <li>
          PTPTN is Malaysia&apos;s national higher-education loan fund; many students receive it
          once a semester, so their income arrives in lumps. Allowances from family, a scholarship
          or a programme such as PESP usually arrive monthly.
        </li>
        <li>
          Small instalments make a phone or a laptop feel affordable today, but several plans at
          once can outrun an income that arrives in lumps. PaySense checks that before you commit.
        </li>
      </ul>
    </details>
  );
}
