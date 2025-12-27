// src/content/config.ts
import { defineCollection, z } from "astro:content";

/**
 * Gemeinsame Basis für chronikfähige Inhalte
 */
const base = z.object({
  title: z.string(),
  subtitle: z.string().optional(),

  date: z.coerce.date(),
  updated: z.coerce.date().optional(),
  order: z.number().int().optional(),

  // tags sind optional, du nutzt sie nicht aktiv
  tags: z.array(z.string()).default([]),
  heroImage: z.string().optional(),
});

/**
 * Stellen & Gebäude
 * =================
 * Häuser, Bauwerke und markante Stellen
 */
const stellen = base.extend({
  label: z.string().min(1),
  x: z.number(),
  y: z.number(),
});

/**
 * Ortschaften
 * ===========
 * Inhalt + Marker in EINEM Markdown
 */
const ortschaften = base.extend({
  label: z.string().min(1),
  x: z.number(),
  y: z.number(),
});

/**
 * Collections
 */
export const collections = {
  landschaft: defineCollection({
    type: "content",
    schema: base,
  }),

  geschichte: defineCollection({
    type: "content",
    schema: base,
  }),

  stellen: defineCollection({
    type: "content",
    schema: stellen,
  }),

  ortschaften: defineCollection({
    type: "content",
    schema: ortschaften,
  }),
};
