"use client";
import { useEffect, useState } from "react";
export function EditionToggle() {
  const [edition, setEdition] = useState<"black" | "light">("black");

  useEffect(() => {
    setEdition(document.documentElement.dataset.edition === "light" ? "light" : "black");
  }, []);

  function toggle() {
    const next = document.documentElement.dataset.edition === "light" ? "black" : "light";
    document.documentElement.dataset.edition = next;
    document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
      meta.setAttribute("content", next === "light" ? "#edf1eb" : "#101112");
    });
    setEdition(next);
    try { localStorage.setItem("booker.edition", next); } catch { /* The selected theme still works in this tab. */ }
  }

  return (
    <button
      className="edition-toggle"
      type="button"
      onClick={toggle}
      aria-pressed={edition === "light"}
      aria-label={edition === "light" ? "Включить тёмную тему" : "Включить Light Edition"}
    >
      <span aria-hidden="true">{edition === "light" ? "◑" : "◐"}</span>
      <span aria-hidden="true">{edition === "light" ? "Тёмная тема" : "Light Edition"}</span>
    </button>
  );
}
