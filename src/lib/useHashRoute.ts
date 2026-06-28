import { useEffect, useState } from "react";

export type Route = "overview" | "methodology" | "lab";
export const ROUTES: { id: Route; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "solar:widget-5-bold" },
  { id: "methodology", label: "Methodology", icon: "solar:graph-up-bold" },
  { id: "lab", label: "Strategy Lab", icon: "solar:test-tube-bold" },
];

function parse(): Route {
  const h = window.location.hash.replace(/^#\/?/, "").split(/[/?#]/)[0];
  return (ROUTES.some((r) => r.id === h) ? h : "overview") as Route;
}

/** Tiny hash router — gh-pages-safe (no server rewrites), no router dependency. */
export function useHashRoute() {
  const [route, setRoute] = useState<Route>(parse);
  useEffect(() => {
    const onHash = () => {
      setRoute(parse());
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const navigate = (r: Route) => {
    if (parse() === r) window.scrollTo({ top: 0 }); // re-selecting current route still scrolls up
    window.location.hash = `#/${r}`;
  };
  return { route, navigate };
}
