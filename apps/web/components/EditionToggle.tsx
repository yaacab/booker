"use client";
import { useEffect, useState } from "react";
export function EditionToggle() {
  const [black, setBlack] = useState(false);
  useEffect(() => { setBlack(document.documentElement.dataset.edition === "black"); }, []);
  function toggle() { const next = !black; setBlack(next); document.documentElement.dataset.edition = next ? "black" : "light"; try { localStorage.setItem("booker.edition", next ? "black" : "light"); } catch {} }
  return <button className="edition-toggle" type="button" onClick={toggle} aria-pressed={black} aria-label="Black Edition"><span aria-hidden>{black ? "◐" : "◑"}</span> {black ? "Black Edition" : "Light Edition"}</button>;
}
