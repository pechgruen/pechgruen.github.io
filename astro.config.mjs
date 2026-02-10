// @ts-check
import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://pechgruen.github.io",
  base: "/",

  image: {
    service: {
      entrypoint: "astro/assets/services/noop",
    },
  },

  integrations: [
    mdx(),
    sitemap(),
  ],
});
