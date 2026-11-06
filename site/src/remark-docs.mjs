// The pages in docs/ are plain Markdown that reads well on GitHub. This makes the same
// files work on the site:
// - a link to another page (../use/spools.md#tags) goes to its route (/q2-offload/docs/use/spools/#tags);
// - a link to a repository file (../slicer/orca/...) goes to that file on GitHub;
// - a GitHub alert (> [!CAUTION]) becomes a Starlight aside.
import path from 'node:path';

const REPO = 'https://github.com/cedbossneo/q2-offload/blob/main/';
const ALERTS = { NOTE: ['note', 'Note'], TIP: ['tip', 'Tip'], IMPORTANT: ['note', 'Important'], WARNING: ['caution', 'Warning'], CAUTION: ['danger', 'Caution'] };

function walk(node, fn) {
  fn(node);
  if (node.children) node.children.forEach((child) => walk(child, fn));
}

export function docsLinks({ docsDir, base }) {
  const repoRoot = path.resolve(docsDir, '..');
  return () => (tree, file) => {
    const from = path.dirname(file.path);
    walk(tree, (node) => {
      if (node.type !== 'link' || /^[a-z]+:|^#|^\//i.test(node.url)) return;
      const [target, hash] = node.url.split('#');
      const abs = path.resolve(from, target);
      if (abs.startsWith(docsDir + path.sep) && abs.endsWith('.md')) {
        const route = path.relative(docsDir, abs).replace(/\.md$/, '').replace(/(^|\/)index$/, '');
        node.url = `${base}/docs/${route ? route + '/' : ''}${hash ? '#' + hash : ''}`;
      } else if (abs.startsWith(repoRoot)) {
        const rel = path.relative(repoRoot, abs);
        node.url = (path.extname(rel) ? REPO : REPO.replace('/blob/', '/tree/')) + rel + (hash ? '#' + hash : '');
      }
    });
  };
}

export function githubAlerts() {
  return () => (tree) => {
    walk(tree, (node) => {
      if (node.type !== 'blockquote') return;
      const first = node.children[0];
      const text = first?.type === 'paragraph' && first.children[0]?.type === 'text' ? first.children[0] : null;
      const match = text && /^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/.exec(text.value);
      if (!match) return;
      const [variant, title] = ALERTS[match[1]];
      text.value = text.value.slice(match[0].length);
      if (!text.value && first.children[1]?.type === 'break') first.children.splice(0, 2);
      else if (!text.value) first.children.shift();
      if (!first.children.length) node.children.shift();
      const content = { type: 'blockquote', data: { hName: 'div', hProperties: { className: ['starlight-aside__content'] } }, children: node.children };
      node.data = { hName: 'aside', hProperties: { className: ['starlight-aside', `starlight-aside--${variant}`], ariaLabel: title } };
      node.children = [
        { type: 'paragraph', data: { hName: 'p', hProperties: { className: ['starlight-aside__title'], ariaHidden: 'true' } }, children: [{ type: 'text', value: title }] },
        content,
      ];
    });
  };
}

// Numbered steps are drawn by CSS counters; a list that starts at 6 must count from there.
export function listStart() {
  return () => (tree) => {
    walk(tree, (node) => {
      if (node.type === 'list' && node.ordered && node.start > 1) {
        node.data = { ...node.data, hProperties: { ...(node.data?.hProperties || {}), style: `--step-start: ${node.start - 1}` } };
      }
    });
  };
}
