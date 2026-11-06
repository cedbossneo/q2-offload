// The documentation pages live in the repository's docs/ folder, as plain Markdown
// (readable on GitHub). Their ids get a docs/ prefix so the site serves them under /docs/.
import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
  docs: defineCollection({
    loader: glob({
      pattern: '**/*.md',
      base: '../docs',
      generateId: ({ entry }) => `docs/${entry.replace(/\.md$/, '')}`.replace(/\/index$/, ''),
    }),
    schema: docsSchema(),
  }),
};
