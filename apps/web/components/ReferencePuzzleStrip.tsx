/** Brand imagery only; these photographs do not identify marketplace profiles. */
export function ReferencePuzzleStrip() {
  return <div className="reference-puzzle-strip" aria-hidden="true">
    {[
      ["dj", "Люди вдохновляют"],
      ["venue", "Места объединяют"],
      ["photographer", "События остаются"],
    ].map(([asset, label]) => <figure key={asset}>
      <img src={`/design/puzzle-${asset}.png`} alt="" width={1280} height={1280} loading="lazy" decoding="async" />
      <figcaption>{label}</figcaption>
    </figure>)}
  </div>;
}
