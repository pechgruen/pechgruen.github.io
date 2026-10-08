// src/content/config.ts
import { defineCollection, z } from "astro:content";

/**
 * Gemeinsame Basis für chronikfähige Inhalte
 * date/updated bleiben echte Dates (wie bisher)
 */
const base = z.object({
  title: z.string(),
  subtitle: z.string().optional(),
  description: z.string().optional(),

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
 * Personen
 * ========
 * Biografien, Erinnerungen, Nachrufe
 * birth/death bewusst als STRING (für "ca.", "?" etc.)
 */
const personen = base.extend({
  birth: z.string().optional(),
  birthplace: z.string().optional(),

  death: z.string().optional(),
  deathplace: z.string().optional(),

  source: z.string().optional(),
  author: z.string().optional(),
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

  wege: defineCollection({
    type: "content",
    schema: base,
  }),

// NOTE:
// Collection "ortschaften" enthält die Inhalte des Bereichs "Nachbarorte".
// Der Name ist historisch gewachsen und bewusst beibehalten.
  ortschaften: defineCollection({
    type: "content",
    schema: ortschaften,
  }),

  personen: defineCollection({
    type: "content",
    schema: personen,
  }),

  cesky: defineCollection({
    type: "content",
    schema: base,
  }),

};
