type IconName = "calendar" | "request" | "profile" | "arrow" | "clock" | "pin" | "building";

export function CabinetIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, string> = {
    calendar: "M7 3v4m10-4v4M4 10h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Zm3 9h3v3H8z",
    request: "M4 5h16v14H4zM4 6l8 7 8-7",
    profile: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-3a5 5 0 0 1 5-5h6a5 5 0 0 1 5 5v3Z",
    arrow: "M5 12h14m-5-5 5 5-5 5",
    clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
    pin: "M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Zm-4 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z",
    building: "M4 21V7l8-4 8 4v14H4Zm5 0v-6h6v6M8 9h1m6 0h1",
  };
  return <svg className="cabinet-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>;
}
