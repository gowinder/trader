import { type RouteConfig, index, layout, route } from "@react-router/dev/routes";

export default [
  index("routes/_index.tsx"),
  route("login", "routes/login.tsx"),
  route("logout", "routes/logout.tsx"),
  route("dashboard", "routes/dashboard.tsx", [
    index("routes/dashboard._index.tsx"),
    route("decisions", "routes/dashboard.decisions.tsx"),
    route("decisions/:id", "routes/dashboard.decisions.$id.tsx"),
  ]),
] satisfies RouteConfig;
