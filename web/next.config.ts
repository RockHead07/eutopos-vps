import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Disajikan FastAPI dari web/out. Tanpa server Node: rute dinamis lewat parameter query.
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
