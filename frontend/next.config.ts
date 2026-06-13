import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root to this directory so Turbopack ignores the
  // stray lockfile in the home directory (~/pnpm-lock.yaml).
  turbopack: {
    root: path.join(__dirname),
  },
};

export default nextConfig;
