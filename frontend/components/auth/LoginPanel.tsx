import { BandFace, BrandMark, type BandKey } from "./LoginArt";

// Same names as the app's result bands (lib/format.ts), in the order the app lists them.
const RESULTS: readonly { band: BandKey; name: string }[] = [
  { band: "safe", name: "Safe" },
  { band: "caution", name: "Caution" },
  { band: "risk", name: "At Risk" },
];

export function LoginPanel() {
  return (
    <section className="lg-panel" aria-label="About PaySense">
      <div className="lg-pattern" aria-hidden="true" />
      <div className="lg-rings" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div className="lg-blob lg-blob-a" aria-hidden="true" />
      <div className="lg-blob lg-blob-b" aria-hidden="true" />

      <div className="lg-brand">
        <BrandMark />
        <span className="lg-brand-name">
          Pay<span>Sense</span>
        </span>
      </div>

      <div className="lg-pitch">
        <h2>
          Think before you <em>split.</em>
        </h2>
        <p>Instantly check if a BNPL instalment fits into your monthly spending.</p>
      </div>

      <ul className="lg-bands" aria-label="The three results PaySense gives">
        {RESULTS.map(({ band, name }) => (
          <li key={band} className="lg-band">
            <BandFace band={band} />
            <span className={`lg-chip lg-chip-${band}`}>{name}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
