/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Playwright drives the dev server over 127.0.0.1
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
