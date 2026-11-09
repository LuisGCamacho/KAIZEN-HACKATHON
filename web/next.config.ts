import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Servidor mínimo (.next/standalone): la imagen de Docker no necesita todo node_modules (despliegues más rápidos)
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
