// The project page (public/index.html, the 3D story) is served at /q2-offload/ and the
// documentation, built from ../docs/*.md, at /q2-offload/docs/.
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { unified } from '@astrojs/markdown-remark';
import { docsLinks, githubAlerts, listStart } from './src/remark-docs.mjs';

const BASE = '/q2-offload';
const DOCS_DIR = fileURLToPath(new URL('../docs', import.meta.url));

export default defineConfig({
  site: 'https://cedbossneo.github.io',
  base: BASE,
  trailingSlash: 'always',
  markdown: { processor: unified({ remarkPlugins: [docsLinks({ docsDir: DOCS_DIR, base: BASE }), githubAlerts(), listStart()] }) },
  vite: { server: { fs: { allow: ['..'] } } },
  integrations: [
    starlight({
      title: 'q2-offload',
      description: 'Run mainline Klipper, Happy Hare and Spoolman for a Qidi Q2 and Qidi Box on your own computer.',
      logo: { src: './src/assets/logo.svg' },
      favicon: '/favicon.svg',
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/cedbossneo/q2-offload' }],
      editLink: { baseUrl: 'https://github.com/cedbossneo/q2-offload/edit/main/docs/' },
      customCss: ['./src/styles/docs.css'],
      head: [
        { tag: 'link', attrs: { rel: 'preconnect', href: 'https://fonts.googleapis.com' } },
        { tag: 'link', attrs: { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,300..800&family=Hanken+Grotesk:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap' } },
      ],
      sidebar: [
        { label: 'Start here', items: ['docs', 'docs/start/requirements', 'docs/start/before-you-start'] },
        {
          label: 'Install',
          items: ['docs/install/prepare-host', 'docs/install/run-installer', 'docs/install/calibrate', 'docs/install/slicer'],
        },
        {
          label: 'Using it',
          items: ['docs/use/web-interfaces', 'docs/use/spools', 'docs/use/pressure-advance', 'docs/use/drying', 'docs/use/failure-detection', 'docs/use/updates'],
        },
        {
          label: 'When something goes wrong',
          items: ['docs/help/klipper-does-not-connect', 'docs/help/flashing', 'docs/help/back-to-stock', 'docs/help/known-limits'],
        },
        {
          label: 'Reference',
          collapsed: true,
          items: ['docs/reference/slicer-gcode', 'docs/reference/older-installs', 'docs/reference/failure-detection', 'docs/reference/repository', 'docs/reference/credits'],
        },
      ],
    }),
  ],
});
